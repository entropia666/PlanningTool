# Planning Tool

Generate a scrollable Gantt-style planning view from JSON files describing tasks, milestones, and deliverables.

## Quick start

```bash
python generate_plan.py data/example -o output/plan.html -t "My Project"
```

Open `output/plan.html` in a browser.

## Workflow

1. **Create JSON files** — one file per planning item in a folder (e.g. `data/my-project/`).
2. **Generate HTML** — run `generate_plan.py` pointing at that folder.
3. **View** — open the output HTML file; scroll vertically through rows and horizontally through time.

Use Cursor (or any LLM) to draft JSON files. Point it at `schema/planning-item.schema.json` and the examples in `data/example/`.

## JSON format

Each file is one object. Required fields depend on type:

| Field | Task | Milestone | Deliverable |
|-------|------|-----------|-------------|
| `id` | ✓ | ✓ | ✓ |
| `type` | `"task"` | `"milestone"` | `"deliverable"` |
| `name` | ✓ | ✓ | ✓ |
| `start`, `end` | ✓ (YYYY-MM-DD) | — | — |
| `date` | — | ✓ | ✓ |
| `predecessors` | optional array of `id`s | optional | optional |

Additional fields (`description`, `assignee`, `status`, `priority`, `tags`, `notes`, `color`, etc.) are shown in the hover tooltip. Any extra keys you add are also displayed.

**Tasks**, **milestones**, and **deliverables** each get their own row by default. To share a row with another item:

- Set the same `"row": 0` (or any index) on each item, or
- Give them the same `"group": "backend"` string (easier to read in JSON)
- Set `"anchor": "other-item-id"` to place on another item's row without assigning a row number

Optional `"row_label"` sets the left-column caption when several items share a row (defaults to names joined with ` · `).

If items on the same row overlap in time, they are stacked slightly within the row.

### Example task

```json
{
  "id": "design",
  "type": "task",
  "name": "System design",
  "description": "Architecture and wireframes.",
  "start": "2026-06-16",
  "end": "2026-07-04",
  "predecessors": ["req-spec"],
  "status": "planned",
  "assignee": "Bob"
}
```

### Example: parallel tasks on one row

```json
{
  "id": "frontend",
  "type": "task",
  "name": "Frontend build",
  "start": "2026-07-07",
  "end": "2026-08-01",
  "group": "implementation",
  "row_label": "Implementation"
}
```

```json
{
  "id": "backend",
  "type": "task",
  "name": "Backend build",
  "start": "2026-07-07",
  "end": "2026-08-15",
  "group": "implementation"
}
```

Both tasks appear on one row because they share `"group": "implementation"`.

### Example milestone

```json
{
  "id": "design-review",
  "type": "milestone",
  "name": "Design review",
  "date": "2026-07-04",
  "predecessors": ["design"]
}
```

### Example deliverable

```json
{
  "id": "mvp-release",
  "type": "deliverable",
  "name": "MVP release",
  "date": "2026-08-22",
  "predecessors": ["implementation"],
  "color": "#059669"
}
```

## Prompt for Cursor / LLM

Copy this when asking an LLM to create planning JSON files:

> Create one JSON file per planning item for a Gantt chart tool. Follow the schema in `schema/planning-item.schema.json`. Use `type`: `task` (with `start` and `end`), `milestone` (with `date`), or `deliverable` (with `date`). Each item needs a unique `id`. Link items with `predecessors` (array of ids). Include rich metadata: `description`, `assignee`, `status`, `priority`, `tags`, `notes`. Dates as `YYYY-MM-DD`. Save files in `data/<project-name>/` with descriptive filenames like `01-kickoff.json`.

## Chart behaviour

- **Tasks** — horizontal bars, width proportional to duration.
- **Milestones** — orange diamonds at a point in time.
- **Deliverables** — green circles at a point in time.
- **Dependencies** — curved arrows from predecessor end to successor start.
- **Tooltips** — hover any item to see all JSON fields.
- **Scrolling** — vertical scroll for rows; horizontal scroll for the timeline.

## CLI options

```
python generate_plan.py [data_dir] [-o OUTPUT] [-t TITLE] [--template PATH]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `data_dir` | `data/example` | Folder of `*.json` item files |
| `-o`, `--output` | `output/plan.html` | Generated HTML path |
| `-t`, `--title` | `Project Plan` | Browser title and header |
| `--template` | `templates/gantt.html` | HTML template |

## Project layout

```
PlanningTool/
  generate_plan.py       # JSON → HTML generator
  templates/gantt.html   # Self-contained chart template
  schema/                # JSON schema for LLM validation
  data/example/          # Sample planning items
  output/plan.html       # Generated view (after running script)
```

No external dependencies — Python 3.9+ standard library only.
