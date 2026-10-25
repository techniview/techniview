#!/usr/bin/env python3
"""Exercise the production backup script with disposable MySQL and restic data."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args, env=None, input=None, check=True):
    result = subprocess.run(
        args, env=env, input=input, text=True, capture_output=True, check=False
    )
    if check and result.returncode:
        raise RuntimeError(
            f"Command {args[0]!r} failed with exit status {result.returncode}:\n"
            f"{result.stderr or result.stdout}"
        )
    return result


def main():
    for command in ("docker", "restic"):
        if not shutil.which(command):
            raise SystemExit(f"{command} is required")
    with tempfile.TemporaryDirectory(prefix="techniview-backup-test-") as directory:
        temporary = Path(directory)
        secret = temporary / "mysql_password"
        secret.write_text("test-only-password\n")
        secret.chmod(0o600)
        root_secret = temporary / "mysql_root_password"
        root_secret.write_text(f"{uuid.uuid4().hex}\n")
        root_secret.chmod(0o600)
        env = {
            **{
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("RESTIC_", "COMPOSE_"))
            },
            "IMAGE_NAMESPACE": "test",
            "IMAGE_TAG": "test",
            "PUBLIC_HOST": "test.invalid",
            "MYSQL_USER": "backup_test",
            "MYSQL_DB": "backup_test",
            "RUNNER_PRIVATE_HOST": "127.0.0.1",
            "EMAIL_FROM": "test@test.invalid",
            "SECRET_DIR": str(temporary),
            "RESTIC_REPOSITORY": str(temporary / "repository"),
            "RESTIC_PASSWORD": "test-only-restic-password",
            "RESTIC_CACHE_DIR": str(temporary / "cache"),
            "TECHNIVIEW_APP_ENV_FILE": "/dev/null",
        }
        production = json.loads(
            run(
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                str(ROOT / "compose.production.yml"),
                "config",
                "--format",
                "json",
                env=env,
            ).stdout
        )
        healthcheck = production["services"]["mysql"]["healthcheck"]
        compose_file = ROOT / "scripts/tests/backup-mysql-compose.yml"
        env["TEST_MYSQL_IMAGE"] = production["services"]["mysql"]["image"]
        env["TEST_MYSQL_ROOT_PASSWORD_FILE"] = str(root_secret)
        env["TEST_MYSQL_PASSWORD_FILE"] = str(secret)
        env["TECHNIVIEW_COMPOSE_FILE"] = str(compose_file)
        compose = [
            "docker",
            "compose",
            "-p",
            f"techniview-backup-test-{uuid.uuid4().hex[:12]}",
            "--env-file",
            "/dev/null",
            "-f",
            str(compose_file),
        ]
        test_configuration = json.loads(
            run(*compose, "config", "--format", "json", env=env).stdout
        )
        if test_configuration["services"]["mysql"]["healthcheck"] != healthcheck:
            raise AssertionError(
                "Backup test must use the production MySQL healthcheck"
            )

        def sql(statement):
            return run(
                *compose,
                "exec",
                "-T",
                "mysql",
                "sh",
                "-c",
                'MYSQL_PWD=$(cat "$MYSQL_PASSWORD_FILE"); export MYSQL_PWD; '
                'exec mysql -u "$MYSQL_USER" "$MYSQL_DATABASE" '
                "--batch --skip-column-names",
                input=statement,
                env=env,
            ).stdout.strip()

        try:
            run(*compose, "up", "-d", env=env)
            container = run(*compose, "ps", "-q", "mysql", env=env).stdout.strip()
            for _ in range(90):
                health = run(
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    container,
                ).stdout.strip()
                if health == "healthy":
                    break
                time.sleep(1)
            else:
                raise AssertionError(
                    "Disposable MySQL failed its production healthcheck"
                )
            sql(
                "CREATE TABLE marker (id INT PRIMARY KEY, value VARCHAR(80)); "
                "INSERT INTO marker VALUES (1, 'restore verified'); "
                "CREATE PROCEDURE marker_proc() SELECT 'routine verified';"
            )
            run("restic", "init", env=env)
            run(str(ROOT / "scripts/backup-mysql.sh"), env=env)
            snapshots = json.loads(run("restic", "snapshots", "--json", env=env).stdout)
            assert len(snapshots) == 1
            dump = run("restic", "dump", "latest", "/techniview.sql", env=env).stdout
            sql("DROP TABLE marker; DROP PROCEDURE marker_proc;")
            sql(dump)
            assert sql("SELECT value FROM marker WHERE id=1;") == "restore verified"
            assert sql("CALL marker_proc();") == "routine verified"
            secret.write_text("incorrect-password\n")
            failed = run(str(ROOT / "scripts/backup-mysql.sh"), env=env, check=False)
            assert failed.returncode != 0, "Invalid credentials must fail backup"
            health_command = production["services"]["mysql"]["healthcheck"]["test"][
                1
            ].replace("$$", "$")
            assert (
                run(
                    *compose,
                    "exec",
                    "-T",
                    "mysql",
                    "sh",
                    "-c",
                    health_command,
                    env=env,
                    check=False,
                ).returncode
                != 0
            )
            # A producer can emit a valid-looking prefix before failing.
            failed = run(
                "restic",
                "backup",
                "--stdin-filename",
                "partial.sql",
                "--stdin-from-command",
                "--",
                "sh",
                "-c",
                "printf 'partial dump'; exit 1",
                env=env,
                check=False,
            )
            assert failed.returncode != 0
            after = json.loads(run("restic", "snapshots", "--json", env=env).stdout)
            assert [item["id"] for item in after] == [item["id"] for item in snapshots]
            print(
                "PASS: authenticated healthcheck, backup/restore, "
                "invalid password, partial dump rejection"
            )
        finally:
            run(*compose, "down", "--volumes", env=env)


if __name__ == "__main__":
    main()
