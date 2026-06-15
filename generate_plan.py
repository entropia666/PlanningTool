#!/usr/bin/env python3
"""Generate a Gantt-style planning HTML view from JSON item files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_items(data_dir: Path) -> list[dict]:
    items: list[dict] = []
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No JSON files found in {data_dir}")

    for path in paths:
        with path.open(encoding="utf-8") as handle:
            item = json.load(handle)
        if not isinstance(item, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        item["_source_file"] = path.name
        items.append(item)

    ids = {item["id"] for item in items if "id" in item}
    for item in items:
        if "id" not in item:
            raise ValueError(f"{item['_source_file']} is missing required field 'id'")
        for pred in item.get("predecessors", []):
            if pred not in ids:
                raise ValueError(
                    f"{item['id']} references unknown predecessor '{pred}' "
                    f"(from {item['_source_file']})"
                )

    return items


ROWABLE_TYPES = frozenset({"task", "milestone", "deliverable"})
ROW_ASSIGN_TYPES = frozenset({"task", "deliverable"})


def assign_rows(items: list[dict]) -> None:
    """Assign row indices to tasks and deliverables; milestones render on the timeline header."""
    rowable = [item for item in items if item.get("type") in ROW_ASSIGN_TYPES]
    if not rowable:
        return

    by_id = {item["id"]: item for item in items}
    memo: dict[str, int] = {}

    def task_depth(item_id: str, visiting: set[str]) -> int:
        if item_id in memo:
            return memo[item_id]
        if item_id in visiting:
            return 0
        visiting.add(item_id)
        item = by_id[item_id]
        preds = [
            p
            for p in item.get("predecessors", [])
            if by_id.get(p, {}).get("type") == "task"
        ]
        value = max((task_depth(p, visiting) for p in preds), default=-1) + 1
        visiting.remove(item_id)
        memo[item_id] = value
        return value

    group_to_row: dict[str, int] = {}
    next_group_row = 0
    for item in rowable:
        if item.get("anchor"):
            continue
        if "group" in item and "row" not in item:
            key = str(item["group"])
            if key not in group_to_row:
                group_to_row[key] = next_group_row
                next_group_row += 1
            item["row"] = group_to_row[key]

    for item in rowable:
        if item.get("anchor") or "row" in item:
            continue
        if item["type"] == "task":
            item["row"] = task_depth(item["id"], set())
            item["_auto_row"] = True

    occupied = {item["row"] for item in rowable if "row" in item and not item.get("_auto_row")}
    for item in sorted(
        (i for i in rowable if i.get("_auto_row")),
        key=lambda i: (i["row"], i["id"]),
    ):
        row = item["row"]
        while row in occupied:
            row += 1
        item["row"] = row
        occupied.add(row)

    for item in rowable:
        if item.get("anchor") or "row" in item:
            continue
        if item["type"] == "deliverable":
            row = 0
            while row in occupied:
                row += 1
            item["row"] = row
            occupied.add(row)

    for item in rowable:
        anchor_id = item.get("anchor")
        if anchor_id and anchor_id in by_id and "row" in by_id[anchor_id]:
            item["row"] = by_id[anchor_id]["row"]

    for item in rowable:
        item.pop("_auto_row", None)

    unique_rows = sorted({item["row"] for item in rowable})
    row_map = {old: new for new, old in enumerate(unique_rows)}
    for item in rowable:
        item["row"] = row_map[item["row"]]


def build_html(items: list[dict], title: str, template_path: Path) -> str:
    assign_rows(items)
    payload = json.dumps(items, indent=2, ensure_ascii=False)
    template = template_path.read_text(encoding="utf-8")
    return template.replace("{{TITLE}}", title).replace("{{ITEMS_JSON}}", payload)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Build a Gantt-style HTML plan from JSON item files."
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        default=str(root / "data" / "aircraft-design"),
        help="Directory containing one JSON file per planning item",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(root / "output" / "aircraft-design.html"),
        help="Output HTML file path",
    )
    parser.add_argument(
        "-t",
        "--title",
        default="Aircraft Design",
        help="Page title shown in the browser",
    )
    parser.add_argument(
        "--template",
        default=str(root / "templates" / "gantt.html"),
        help="HTML template path",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    output_path = Path(args.output)
    template_path = Path(args.template)

    try:
        items = load_items(data_dir)
        html = build_html(items, args.title, template_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {len(items)} items to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
