"""Shared planning logic for static export and the interactive web app."""

from __future__ import annotations

import calendar
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROWABLE_TYPES = frozenset({"task", "milestone", "deliverable"})
ROW_ASSIGN_TYPES = frozenset({"task", "deliverable"})
INTERNAL_FIELDS = frozenset({"_source_file", "_auto_row", "_mtime"})

TYPE_PREFIXES = {
    "task": "task",
    "milestone": "milestone",
    "deliverable": "deliverable",
}


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


NEW_TASK_DURATION_MONTHS = 3


def add_calendar_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def plan_data_dir(root: Path, plan: str) -> Path:
    return root / "data" / plan


def load_items(data_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No JSON files found in {data_dir}")

    for path in paths:
        with path.open(encoding="utf-8") as handle:
            item = json.load(handle)
        if not isinstance(item, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        item["_source_file"] = path.name
        item["_mtime"] = path.stat().st_mtime
        items.append(item)

    validate_predecessors(items)
    return items


def validate_predecessors(items: list[dict[str, Any]]) -> None:
    ids = {item["id"] for item in items if "id" in item}
    for item in items:
        if "id" not in item:
            raise ValueError(f"{item.get('_source_file', '?')} is missing required field 'id'")
        for pred in item.get("predecessors", []):
            if pred not in ids:
                raise ValueError(
                    f"{item['id']} references unknown predecessor '{pred}' "
                    f"(from {item['_source_file']})"
                )


def strip_internal_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in INTERNAL_FIELDS}


def assign_rows(items: list[dict[str, Any]]) -> None:
    """Assign row indices to tasks and deliverables; milestones render on the timeline header."""
    rowable = [item for item in items if item.get("type") in ROW_ASSIGN_TYPES]
    if not rowable:
        return

    by_id = {item["id"]: item for item in items}
    memo: dict[str, int] = {}

    def task_depth(item_id: str, visiting: set[str]) -> int:
        if item_id in visiting:
            return 0
        if item_id in memo:
            return memo[item_id]
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


def item_end_date(item: dict[str, Any]) -> date:
    if item["type"] == "task":
        return parse_date(item["end"])
    return parse_date(item["date"])


def item_start_date(item: dict[str, Any]) -> date:
    if item["type"] == "task":
        return parse_date(item["start"])
    return parse_date(item["date"])


def find_item_file(data_dir: Path, item_id: str) -> Path | None:
    for path in sorted(data_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and data.get("id") == item_id:
            return path
    return None


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "item"


def next_file_number(data_dir: Path, item_type: str) -> int:
    prefix = TYPE_PREFIXES.get(item_type, item_type)
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)-", re.IGNORECASE)
    max_num = -1
    for path in data_dir.glob("*.json"):
        match = pattern.match(path.name)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num + 1


def make_filename(data_dir: Path, item_type: str, name: str) -> str:
    num = next_file_number(data_dir, item_type)
    slug = slugify(name)
    prefix = TYPE_PREFIXES[item_type]
    return f"{prefix}-{num:02d}-{slug}.json"


def write_item_file(path: Path, item: dict[str, Any]) -> None:
    payload = strip_internal_fields(item)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_item_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        item = json.load(handle)
    if not isinstance(item, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    item["_source_file"] = path.name
    item["_mtime"] = path.stat().st_mtime
    return item


def new_task_template(start: str, end: str, row: int | None = None) -> dict[str, Any]:
    temp_id = f"new-task-{int(time.time() * 1000)}"
    item: dict[str, Any] = {
        "id": temp_id,
        "type": "task",
        "name": "New task",
        "description": "",
        "start": start,
        "end": end,
        "predecessors": [],
        "status": "planned",
        "tags": [],
    }
    if row is not None:
        item["row"] = row
    return item


MILESTONE_SNAP_DAYS = 10


def snap_deliverable_to_milestone(
    item: dict[str, Any],
    items: list[dict[str, Any]],
    threshold_days: int = MILESTONE_SNAP_DAYS,
) -> bool:
    """Snap a deliverable date to the nearest milestone within ±threshold_days."""
    if item.get("type") != "deliverable" or "date" not in item:
        return False

    deliverable_date = parse_date(item["date"])
    best_date: date | None = None
    best_dist = threshold_days + 1

    for other in items:
        if other.get("type") != "milestone" or "date" not in other:
            continue
        ms_date = parse_date(other["date"])
        dist = abs((deliverable_date - ms_date).days)
        if dist <= threshold_days and dist < best_dist:
            best_dist = dist
            best_date = ms_date

    if best_date is None:
        return False
    item["date"] = format_date(best_date)
    return True


def earliest_allowed_start(item: dict[str, Any], by_id: dict[str, Any]) -> date | None:
    """Earliest date this item may start (day after latest predecessor ends)."""
    latest_end: date | None = None
    for pred_id in item.get("predecessors", []):
        pred = by_id.get(pred_id)
        if not pred:
            continue
        end = item_end_date(pred)
        if latest_end is None or end > latest_end:
            latest_end = end
    if latest_end is None:
        return None
    return latest_end + timedelta(days=1)


def push_item_to_earliest(item: dict[str, Any], by_id: dict[str, Any]) -> bool:
    """Shift item forward to satisfy predecessors. Returns True if dates changed."""
    required = earliest_allowed_start(item, by_id)
    if required is None:
        return False

    if item["type"] == "task":
        start = item_start_date(item)
        if start >= required:
            return False
        duration = max(1, (item_end_date(item) - start).days)
        item["start"] = format_date(required)
        item["end"] = format_date(required + timedelta(days=duration))
        return True

    point = item_start_date(item)
    if point >= required:
        return False
    item["date"] = format_date(required)
    return True


def clamp_to_predecessors(item: dict[str, Any], by_id: dict[str, Any]) -> bool:
    """Clamp an item so it does not start before its predecessors finish."""
    return push_item_to_earliest(item, by_id)


def apply_cascade(
    items: list[dict[str, Any]],
    changed_ids: set[str],
) -> set[str]:
    """Push successors forward when predecessor constraints are violated. Returns all changed ids."""
    by_id = {item["id"]: item for item in items}
    successors: dict[str, list[str]] = {item["id"]: [] for item in items}
    for item in items:
        for pred in item.get("predecessors", []):
            if pred in successors:
                successors[pred].append(item["id"])

    affected = set(changed_ids)
    queue = list(changed_ids)
    head = 0
    while head < len(queue):
        item_id = queue[head]
        head += 1
        for succ_id in successors.get(item_id, []):
            succ = by_id[succ_id]
            if push_item_to_earliest(succ, by_id):
                if succ_id not in affected:
                    affected.add(succ_id)
                    queue.append(succ_id)

    return affected


def clamp_task_to_predecessors(item: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Backward-compatible wrapper used by older callers."""
    by_id = {i["id"]: i for i in items}
    clamp_to_predecessors(item, by_id)
