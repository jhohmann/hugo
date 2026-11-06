"""Local entry point: load .env, migrate, then start the development server."""

import argparse
import logging

from app.config import PROJECT_ROOT, load_environment
from app.migrate import run_migrations


def main() -> int:
    parser = argparse.ArgumentParser(description="Hugo lokal starten")
    parser.add_argument("--env-file")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    load_environment(args.env_file)
    logging.basicConfig(level=logging.INFO)
    if run_migrations()["status"] != "ok":
        return 1
    import uvicorn
    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=args.port,
        reload=not args.no_reload, reload_dirs=[str(PROJECT_ROOT / "backend" / "app")],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
