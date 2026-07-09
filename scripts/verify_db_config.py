"""
Verify database configuration from Django settings.
Run: python scripts/verify_db_config.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "employee_truck_control.settings")

import django
django.setup()

from django.conf import settings

db = settings.DATABASES["default"]
pool_enabled = os.environ.get("DB_POOL_ENABLED", "False")

print("=" * 60)
print("DATABASE CONFIGURATION VERIFICATION")
print("=" * 60)
print(f"  Engine:          {db['ENGINE']}")
print(f"  Name:            {db['NAME']}")
print(f"  User:            {db['USER']}")
print(f"  Host:            {db['HOST']}")
print(f"  Port:            {db['PORT']}")
print(f"  CONN_MAX_AGE:    {db.get('CONN_MAX_AGE')}")
print(f"  SSL Mode:        {db.get('OPTIONS', {}).get('sslmode', 'N/A')}")
print(f"  Pool Enabled:    {pool_enabled}")
print(f"  Pool Settings:   {db.get('POOL_SETTINGS', 'Not active')}")
print()
print("Available management commands:")
print("  python manage.py db_backup")
print("  python manage.py db_restore <backup_file>")
print("=" * 60)

# Check if PostgreSQL client tools are available
import shutil
pg_dump = shutil.which("pg_dump")
pg_restore = shutil.which("pg_restore")
print()
print("PostgreSQL client tools:")
print(f"  pg_dump:    {'Found' if pg_dump else 'NOT FOUND - install PostgreSQL client'}")
print(f"  pg_restore: {'Found' if pg_restore else 'NOT FOUND - install PostgreSQL client'}")
print("=" * 60)