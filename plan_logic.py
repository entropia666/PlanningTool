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

_ROOT = Path(__file__).resolve().parent
DISCIPLINES_PATH = _ROOT / "schema" / "disciplines.json"
PLANNING_SCHEMA_PATH = _ROOT / "schema" / "planning-item.schema.json"


def load_discipline_defs(path: Path | None = None) -> list[dict[str, str]]:
    """Load ordered discipline definitions from schema/disciplines.json."""
    source = path or DISCIPLINES_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{source} must be a non-empty JSON array")

    defs: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError(f"Each discipline entry must be an object in {source}")
        discipline_id = entry.get("id")
        label = entry.get("label")
        if not isinstance(discipline_id, str) or not discipline_id:
            raise ValueError(f"Discipline entry missing string 'id' in {source}")
        if not isinstance(label, str) or not label:
            raise ValueError(f"Discipline '{discipline_id}' missing string 'label' in {source}")
        if discipline_id in seen:
            raise ValueError(f"Duplicate discipline id '{discipline_id}' in {source}")
        seen.add(discipline_id)
        defs.append({"id": discipline_id, "label": label})
    return defs


DISCIPLINE_DEFS = load_discipline_defs()
DISCIPLINES: list[str] = [entry["id"] for entry in DISCIPLINE_DEFS]
DISCIPLINE_LABELS: dict[str, str] = {
    entry["id"]: entry["label"] for entry in DISCIPLINE_DEFS
}


def disciplines_json() -> str:
    """JSON array of discipline definitions for injection into HTML templates."""
    return json.dumps(DISCIPLINE_DEFS, ensure_ascii=False)


def render_gantt_template(template: str, **replacements: str) -> str:
    """Replace template placeholders, including disciplines from the shared config."""
    html = template.replace("{{DISCIPLINES_JSON}}", disciplines_json())
    for key, value in replacements.items():
        html = html.replace(f"{{{{{key}}}}}", value)
    return html


def load_planning_schema(path: Path | None = None) -> dict[str, Any]:
    """Load planning-item schema with discipline enum synced from disciplines.json."""
    schema = json.loads((path or PLANNING_SCHEMA_PATH).read_text(encoding="utf-8"))
    discipline = schema.get("properties", {}).get("discipline")
    if isinstance(discipline, dict):
        discipline["enum"] = list(DISCIPLINES)
    return schema

ITEM_DISCIPLINE_BY_ID: dict[str, str] = {
    "flaps-loft-kinematics": "aerodynamic-design",
    "fairings-loft-design": "aerodynamic-design",
    "f100-aero-shape-design": "aerodynamic-design",
    "f100-aero-shape-improvements": "aerodynamic-design",
    "primary-control-surfaces-shape-design": "aerodynamic-design",
    "control-surfaces-final-sizing": "handling-qualities",
    "primary-structure-external-loft": "aerodynamic-design",
    "components-external-loft": "aerodynamic-design",
    "flaps-control-surfaces-kinematics": "aerodynamic-design",
    "planform-freeze": "aerodynamic-design",
    "wind-tunnel-model-test-analysis": "aerodynamic-data",
    "gather-cl415-engineering-info": "aerodynamic-data",
    "CL 415 Aero data creation": "aerodynamic-data",
    "wind-tunnel-validated-aero-data": "aerodynamic-data",
    "reverse-engineer-cl415": "aerodynamic-data",
    "aero-data-for-hq-perform-concept": "aerodynamic-data",
    "aero-data-for-hq-perform-improved": "aerodynamic-data",
    "aero-data-for-hq-perfo-loads": "aerodynamic-data",
    "flight-loads": "flight-loads",
    "components-loads": "flight-loads",
    "design-loads-methodology-flight": "flight-loads",
    "preliminary-flight-loads-primary-structure": "flight-loads",
    "primary-structure-external-loads": "flight-loads",
    "components-external-loads": "flight-loads",
    "ground-water-loads": "ground-loads",
    "design-loads-methodology-ground": "ground-loads",
    "preliminary-ground-loads": "ground-loads",
    "design-loads-methodology-water": "water-loads",
    "preliminary-water-loads": "water-loads",
    "validate-cl415-performance": "performance",
    "mission-performance": "performance",
    "propulsive-performance": "performance",
    "evaluate-performance": "performance",
    "ground-water-performance-evaluation-methodology": "performance",
    "evaluate-f100-performance": "performance",
    "handling-qualities-actuator": "handling-qualities",
    "validate-cl415-handling-qualities": "handling-qualities",
    "handling-qualities-compliance": "handling-qualities",
    "actuator-max-capability": "handling-qualities",
    "flight-control-law-architecture-drivers": "handling-qualities",
    "evaluate-handling-qualities": "handling-qualities",
    "in-flight-handling-qualities-methodology": "handling-qualities",
    "ground-handling-qualities-methodology": "handling-qualities",
    "water-handling-qualities-methodology": "handling-qualities",
    "evaluate-f100-handling-qualities-concept": "handling-qualities",
    "evaluate-f100-handling-qualities-pre-freeze": "handling-qualities",
    "tails-final-sizing": "handling-qualities",
    "mass-allowance": "mass-and-cog",
    "mass-cog-envelope": "mass-and-cog",
    "mass-and-cog-estimate": "mass-and-cog",
    "planform-for-concept-review": "overall-aircraft-design",
    "planform-freeze-preliminary-design": "overall-aircraft-design",
}

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


def discipline_index(discipline: str) -> int:
    try:
        return DISCIPLINES.index(discipline)
    except ValueError:
        return 0


def infer_discipline(item: dict[str, Any]) -> str:
    if item.get("discipline") in DISCIPLINES:
        return str(item["discipline"])

    item_id = item.get("id", "")
    if item_id in ITEM_DISCIPLINE_BY_ID:
        return ITEM_DISCIPLINE_BY_ID[item_id]

    row = item.get("row")
    if isinstance(row, int) and 0 <= row < len(DISCIPLINES):
        return DISCIPLINES[row]

    haystack = " ".join(
        [
            item_id,
            str(item.get("name", "")),
            str(item.get("group", "")),
            " ".join(str(t) for t in item.get("tags", [])),
        ]
    ).lower()

    rules: list[tuple[tuple[str, ...], str]] = [
        (("mass", "cog", "weight"), "mass-and-cog"),
        (("handling", "actuator", "flight-control"), "handling-qualities"),
        (("performance", "propulsion", "mission-performance"), "performance"),
        (("aeroelastic",), "aeroelastics"),
        (("water load", "water-load"), "water-loads"),
        (("ground load", "ground-load"), "ground-loads"),
        (("flight load", "loads", "load"), "flight-loads"),
        (("wind-tunnel", "aero data", "reverse-engineer", "reference-aircraft"), "aerodynamic-data"),
        (("loft", "kinematic", "planform", "fairing", "aero shape"), "aerodynamic-design"),
    ]
    for keywords, discipline in rules:
        if any(keyword in haystack for keyword in keywords):
            return discipline

    return "aerodynamic-design"


def assign_rows(items: list[dict[str, Any]]) -> None:
    """Map each task/deliverable to a fixed discipline row."""
    for item in items:
        if item.get("type") not in ROW_ASSIGN_TYPES:
            continue

        if item.get("discipline") not in DISCIPLINES:
            item["discipline"] = infer_discipline(item)

        item["row"] = discipline_index(item["discipline"])


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


def new_task_template(
    start: str,
    end: str,
    discipline: str | None = None,
    row: int | None = None,
) -> dict[str, Any]:
    temp_id = f"new-task-{int(time.time() * 1000)}"
    if discipline not in DISCIPLINES:
        if row is not None and 0 <= row < len(DISCIPLINES):
            discipline = DISCIPLINES[row]
        else:
            discipline = DISCIPLINES[0]
    item: dict[str, Any] = {
        "id": temp_id,
        "type": "task",
        "name": "New task",
        "description": "",
        "start": start,
        "end": end,
        "discipline": discipline,
        "row": discipline_index(discipline),
        "predecessors": [],
        "status": "planned",
        "tags": [],
    }
    return item


def new_deliverable_template(
    date: str,
    discipline: str | None = None,
    row: int | None = None,
) -> dict[str, Any]:
    temp_id = f"new-deliverable-{int(time.time() * 1000)}"
    if discipline not in DISCIPLINES:
        if row is not None and 0 <= row < len(DISCIPLINES):
            discipline = DISCIPLINES[row]
        else:
            discipline = DISCIPLINES[0]
    item: dict[str, Any] = {
        "id": temp_id,
        "type": "deliverable",
        "name": "New deliverable",
        "description": "",
        "date": date,
        "discipline": discipline,
        "row": discipline_index(discipline),
        "predecessors": [],
        "status": "planned",
        "tags": [],
    }
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
