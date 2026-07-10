"""Daily snapshot of wiki.db, meant to run on a schedule (e.g. a
PythonAnywhere Scheduled Task, or a cron entry on any other host) -- not
imported by the app itself.

Uses sqlite3's own online backup API rather than a plain file copy: copying
a live database's file bytes directly can capture it mid-write and produce a
corrupt snapshot, especially with WAL mode enabled (see models.get_db()),
where recent changes can still be sitting in a separate -wal file rather
than wiki.db itself. The backup() API reads through SQLite's own engine, so
it always gets a consistent, complete snapshot no matter what else is
happening to the live database at that moment.

This protects against a different class of problem than the persistent-disk
setup in the README: a bad edit, an app bug, or a corrupted file can still
lose data even on a host that never wipes its filesystem. It does not by
itself protect against the whole disk/account disappearing, since the
backups normally live right next to the database being backed up -- for
that, periodically copy the backups/ folder itself somewhere else (download
it via the host's file browser, email it, sync it to cloud storage, etc).
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone

import models

# Overridable via the BACKUP_DIR environment variable, same pattern as
# models.DB_PATH / images.UPLOAD_DIR.
BACKUP_DIR = os.environ.get("BACKUP_DIR", "backups")
KEEP_DAYS = 30


def backup_once():
    if not os.path.exists(models.DB_PATH):
        print(f"No database found at {models.DB_PATH!r} -- nothing to back up yet.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest_path = os.path.join(BACKUP_DIR, f"wiki-{stamp}.db")

    src_conn = sqlite3.connect(models.DB_PATH)
    dest_conn = sqlite3.connect(dest_path)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    print(f"Backed up {models.DB_PATH!r} -> {dest_path!r}")
    _prune_old_backups()


def _prune_old_backups():
    now = datetime.now(timezone.utc).timestamp()
    for name in os.listdir(BACKUP_DIR):
        if not (name.startswith("wiki-") and name.endswith(".db")):
            continue
        path = os.path.join(BACKUP_DIR, name)
        age_days = (now - os.path.getmtime(path)) / 86400
        if age_days > KEEP_DAYS:
            os.remove(path)
            print(f"Removed backup older than {KEEP_DAYS} days: {name}")


if __name__ == "__main__":
    # A scheduled task's log is the only place anyone will ever see this run
    # -- exit non-zero on failure so PythonAnywhere's Task tab visibly flags
    # a broken backup instead of it silently failing forever.
    try:
        backup_once()
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure here should exit non-zero
        print(f"Backup failed: {exc}")
        sys.exit(1)
