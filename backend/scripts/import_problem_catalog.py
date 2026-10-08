"""Import a prepared external problem catalog into the configured database."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.db import SessionLocal
from app.services.catalog_import import import_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "catalog", type=Path, help="Path to the validated catalog JSON file"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            result = import_catalog(db, args.catalog)
        except Exception:
            db.rollback()
            raise
    print(
        f"Imported {result['imported']} problems; "
        f"{result['already_present']} were already present; "
        f"catalog total {result['catalog_total']}, "
        f"curriculum total {result['curriculum_total']}."
    )


if __name__ == "__main__":
    main()
