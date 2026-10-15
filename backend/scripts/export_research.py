"""Produce a restricted research CSV from a deployment shell."""

import argparse
import os
from pathlib import Path

from app.core.db import SessionLocal
from app.services.reporting import research_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_id", type=int)
    parser.add_argument("assignment_id", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    publication_key = os.environ.get("RESEARCH_PUBLICATION_KEY", "").strip()
    if not publication_key:
        parser.error("RESEARCH_PUBLICATION_KEY must be set")

    with SessionLocal() as db:
        content = research_csv(db, args.course_id, args.assignment_id, publication_key)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
        output.write(content)


if __name__ == "__main__":
    main()
