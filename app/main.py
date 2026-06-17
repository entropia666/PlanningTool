"""FastAPI application for the interactive Gantt editor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from plan_logic import (
    DISCIPLINES,
    INTERNAL_FIELDS,
    NEW_TASK_DURATION_MONTHS,
    add_calendar_months,
    apply_cascade,
    assign_rows,
    clamp_to_predecessors,
    find_item_file,
    format_date,
    load_items,
    make_filename,
    new_deliverable_template,
    new_task_template,
    parse_date,
    plan_data_dir,
    read_item_file,
    snap_deliverable_to_milestone,
    strip_internal_fields,
    validate_predecessors,
    write_item_file,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "planning-item.schema.json"
TEMPLATE_PATH = ROOT / "templates" / "gantt-editor.html"


def create_app(default_plan: str = "aircraft-design") -> FastAPI:
    app = FastAPI(title="Aircraft Planning Editor")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    def data_dir(plan: str) -> Path:
        path = plan_data_dir(ROOT, plan)
        if not path.is_dir():
            raise HTTPException(status_code=404, detail=f"Plan folder not found: {plan}")
        return path

    def validate_item_payload(item: dict[str, Any], data_path: Path, exclude_id: str | None = None) -> None:
        errors = sorted(validator.iter_errors(item), key=lambda e: e.path)
        if errors:
            raise HTTPException(
                status_code=400,
                detail="; ".join(e.message for e in errors),
            )
        items = load_items(data_path)
        ids = {i["id"] for i in items if i["id"] != exclude_id}
        if item["id"] in ids:
            raise HTTPException(status_code=400, detail=f"Duplicate id '{item['id']}'")
        for pred in item.get("predecessors", []):
            all_ids = ids | {item["id"]}
            if pred not in all_ids:
                existing = {i["id"] for i in items}
                if pred not in existing:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown predecessor '{pred}'",
                    )

    def items_with_rows(plan: str) -> list[dict[str, Any]]:
        items = load_items(data_dir(plan))
        assign_rows(items)
        return items

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        html = (
            template.replace("{{TITLE}}", "Aircraft Design")
            .replace("{{DEFAULT_PLAN}}", default_plan)
        )
        return HTMLResponse(html)

    @app.get("/api/plans/{plan}/items")
    async def list_items(plan: str) -> JSONResponse:
        try:
            items = items_with_rows(plan)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(items)

    @app.get("/api/plans/{plan}/items/{item_id}")
    async def get_item(plan: str, item_id: str) -> JSONResponse:
        path = find_item_file(data_dir(plan), item_id)
        if path is None:
            raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
        item = read_item_file(path)
        return JSONResponse(item)

    @app.get("/api/plans/{plan}/sync")
    async def sync_status(plan: str) -> JSONResponse:
        """Return mtimes for all items — used by the client to detect external edits."""
        directory = data_dir(plan)
        files: dict[str, float] = {}
        for path in sorted(directory.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict) and "id" in data:
                    files[data["id"]] = path.stat().st_mtime
            except (json.JSONDecodeError, OSError):
                continue
        return JSONResponse({"files": files})

    @app.post("/api/plans/{plan}/items")
    async def create_item(plan: str, request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")

        directory = data_dir(plan)
        item_type = body.get("type", "task")
        if item_type not in ("task", "milestone", "deliverable"):
            raise HTTPException(status_code=400, detail="Invalid type")

        name = body.get("name", "New task")
        filename = body.get("_filename") or make_filename(directory, item_type, name)
        path = directory / filename
        if path.exists():
            raise HTTPException(status_code=409, detail=f"File already exists: {filename}")

        item = {k: v for k, v in body.items() if not k.startswith("_")}
        validate_item_payload(item, directory)

        write_item_file(path, item)
        saved = read_item_file(path)
        return JSONResponse(saved, status_code=201)

    @app.put("/api/plans/{plan}/items/{item_id}")
    async def update_item(plan: str, item_id: str, request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")

        directory = data_dir(plan)
        path = find_item_file(directory, item_id)
        if path is None:
            raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")

        item = {k: v for k, v in body.items() if k not in INTERNAL_FIELDS and not k.startswith("_")}
        if item.get("id") != item_id:
            raise HTTPException(status_code=400, detail="Cannot change item id via update")

        validate_item_payload(item, directory, exclude_id=item_id)
        items = load_items(directory)
        by_id = {i["id"]: i for i in items}
        if item.get("type") == "deliverable":
            snap_deliverable_to_milestone(item, items)
            clamp_to_predecessors(item, by_id)
        write_item_file(path, item)
        saved = read_item_file(path)
        return JSONResponse(saved)

    @app.delete("/api/plans/{plan}/items/{item_id}")
    async def delete_item(plan: str, item_id: str) -> JSONResponse:
        directory = data_dir(plan)
        path = find_item_file(directory, item_id)
        if path is None:
            raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
        path.unlink()
        return JSONResponse({"deleted": item_id})

    @app.post("/api/plans/{plan}/cascade")
    async def cascade_updates(plan: str, request: Request) -> JSONResponse:
        """Apply date changes to one or more items with successor cascade, then persist."""
        body = await request.json()
        updates = body.get("updates", [])
        if not isinstance(updates, list) or not updates:
            raise HTTPException(status_code=400, detail="'updates' must be a non-empty array")

        directory = data_dir(plan)
        items = load_items(directory)
        by_id = {item["id"]: item for item in items}

        changed_ids: set[str] = set()
        for upd in updates:
            item_id = upd.get("id")
            if item_id not in by_id:
                raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
            item = by_id[item_id]
            if item["type"] == "task":
                if "start" in upd:
                    item["start"] = upd["start"]
                if "end" in upd:
                    item["end"] = upd["end"]
            elif "date" in upd:
                item["date"] = upd["date"]
                if item["type"] == "deliverable":
                    snap_deliverable_to_milestone(item, items)
            clamp_to_predecessors(item, by_id)
            changed_ids.add(item_id)

        affected = apply_cascade(items, changed_ids)

        saved: list[dict[str, Any]] = []
        for item_id in affected:
            item = by_id[item_id]
            path = find_item_file(directory, item_id)
            if path is None:
                continue
            write_item_file(path, item)
            saved.append(read_item_file(path))

        assign_rows(items)
        return JSONResponse({"items": saved, "affected_ids": sorted(affected)})

    @app.post("/api/plans/{plan}/items/new-task")
    async def create_task_at_position(plan: str, request: Request) -> JSONResponse:
        """Create a new task at a given date/row (right-click on chart)."""
        body = await request.json()
        start_str = body.get("start")
        row = body.get("row")
        if not start_str:
            raise HTTPException(status_code=400, detail="'start' date required")

        start = parse_date(start_str)
        end = add_calendar_months(start, NEW_TASK_DURATION_MONTHS)
        discipline = body.get("discipline")
        if discipline not in DISCIPLINES:
            discipline = None
        item = new_task_template(
            format_date(start),
            format_date(end),
            discipline=discipline,
            row=row,
        )
        directory = data_dir(plan)
        filename = make_filename(directory, "task", item["name"])
        path = directory / filename
        write_item_file(path, item)
        saved = read_item_file(path)
        assign_rows([saved])
        return JSONResponse(saved, status_code=201)

    @app.post("/api/plans/{plan}/items/new-deliverable")
    async def create_deliverable_at_position(plan: str, request: Request) -> JSONResponse:
        """Create a new deliverable at a given date/row (right-click on chart)."""
        body = await request.json()
        date_str = body.get("date") or body.get("start")
        row = body.get("row")
        if not date_str:
            raise HTTPException(status_code=400, detail="'date' required")

        discipline = body.get("discipline")
        if discipline not in DISCIPLINES:
            discipline = None
        item = new_deliverable_template(
            date_str,
            discipline=discipline,
            row=row,
        )
        directory = data_dir(plan)
        items = load_items(directory)
        snap_deliverable_to_milestone(item, items)
        filename = make_filename(directory, "deliverable", item["name"])
        path = directory / filename
        write_item_file(path, item)
        saved = read_item_file(path)
        assign_rows([saved])
        return JSONResponse(saved, status_code=201)

    return app
