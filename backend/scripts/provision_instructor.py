"""Create the first verified instructor account from an operator shell."""

import argparse
from datetime import UTC, datetime
from getpass import getpass

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import User, UserRole
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("email")
    args = parser.parse_args()
    email = args.email.strip().lower()
    password = getpass("Initial password: ")
    if len(password) < 8:
        parser.error("password must contain at least 8 characters")
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            parser.error("an account with that email already exists")
        db.add(
            User(
                name=args.name.strip(),
                email=email,
                password_hash=hash_password(password),
                role=UserRole.PROFESSOR,
                email_verified_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()
    print(f"Created instructor {email}.")


if __name__ == "__main__":
    main()
