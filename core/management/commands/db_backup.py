"""
Management command: db_backup

Creates a compressed SQL backup of the database using pg_dump (PostgreSQL)
or sqlite3 (SQLite), saves it to the BACKUP_DIR with a timestamped filename,
and optionally prunes backups older than BACKUP_RETENTION_DAYS.

Usage:
    python manage.py db_backup
    python manage.py db_backup --output /custom/path/backup.sql.gz
    python manage.py db_backup --no-prune
"""
import gzip
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

# Default: store backups in a 'backups' folder alongside the project
DEFAULT_BACKUP_DIR = settings.BASE_DIR / "backups"
DEFAULT_RETENTION_DAYS = 30  # keep 30 days of backups


class Command(BaseCommand):
    help = "Create a compressed SQL backup of the current database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", "-o",
            type=str,
            default=None,
            help="Full output path for the backup file (default: backups/<dbname>_<timestamp>.sql.gz).",
        )
        parser.add_argument(
            "--no-prune",
            action="store_true",
            help="Skip pruning of old backups.",
        )

    def handle(self, *args, **options):
        db_engine = settings.DATABASES["default"]["ENGINE"]
        output_path = options["output"]
        no_prune = options["no_prune"]

        if "sqlite" in db_engine:
            self._backup_sqlite(output_path)
        elif "postgresql" in db_engine:
            self._backup_postgres(output_path)
        else:
            raise CommandError(f"Unsupported database engine: {db_engine}")

        if not no_prune:
            self._prune_old_backups()

    # ------------------------------------------------------------------
    # SQLite backup
    # ------------------------------------------------------------------
    def _backup_sqlite(self, output_path: str | None):
        db_name = settings.DATABASES["default"]["NAME"]
        db_path = Path(db_name)

        if not db_path.exists():
            raise CommandError(f"SQLite database not found at {db_path}")

        backup_path = self._resolve_output_path(output_path, db_path.stem)
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"Backing up SQLite database: {db_path}")
        self.stdout.write(f"Output: {backup_path}")

        try:
            # Use .backup command via sqlite3 CLI for a safe online backup
            result = subprocess.run(
                ["sqlite3", str(db_path), f".backup {backup_path}"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise CommandError(f"sqlite3 backup failed: {result.stderr}")

            # Compress the backup
            compressed = backup_path.with_suffix(".sql.gz")
            with open(backup_path, "rb") as f_in:
                with gzip.open(compressed, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed temp file
            backup_path.unlink()

            size_mb = compressed.stat().st_size / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f"Backup created: {compressed} ({size_mb:.2f} MB)"
            ))
        except subprocess.TimeoutExpired:
            raise CommandError("sqlite3 backup timed out after 120 seconds.")
        except FileNotFoundError:
            raise CommandError(
                "sqlite3 CLI not found. Install it or use a different backup method."
            )

    # ------------------------------------------------------------------
    # PostgreSQL backup
    # ------------------------------------------------------------------
    def _backup_postgres(self, output_path: str | None):
        db_conf = settings.DATABASES["default"]
        db_name = db_conf["NAME"]
        db_user = db_conf["USER"]
        db_host = db_conf["HOST"]
        db_port = db_conf["PORT"]

        backup_path = self._resolve_output_path(output_path, db_name)
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"Backing up PostgreSQL database: {db_name}")
        self.stdout.write(f"Output: {backup_path}")

        # Build pg_dump command
        env = os.environ.copy()
        if db_conf.get("PASSWORD"):
            env["PGPASSWORD"] = db_conf["PASSWORD"]

        cmd = [
            "pg_dump",
            "--dbname", db_name,
            "--host", db_host,
            "--port", str(db_port),
            "--username", db_user,
            "--no-password",          # use PGPASSWORD env var
            "--format", "custom",     # custom format allows parallel restore
            "--compress", "9",        # max compression
            "--verbose",
        ]

        try:
            with open(backup_path, "wb") as f_out:
                result = subprocess.run(
                    cmd,
                    stdout=f_out,
                    stderr=subprocess.PIPE,
                    env=env,
                    timeout=300,  # 5 minutes
                )

            if result.returncode != 0:
                # pg_dump writes progress to stderr, so only show if it actually failed
                error_msg = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
                raise CommandError(f"pg_dump failed (exit {result.returncode}): {error_msg[:500]}")

            size_mb = backup_path.stat().st_size / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f"Backup created: {backup_path} ({size_mb:.2f} MB)"
            ))
        except subprocess.TimeoutExpired:
            raise CommandError("pg_dump timed out after 300 seconds.")
        except FileNotFoundError:
            raise CommandError(
                "pg_dump not found. Install PostgreSQL client tools and ensure pg_dump is on PATH."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_output_path(self, output_path: str | None, db_name: str) -> Path:
        if output_path:
            return Path(output_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{db_name}_{timestamp}.dump"
        return DEFAULT_BACKUP_DIR / filename

    def _prune_old_backups(self):
        """Remove backup files older than DEFAULT_RETENTION_DAYS."""
        if not DEFAULT_BACKUP_DIR.exists():
            return

        cutoff = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS)
        pruned = 0

        for f in DEFAULT_BACKUP_DIR.iterdir():
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    pruned += 1

        if pruned:
            self.stdout.write(f"Pruned {pruned} old backup(s) (retention: {DEFAULT_RETENTION_DAYS} days).")
        else:
            self.stdout.write("No old backups to prune.")
