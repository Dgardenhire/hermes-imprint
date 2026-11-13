"""Bringing data over from the plugin's earlier name, once per data folder.

Before Nov 12, 2026 the plugin was called Imprint and kept its data in ``<HERMES_HOME>/plugin-data/imprint/`` with the
database ``imprint.db``. The first time Letterpress opens its own folder (``plugin-data/letterpress/``), ``carry_over``
copies that data in, so sources, brands, made pieces and settings are all there.

The rules:
- Copy, never move. Nothing in the earlier folder is changed or deleted.
- Never overwrite. If the new folder already has a database, nothing happens; a file already in the new folder is kept.
- Only this plugin's data. Another plugin in the catalog uses the earlier name too, so the earlier folder is copied only
  when its ``imprint.db`` has this plugin's own tables.
- Whole or not at all. Each database is copied with SQLite's backup (a consistent copy even while the earlier plugin is
  open) into a scratch file, and the new database appears only when that copy is complete, by a link that fails rather
  than replace a database another process placed first. The marker ``.carried-over`` records that it happened, so
  "Forget everything" (which keeps the marker) does not bring the earlier data back.
- Never in the way. Any failure removes the files this copy made, leaves the earlier folder as it was, and the plugin
  starts with an empty folder; the next start tries again."""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path

EARLIER_DB = "imprint.db"
NEW_DB = "letterpress.db"
MARKER = ".carried-over"
# Tables every database this plugin ever wrote has; another plugin's file under the earlier name will not have them all.
OWN_TABLES = {"sources", "passages", "outputs", "renders", "jobs", "settings"}

_done: set = set()
_lock = threading.Lock()


def _is_ours(db: Path) -> bool:
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            c.close()
    except sqlite3.Error:
        return False
    return OWN_TABLES <= names


def _place(tmp: Path, target: Path) -> bool:
    """Put ``tmp`` at ``target`` only if nothing is there. Returns whether it was placed; ``tmp`` is gone either way."""
    try:
        os.link(tmp, target)  # fails if target exists, so a file another process placed first is never replaced
        placed = True
    except FileExistsError:
        placed = False
    except OSError:  # a file system without hard links
        placed = not target.exists()
        if placed:
            os.replace(tmp, target)
    try:
        tmp.unlink()
    except OSError:
        pass
    return placed


def _copy_db(src: Path, target: Path) -> bool:
    tmp = target.with_name(f"{target.name}.carrying-{uuid.uuid4().hex[:8]}")
    try:
        s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        try:
            d = sqlite3.connect(str(tmp))
            try:
                s.backup(d)
            finally:
                d.close()
        finally:
            s.close()
        return _place(tmp, target)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _skip(rel: Path, name: str) -> bool:
    """Database files are copied with SQLite's backup, not as bytes; the marker is never copied."""
    return name == MARKER or name.startswith(EARLIER_DB) or name.startswith(NEW_DB) or ".carrying-" in name


def carry_over(new_dir: Path, old_dir: Path) -> str:
    """Copy ``old_dir`` into ``new_dir`` once. Returns ``none`` (nothing of this plugin's to bring), ``skipped`` (the new
    folder already has a database or was filled before), ``carried``, or ``failed`` (nothing changed in ``old_dir``)."""
    new_dir, old_dir = Path(new_dir), Path(old_dir)
    old_db = old_dir / EARLIER_DB
    if not old_db.is_file() or not _is_ours(old_db):
        return "none"
    if (new_dir / NEW_DB).exists() or (new_dir / MARKER).exists():
        return "skipped"
    placed: list = []
    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        dbs = []
        for root, dirs, files in os.walk(old_dir):
            here = Path(root)
            rel = here.relative_to(old_dir)
            for name in files:
                if name == EARLIER_DB:
                    if rel != Path(".") and _is_ours(here / name):
                        dbs.append(rel)  # the sample notebook's own database
                    continue
                if _skip(rel, name):
                    continue
                target = new_dir / rel / name
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(f"{name}.carrying-{uuid.uuid4().hex[:8]}")
                shutil.copy2(here / name, tmp)
                if _place(tmp, target):
                    placed.append(target)
        for rel in dbs:
            (new_dir / rel).mkdir(parents=True, exist_ok=True)
            if _copy_db(old_dir / rel / EARLIER_DB, new_dir / rel / NEW_DB):
                placed.append(new_dir / rel / NEW_DB)
        # the main database last, so a half-finished carry-over never looks like a finished folder
        if not _copy_db(old_db, new_dir / NEW_DB):
            return "skipped"  # another process finished first
        try:
            (new_dir / MARKER).write_text(f"copied from {old_dir.name}; the original was left in place\n", "utf-8")
        except OSError:
            pass
        return "carried"
    except Exception:  # noqa: BLE001 - never block the plugin over this
        for p in placed:  # only files this call created in the new folder
            try:
                p.unlink()
            except OSError:
                pass
        return "failed"


def carry_over_once(new_dir: Path, old_dir: Path) -> str:
    """``carry_over``, at most once per folder in this process."""
    key = str(new_dir)
    with _lock:
        if key in _done:
            return "skipped"
        result = carry_over(new_dir, old_dir)
        _done.add(key)
        return result
