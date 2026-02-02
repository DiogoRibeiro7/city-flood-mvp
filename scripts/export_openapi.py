from __future__ import annotations

import os
import pathlib

import yaml

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/floodmvp"

from floodmvp.api.main import app  # noqa: E402


def main() -> None:
    out_path = pathlib.Path("docs/openapi/public.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, sort_keys=False)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
