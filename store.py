"""Letterpress's index on disk: one SQLite database plus the files it points at.

Folder: ``<HERMES_HOME>/plugin-data/letterpress/`` (``runtime.data_dir``).

- ``letterpress.db``            sources, passages, outputs, renders, jobs, chats, usage, looks, settings
- ``sources/<sha256>.<ext>`` original files, kept so text can be read again
- ``kits/<kit-id>/``        ``kit.json``, ``logo.*``, ``fonts/*.ttf`` (see kits.py)
- ``outputs/<output-id>/``  content JSON and every exported file

Inside Hermes the database opens through ``plugins.plugin_storage.plugin_db`` (WAL, shared helper);
in tests through ``sqlite3`` in the temporary folder. One lock serializes writes from job threads.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from . import carryover, runtime
except ImportError:  # loaded loose
    import carryover  # type: ignore
    import runtime  # type: ignore

DB_NAME = "letterpress.db"
_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None
_conn_dir: Optional[str] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, sha256 TEXT, kind TEXT, title TEXT, origin TEXT, ext TEXT,
  bytes INTEGER DEFAULT 0, chars INTEGER DEFAULT 0, units INTEGER DEFAULT 0, unit_label TEXT,
  truncated INTEGER DEFAULT 0, note TEXT, created_at REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS sources_sha ON sources(sha256);
CREATE TABLE IF NOT EXISTS passages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, seq INTEGER, locator TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS passages_source ON passages(source_id, seq);
CREATE TABLE IF NOT EXISTS outputs (
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, source_ids TEXT, brief TEXT, neutral TEXT,
  kit_ids TEXT, status TEXT, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
  created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS renders (
  output_id TEXT, kit_id TEXT, kit_version INTEGER, content TEXT, voice_note TEXT, decisions TEXT,
  created_at REAL, PRIMARY KEY (output_id, kit_id)
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, kind TEXT, key TEXT, status TEXT, step TEXT, params TEXT, result TEXT,
  error TEXT, error_code TEXT, created_at REAL, updated_at REAL
);
CREATE INDEX IF NOT EXISTS jobs_key ON jobs(key, status);
CREATE TABLE IF NOT EXISTS chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, refs TEXT, followups TEXT,
  source_ids TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, purpose TEXT, output_id TEXT,
  tokens_in INTEGER, tokens_out INTEGER, created_at REAL
);
CREATE TABLE IF NOT EXISTS looks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kit_id TEXT, kind TEXT, layout TEXT, ground TEXT,
  type_pair TEXT, accent TEXT, signature TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY, text TEXT, refs TEXT, source_ids TEXT, chat_id INTEGER, created_at REAL
);
"""

# Columns added after the first release. A database made by an older Letterpress gets them on open; nothing in an
# existing row changes (a source is in the notebook until the person unticks it).
COLUMNS = (
    ("sources", "summary", "TEXT"), ("sources", "questions", "TEXT"), ("sources", "summary_state", "TEXT"),
    ("sources", "included", "INTEGER DEFAULT 1"), ("chats", "pinned", "INTEGER DEFAULT 0"), ("jobs", "steps", "TEXT"),
)


def _migrate(c) -> None:
    for table, col, decl in COLUMNS:
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def root() -> Path:
    return runtime.data_dir()


def conn() -> sqlite3.Connection:
    """The shared connection, reopened when the data folder changes (profile switch, tests)."""
    global _conn, _conn_dir
    with _lock:
        here = str(root())
        if _conn is not None and _conn_dir == here and Path(here, DB_NAME).exists():
            return _conn
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
        c = None
        if not runtime.data_dir_override() and not runtime.sample_open():
            try:
                from plugins.plugin_storage import plugin_db
                c = plugin_db(runtime.PLUGIN_ID, DB_NAME)
            except Exception:
                c = None
        if c is None:
            c = sqlite3.connect(str(Path(here) / DB_NAME), check_same_thread=False)
            try:
                c.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
        c.row_factory = sqlite3.Row
        c.executescript(SCHEMA)
        c.executescript(VERSIONS_SCHEMA)
        _migrate(c)
        c.commit()
        _conn, _conn_dir = c, here
        return c


def q(sql: str, args: Iterable = ()) -> list:
    with _lock:
        return [dict(r) for r in conn().execute(sql, tuple(args)).fetchall()]


def one(sql: str, args: Iterable = ()) -> Optional[dict]:
    rows = q(sql, args)
    return rows[0] if rows else None


def run(sql: str, args: Iterable = ()) -> int:
    with _lock:
        c = conn()
        cur = c.execute(sql, tuple(args))
        c.commit()
        return cur.lastrowid


def many(sql: str, rows: Iterable[Iterable]) -> None:
    with _lock:
        c = conn()
        c.executemany(sql, [tuple(r) for r in rows])
        c.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> float:
    return time.time()


def today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


def loads(s: Optional[str], default=None):
    if not s:
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- settings --

def get_setting(key: str, default=None):
    row = one("SELECT value FROM settings WHERE key=?", (key,))
    return loads(row["value"], default) if row else default


def set_setting(key: str, value) -> None:
    run("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, dumps(value)))


# ---------------------------------------------------------------- usage --

def record_usage(purpose: str, usage: dict, output_id: Optional[str] = None) -> None:
    tin, tout = int(usage.get("input") or 0), int(usage.get("output") or 0)
    run("INSERT INTO usage(day, purpose, output_id, tokens_in, tokens_out, created_at) VALUES(?,?,?,?,?,?)",
        (today(), purpose, output_id, tin, tout, now()))
    if output_id:
        run("UPDATE outputs SET tokens_in=tokens_in+?, tokens_out=tokens_out+? WHERE id=?", (tin, tout, output_id))


def tokens_today() -> int:
    row = one("SELECT COALESCE(SUM(tokens_in+tokens_out),0) AS n FROM usage WHERE day=?", (today(),))
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------- files --

class OutsideDataFolder(ValueError):
    """A write aimed anywhere but Letterpress's own data folder."""


def inside_root(path: Path) -> Path:
    """``path`` resolved, only when it stays inside the data folder (no ``..``, no absolute path, no link out)."""
    base = root().resolve()
    p = Path(path)
    full = (p if p.is_absolute() else base / p).resolve()
    if full == base or not full.is_relative_to(base):
        raise OutsideDataFolder("Letterpress writes only inside its own data folder.")
    return full


def write_bytes(path: Path, data: bytes) -> None:
    """Atomic write inside the data folder. Every file Letterpress writes comes through here (``write_json`` too),
    and a path that resolves outside the folder is refused before anything is created."""
    path = inside_root(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: Path, data) -> None:
    write_bytes(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return default


def folder_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def forget_everything() -> None:
    """Delete every source, kit, output and record. The folder itself stays, empty."""
    global _conn, _conn_dir
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
        _conn, _conn_dir = None, None
        base = root()
        for child in list(base.iterdir()):
            if child.name == carryover.MARKER:
                continue  # so data kept under the plugin's earlier name is not copied back in
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- versions --
# Every output keeps its versions in ``output_versions``: ``doc`` is the output's neutral doc for that version and
# ``renders`` the voiced doc of every brand it is set in, so Undo puts back exactly what was on screen. Version 1
# ("Made") is written when the make job finishes, or on first read for an output made before versions existed, so a
# database from an older Letterpress opens with nothing lost. Keeping a new version after an Undo drops the versions
# ahead of it (no Redo).

VERSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS output_versions (
  output_id TEXT, v INTEGER, doc TEXT, reason TEXT, created_at REAL, active INTEGER DEFAULT 0, renders TEXT,
  PRIMARY KEY (output_id, v)
);
"""


def _snapshot(output_id: str) -> Optional[tuple]:
    out = one("SELECT neutral, created_at FROM outputs WHERE id=?", (output_id,))
    if not out:
        return None
    rends = {r["kit_id"]: loads(r["content"], {}) for r in q("SELECT kit_id, content FROM renders WHERE output_id=?", (output_id,))}
    return loads(out["neutral"], {}) or {}, rends, out["created_at"]


def _ensure_v1(output_id: str) -> None:
    with _lock:
        if one("SELECT 1 AS x FROM output_versions WHERE output_id=? LIMIT 1", (output_id,)):
            return
        snap = _snapshot(output_id)
        if snap is None:
            raise ValueError("That output is gone. Make it again from your sources.")
        doc, rends, made = snap
        run("INSERT OR IGNORE INTO output_versions(output_id, v, doc, reason, created_at, active, renders) VALUES(?,?,?,?,?,1,?)",
            (output_id, 1, dumps(doc), "Made", made or now(), dumps(rends)))


def record_made(output_id: str) -> None:
    """Version 1 of a fresh output, as the make job left it."""
    with _lock:
        run("DELETE FROM output_versions WHERE output_id=?", (output_id,))
        _ensure_v1(output_id)


def _carry(old, new, voiced):
    """The voiced doc for ``new``: every part the edit left alone keeps its brand voicing (from ``voiced``, which is
    ``old`` voiced), and every changed or added part is the new neutral wording. List items are matched by content,
    so a moved or inserted slide keeps the voicing of the slides around it."""
    if old == new:
        return copy.deepcopy(voiced)
    if isinstance(new, dict) and isinstance(old, dict) and isinstance(voiced, dict):
        return {k: (_carry(old[k], v, voiced[k]) if k in old and k in voiced else copy.deepcopy(v)) for k, v in new.items()}
    if isinstance(new, list) and isinstance(old, list) and isinstance(voiced, list) and len(voiced) == len(old):
        used, out = set(), []
        for i, item in enumerate(new):
            j = next((j for j, o in enumerate(old) if j not in used and o == item), None)
            if j is None and i < len(old) and i not in used and isinstance(item, dict) and isinstance(old[i], dict) \
                    and item.get("type") == old[i].get("type") and len(new) == len(old):
                j = i  # the same slide, edited in place: keep the voicing of its untouched fields
            if j is None:
                out.append(copy.deepcopy(item))
            else:
                used.add(j)
                out.append(_carry(old[j], item, voiced[j]))
        return out
    return copy.deepcopy(new)


def _write(output_id: str, doc: dict, rends: dict) -> None:
    title = (doc or {}).get("title") or (doc or {}).get("headline") or ""
    run("UPDATE outputs SET neutral=?, title=?, updated_at=? WHERE id=?", (dumps(doc), title, now(), output_id))
    for kit_id, body in rends.items():
        run("UPDATE renders SET content=? WHERE output_id=? AND kit_id=?", (dumps(body), output_id, kit_id))


def add_version(output_id: str, doc: dict, reason: str) -> int:
    """Save ``doc`` as the output's new neutral doc, carry it into every brand's voiced doc, make it active.
    Returns its version number."""
    if not isinstance(doc, dict) or not doc:
        raise ValueError("That version is empty.")
    with _lock:
        _ensure_v1(output_id)
        old, rends, _made = _snapshot(output_id)
        act = one("SELECT v FROM output_versions WHERE output_id=? AND active=1", (output_id,))
        cur = act["v"] if act else (one("SELECT MAX(v) AS v FROM output_versions WHERE output_id=?", (output_id,)) or {}).get("v") or 1
        new_rends = {}
        for kit_id, body in rends.items():
            voiced = (body or {}).get("doc") or old
            new_rends[kit_id] = {**(body or {}), "doc": _carry(old, doc, voiced)}
        _write(output_id, doc, new_rends)
        run("DELETE FROM output_versions WHERE output_id=? AND v>?", (output_id, cur))
        run("UPDATE output_versions SET active=0 WHERE output_id=?", (output_id,))
        v = cur + 1
        run("INSERT INTO output_versions(output_id, v, doc, reason, created_at, active, renders) VALUES(?,?,?,?,?,1,?)",
            (output_id, v, dumps(doc), (reason or "Edited")[:120], now(), dumps(new_rends)))
        return v


def undo(output_id: str) -> int:
    """Make the previous version active and put its docs back. ``ValueError("Nothing to undo.")`` at version 1."""
    with _lock:
        _ensure_v1(output_id)
        act = one("SELECT v FROM output_versions WHERE output_id=? AND active=1", (output_id,))
        cur = act["v"] if act else 1
        prev = one("SELECT * FROM output_versions WHERE output_id=? AND v<? ORDER BY v DESC LIMIT 1", (output_id, cur))
        if not prev:
            raise ValueError("Nothing to undo.")
        have = {r["kit_id"] for r in q("SELECT kit_id FROM renders WHERE output_id=?", (output_id,))}
        rends = {k: b for k, b in (loads(prev["renders"], {}) or {}).items() if k in have}
        _write(output_id, loads(prev["doc"], {}) or {}, rends)
        run("UPDATE output_versions SET active=CASE WHEN v=? THEN 1 ELSE 0 END WHERE output_id=?", (prev["v"], output_id))
        return prev["v"]


def versions(output_id: str) -> list:
    """``[{v, created_at, reason, active}]``, oldest first."""
    _ensure_v1(output_id)
    return [{"v": r["v"], "created_at": r["created_at"], "reason": r["reason"], "active": bool(r["active"])}
            for r in q("SELECT v, created_at, reason, active FROM output_versions WHERE output_id=? ORDER BY v", (output_id,))]


def drop_versions(output_id: str) -> None:
    run("DELETE FROM output_versions WHERE output_id=?", (output_id,))


_VERSION_FNS = {"add_version": add_version, "undo": undo, "versions": versions}


def __getattr__(name):  # a test that patches and then deletes one of these must not take the real one away
    if name in _VERSION_FNS:
        return _VERSION_FNS[name]
    raise AttributeError(name)
