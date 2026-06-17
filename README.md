# Planning Tool

Generate a scrollable Gantt-style planning view from JSON files describing tasks, milestones, and deliverables.

## Quick start

### Static HTML export

```bash
python generate_plan.py data/aircraft-design -o output/aircraft-design.html -t "Aircraft Design"
```

Open `output/aircraft-design.html` in a browser.

### Interactive web editor

Install dependencies (first time only):

```bash
pip install -r requirements.txt
```

Start the local editor:

```bash
python -m app
```

Open [http://localhost:8000](http://localhost:8000). Options: `--port 8000`, `--plan aircraft-design`, `--host 127.0.0.1`.

## Dual workflow (web + Cursor)

Both the web app and `generate_plan.py` read the same JSON files under `data/<plan>/` (one file per item). The disk is the source of truth — there is no database.

1. **Edit in the browser** — drag task bars to move or resize (snaps to whole days, pushes dependent items forward), click any item to edit JSON in the side panel, right-click empty chart area to create a new task (3-month default duration).
2. **Edit in Cursor** — change any `data/aircraft-design/*.json` file directly; the web app polls every 3 seconds and reloads (or prompts if you have unsaved panel edits).
3. **Static export** — `python generate_plan.py` still produces a read-only HTML file using `templates/gantt.html`.

New tasks are saved immediately as `task-NN-slug.json`. Dragging a task earlier than its predecessors allows is clamped to the day after the latest predecessor ends.

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

**Milestones** render on the **timeline header** (diamond + label) with a **vertical line** spanning the full chart height. Tasks and deliverables occupy rows below.

To share a row, use the same `"row"`, `"group"`, or `"anchor"` on tasks/deliverables.

If items on the same row overlap in time, the row expands into **subrows** (stacked lanes with light divider lines).

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

> Create one JSON file per planning item for a Gantt chart tool. Follow the schema in `schema/planning-item.schema.json`. Use `type`: `task` (with `start` and `end`), `milestone` (with `date`), or `deliverable` (with `date`). Each item needs a unique `id`. Link items with `predecessors` (array of ids). Include rich metadata: `description`, `assignee`, `status`, `priority`, `tags`, `notes`. Dates as `YYYY-MM-DD`. Save files in `data/<project-name>/` with type-prefixed filenames like `task-01-flight-loads.json`, `milestone-00-kickoff.json`, or `deliverable-07-primary-structure-external-loft.json`.

## Chart behaviour

- **Tasks** — horizontal bars, width proportional to duration.
- **Milestones** — orange diamonds at a point in time.
- **Deliverables** — green circles at a point in time.
- **Dependencies** — straight diagonal arrows from predecessor end to successor start.
- **Tooltips** — hover any item to see all JSON fields.
- **Scrolling** — vertical scroll for rows; horizontal scroll for the timeline.
- **Zoom** — use **Ctrl + scroll** (or **⌘ + scroll** on Mac) over the chart to zoom toward the cursor; **+/−**, slider, and **Fit** in the header.

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
Aircraft_Planning/
  generate_plan.py         # JSON → static HTML (uses plan_logic)
  plan_logic.py            # Shared load, validate, assign_rows, cascade
  app/                     # Interactive web editor (python -m app)
  templates/
    gantt.html             # Read-only chart template
    gantt-editor.html      # Interactive editor page
  schema/                  # JSON schema for validation
  data/aircraft-design/    # Planning items (one JSON file each)
  output/                  # Generated static HTML
  requirements.txt         # fastapi, uvicorn, jsonschema
```

Static export uses Python 3.9+ stdlib only. The web editor requires `pip install -r requirements.txt`.
