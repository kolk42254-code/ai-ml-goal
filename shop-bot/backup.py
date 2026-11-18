"""Back up the shop: a safe copy of shop.db (orders, items, shop details) plus the item photos,
in one zip file in the backups/ folder. Keeps the newest 14 backups and deletes older ones.
It is safe to run while customers are ordering.

Run by hand:     python backup.py
Every night:     see deploy/DEPLOY.md (step 7)
Restore:         see deploy/DEPLOY.md ("Bring back a backup")"""
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

import config

BACKUP_DIR = config.BASE_DIR / "backups"
KEEP = 14


def make_backup(backup_dir=BACKUP_DIR, keep=KEEP):
    """Write one backup zip and return its path. Only the newest `keep` backups are kept."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(exist_ok=True)
    backup_dir.chmod(0o700)                                   # backups hold customers' names and phone numbers
    stamp = datetime.now(config.SHOP_TIMEZONE).strftime("%Y-%m-%d_%H%M%S_%f")
    target = backup_dir / f"shop-backup-{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "shop.db"
        if Path(config.DATABASE_FILE).exists():
            with closing(sqlite3.connect(config.DATABASE_FILE)) as source, closing(sqlite3.connect(copy)) as dest:
                source.backup(dest)                           # a complete, consistent copy, even mid-order
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            if copy.exists():
                archive.write(copy, "shop.db")
            uploads = Path(config.UPLOADS_DIR)
            if uploads.is_dir():
                for photo in sorted(uploads.iterdir()):
                    if photo.is_file():
                        archive.write(photo, f"uploads/{photo.name}")
    target.chmod(0o600)
    for old in sorted(backup_dir.glob("shop-backup-*.zip"))[:-keep]:     # names sort oldest first
        old.unlink()
    return target


if __name__ == "__main__":
    print(f"Backup saved: {make_backup()}")
