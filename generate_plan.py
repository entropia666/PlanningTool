#!/usr/bin/env python3
"""Generate a Gantt-style planning HTML view from JSON item files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plan_logic import assign_rows, load_items


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
