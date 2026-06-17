"""Run with: python -m app [--port PORT] [--plan PLAN]"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Gantt planning editor")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--plan",
        default="aircraft-design",
        help="Default plan folder under data/ (default: aircraft-design)",
    )
    args = parser.parse_args()

    from app.main import create_app

    app = create_app(default_plan=args.plan)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
