"""
Management command: db_restore

Restores a database from a backup file created by db_backup.
Supports PostgreSQL (pg_restore) and SQLite (sqlite3).

Usage:
    python manage.py db_restore backups/employee_truck_control_20260101_120000.dump
    python manage.py db_restore backups/employee_truck_control_20260101_120000.sql.gz
    python manage.py db_restore --list backups/employee_truck_control_20260101_120000.dump
"""
import gzip
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Restore the database from a backup file created by db_backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_file",
            type=str,
            help="Path to the backup file (.dump for PostgreSQL, .sql.gz for SQLite).",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List the contents of a PostgreSQL custom-format dump without restoring.",
        )

    def handle(self, *args, **options):
        backup_path = Path(options["backup_file"])
        list_only = options["list"]

        if not backup_path.exists():
            raise CommandError(f"Backup file not found: {backup_path}")

        db_engine = settings.DATABASES["default"]["ENGINE"]

        if "sqlite" in db_engine:
            if list_only:
                self.stdout.write("--list is not supported for SQLite backups.")
                return
            self._restore_sqlite(backup_path)
        elif "postgresql" in db_engine:
            self._restore_postgres(backup_path, list_only)
        else:
            raise CommandError(f"Unsupported database engine: {db_engine}")

    # ------------------------------------------------------------------
    # SQLite restore
    # ------------------------------------------------------------------
    def _restore_sqlite(self, backup_path: Path):
        db_name = settings.DATABASES["default"]["NAME"]
        db_path = Path(db_name)

        self.stdout.write(f"Restoring SQLite database: {db_path}")
        self.stdout.write(f"From backup: {backup_path}")

        # Confirm with the user
        answer = input(
            f"This will OVERWRITE the current database at {db_path}. "
            f"Are you sure? (yes/no): "
        )
        if answer.lower() not in ("yes", "y"):
            self.stdout.write("Restore cancelled.")
            return

        # Decompress if gzipped
        if backup_path.suffix == ".gz":
            self.stdout.write("Decompressing backup file...")
            with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
                with gzip.open(backup_path, "rb") as f_in:
                    shutil.copyfileobj(f_in, tmp)
                decompressed = Path(tmp.name)
        else:
            decompressed = backup_path

        try:
            # Close current connection and restore
            result = subprocess.run(
                ["sqlite3", str(db_path), f".read {decompressed}"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                raise CommandError(f"SQLite restore failed: {result.stderr}")

            self.stdout.write(self.style.SUCCESS("Database restored successfully."))
        except subprocess.TimeoutExpired:
            raise CommandError("SQLite restore timed out after 300 seconds.")
        except FileNotFoundError:
            raise CommandError(
                "sqlite3 CLI not found. Install it or use a different restore method."
            )
        finally:
            if backup_path.suffix == ".gz" and decompressed.exists():
                decompressed.unlink()

    # ------------------------------------------------------------------
    # PostgreSQL restore
    # ------------------------------------------------------------------
    def _restore_postgres(self, backup_path: Path, list_only: bool):
        db_conf = settings.DATABASES["default"]
        db_name = db_conf["NAME"]
        db_user = db_conf["USER"]
        db_host = db_conf["HOST"]
        db_port = db_conf["PORT"]

        env = os.environ.copy()
        if db_conf.get("PASSWORD"):
            env["PGPASSWORD"] = db_conf["PASSWORD"]

        if list_only:
            cmd = [
                "pg_restore",
                "--dbname", db_name,
                "--host", db_host,
                "--port", str(db_port),
                "--username", db_user,
                "--no-password",
                "--list",
                str(backup_path),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
                if result.returncode != 0:
                    raise CommandError(f"pg_restore --list failed: {result.stderr}")
                self.stdout.write(result.stdout)
            except subprocess.TimeoutExpired:
                raise CommandError("pg_restore --list timed out.")
            except FileNotFoundError:
                raise CommandError(
                    "pg_restore not found. Install PostgreSQL client tools."
                )
            return

        self.stdout.write(f"Restoring PostgreSQL database: {db_name}")
        self.stdout.write(f"From backup: {backup_path}")

        # Confirm with the user
        answer = input(
            f"This will OVERWRITE the current database '{db_name}'. "
            f"Are you sure? (yes/no): "
        )
        if answer.lower() not in ("yes", "y"):
            self.stdout.write("Restore cancelled.")
            return

        # Build pg_restore command
        cmd = [
            "pg_restore",
            "--dbname", db_name,
            "--host", db_host,
            "--port", str(db_port),
            "--username", db_user,
            "--no-password",
            "--clean",              # drop existing objects before recreating
            "--if-exists",          # avoid errors if objects don't exist
            "--no-owner",           # skip ownership restoration
            "--verbose",
            str(backup_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=600,  # 10 minutes for large restores
            )

            if result.returncode != 0:
                error_msg = result.stderr[:1000] if result.stderr else ""
                raise CommandError(f"pg_restore failed (exit {result.returncode}): {error_msg}")

            self.stdout.write(self.style.SUCCESS("Database restored successfully."))
        except subprocess.TimeoutExpired:
            raise CommandError("pg_restore timed out after 600 seconds.")
        except FileNotFoundError:
            raise CommandError(
                "pg_restore not found. Install PostgreSQL client tools and ensure pg_restore is on PATH."
            )
