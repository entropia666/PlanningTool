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


def assign_rows(items: list[dict]) -> None:
    """Assign row indices to tasks; milestones/deliverables share task rows."""
    tasks = [item for item in items if item.get("type") == "task"]
    if not tasks:
        return

    by_id = {item["id"]: item for item in items}
    memo: dict[str, int] = {}

    def depth(item_id: str, visiting: set[str]) -> int:
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
        value = max((depth(p, visiting) for p in preds), default=-1) + 1
        visiting.remove(item_id)
        memo[item_id] = value
        return value

    group_to_row: dict[str, int] = {}
    next_group_row = 0
    for item in tasks:
        if "group" in item and "row" not in item:
            key = str(item["group"])
            if key not in group_to_row:
                group_to_row[key] = next_group_row
                next_group_row += 1
            item["row"] = group_to_row[key]

    for item in tasks:
        if "row" not in item:
            item["row"] = depth(item["id"], set())
            item["_auto_row"] = True

    occupied = {item["row"] for item in tasks if not item.get("_auto_row")}
    for item in sorted(
        (t for t in tasks if t.get("_auto_row")),
        key=lambda i: (i["row"], i["id"]),
    ):
        row = item["row"]
        while row in occupied:
            row += 1
        item["row"] = row
        occupied.add(row)

    for item in tasks:
        item.pop("_auto_row", None)

    unique_rows = sorted({item["row"] for item in tasks})
    row_map = {old: new for new, old in enumerate(unique_rows)}
    for item in tasks:
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
        default=str(root / "data" / "example"),
        help="Directory containing one JSON file per planning item",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(root / "output" / "plan.html"),
        help="Output HTML file path",
    )
    parser.add_argument(
        "-t",
        "--title",
        default="Project Plan",
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
