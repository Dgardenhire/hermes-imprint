"""Background jobs: every model call, web read and long file read runs here, never inside a request.

A job has an id, a kind, a dedupe key and a status (running, done, failed). The pane starts one with a
POST, gets the id back at once, and polls ``GET /jobs/<id>`` (a pushed ``plugin.imprint.job`` event
speeds that up when Hermes delivers it). Jobs are rows in SQLite, so they survive a pane reload. When
Hermes restarts, any job still marked running is marked failed with "Stopped when Hermes restarted", and
the pane offers Retry, which starts the same kind with the same parameters.

A second start with the same key while one is running returns the running job, so double clicks and two
windows never run the same work twice.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
import threading
import traceback
from typing import Callable, Optional

try:
    from . import runtime as R
    from . import store
except ImportError:  # loaded loose
    import runtime as R  # type: ignore
    import store  # type: ignore

_log = logging.getLogger("hermes.plugins.imprint")
HANDLERS: dict = {}
_threads: dict = {}
_start_lock = threading.Lock()

RESTARTED = "Stopped when Hermes restarted. Press Retry."
UNEXPECTED = "Something went wrong on Imprint's side. Press Retry. If it happens again, try fewer sources."


STOPPED = "Stopped. Your outline is kept."


class Stopped(Exception):
    """Raised inside a job at its next step after the person pressed Stop."""


class JobError(RuntimeError):
    """A plain failure a job reports as is."""

    def __init__(self, message: str, code: str = "failed"):
        super().__init__(message)
        self.code = code


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def view(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {"id": row["id"], "kind": row["kind"], "status": row["status"], "step": row.get("step") or "",
            "result": store.loads(row.get("result")), "error": row.get("error"), "error_code": row.get("error_code"),
            "params": store.loads(row.get("params"), {}), "created_at": row.get("created_at"), "updated_at": row.get("updated_at"),
            "steps": store.loads(row.get("steps"), []) or []}


def get(job_id: str) -> Optional[dict]:
    return view(store.one("SELECT * FROM jobs WHERE id=?", (job_id,)))


def running(kind: Optional[str] = None) -> list:
    if kind:
        rows = store.q("SELECT * FROM jobs WHERE status='running' AND kind=? ORDER BY created_at", (kind,))
    else:
        rows = store.q("SELECT * FROM jobs WHERE status='running' ORDER BY created_at")
    return [view(r) for r in rows]


def recent(n: int = 30) -> list:
    return [view(r) for r in store.q("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (n,))]


def recover() -> int:
    """Mark jobs left running by a previous process as failed, with Retry."""
    rows = store.q("SELECT id FROM jobs WHERE status='running'")
    live = {jid for jid, t in _threads.items() if t.is_alive()}
    stale = [r["id"] for r in rows if r["id"] not in live]
    for jid in stale:
        store.run("UPDATE jobs SET status='failed', error=?, error_code='restart', updated_at=? WHERE id=?",
                  (RESTARTED, store.now(), jid))
    return len(stale)


def step(job_id: str, text: str) -> None:
    """The job's current step. Every step is also kept, with when it began, so the pane can show what is done,
    what is running and how long each part took: real progress, never a made-up percentage."""
    t = store.now()
    row = store.one("SELECT steps, status FROM jobs WHERE id=?", (job_id,)) or {}
    if row.get("status") == "stopped":
        raise Stopped()
    steps = store.loads(row.get("steps"), []) or []
    if not steps or steps[-1].get("text") != text[:120]:
        if steps and not steps[-1].get("done_at"):
            steps[-1]["done_at"] = t
        steps.append({"text": text[:120], "at": t, "done_at": None})
    store.run("UPDATE jobs SET step=?, steps=?, updated_at=? WHERE id=? AND status='running'", (text[:120], store.dumps(steps[-20:]), t, job_id))
    R.broadcast("job", {"id": job_id, "status": "running", "step": text[:120]})


def _close_steps(job_id: str) -> None:
    row = store.one("SELECT steps FROM jobs WHERE id=?", (job_id,)) or {}
    steps = store.loads(row.get("steps"), []) or []
    if steps and not steps[-1].get("done_at"):
        steps[-1]["done_at"] = store.now()
        store.run("UPDATE jobs SET steps=? WHERE id=?", (store.dumps(steps), job_id))


def stopped(job_id: str) -> bool:
    row = store.one("SELECT status FROM jobs WHERE id=?", (job_id,))
    return bool(row) and row["status"] == "stopped"


def stop(job_id: str) -> dict:
    """Stop a running job: it shows as stopped at once and its work ends at its next step. Retry starts it again."""
    job = get(job_id)
    if not job:
        raise ValueError("That job is gone.")
    if job["status"] != "running":
        return job
    store.run("UPDATE jobs SET status='stopped', error=?, error_code='stopped', updated_at=? WHERE id=? AND status='running'",
              (STOPPED, store.now(), job_id))
    _close_steps(job_id)
    R.broadcast("job", {"id": job_id, "status": "stopped"})
    return get(job_id)


def start(kind: str, key: str, params: dict, wait: bool = False) -> dict:
    """Start a job (or return the one already running under ``key``)."""
    if kind not in HANDLERS:
        raise ValueError(f"unknown job kind {kind!r}")
    with _start_lock:
        existing = store.one("SELECT * FROM jobs WHERE key=? AND status='running' ORDER BY created_at DESC", (key,))
        if existing and (existing["id"] in _threads and _threads[existing["id"]].is_alive()):
            return view(existing)
        job_id = store.new_id("j")
        t = store.now()
        store.run("INSERT INTO jobs(id, kind, key, status, step, params, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (job_id, kind, key, "running", "Starting", store.dumps(params), t, t))
        # The job runs in the request's context: Hermes keeps the active profile's home in a context
        # variable, and a bare thread would fall back to the default profile's data folder and model.
        scope = contextvars.copy_context()
        th = threading.Thread(target=scope.run, args=(_run, job_id, kind, params), name=f"imprint-{kind}-{job_id}", daemon=True)
        _threads[job_id] = th
        th.start()
    if wait:
        th.join()
    return get(job_id)


def retry(job_id: str) -> dict:
    old = get(job_id)
    if not old:
        raise ValueError("That job is gone.")
    if old["status"] == "running":
        return old  # stopped, failed and done jobs all start again
    key = (store.one("SELECT key FROM jobs WHERE id=?", (job_id,)) or {}).get("key") or job_id
    return start(old["kind"], key, old["params"] or {})


def _run(job_id: str, kind: str, params: dict) -> None:
    fn: Callable = HANDLERS[kind]
    try:
        if inspect.iscoroutinefunction(fn):
            result = asyncio.run(fn(job_id, params))
        else:
            result = fn(job_id, params)
        _close_steps(job_id)
        if stopped(job_id):  # finished after Stop: the work is kept, the job stays stopped
            store.run("UPDATE jobs SET result=? WHERE id=?", (store.dumps(result), job_id))
            return
        store.run("UPDATE jobs SET status='done', step='Done', result=?, updated_at=? WHERE id=? AND status='running'",
                  (store.dumps(result), store.now(), job_id))
        R.broadcast("job", {"id": job_id, "status": "done"})
    except Stopped:
        pass
    except (JobError, R.ModelError) as e:
        _fail(job_id, str(e), getattr(e, "code", "failed"))
    except ValueError as e:  # our own plain refusals (ingest.Refused, kits.KitError) are ValueErrors
        _fail(job_id, str(e) or UNEXPECTED, "refused")
    except Exception:
        _log.error("imprint: job %s (%s) failed:\n%s", job_id, kind, traceback.format_exc())
        _fail(job_id, UNEXPECTED, "unexpected")
    finally:
        _threads.pop(job_id, None)


def _fail(job_id: str, message: str, code: str) -> None:
    if stopped(job_id):
        return
    _close_steps(job_id)
    store.run("UPDATE jobs SET status='failed', error=?, error_code=?, updated_at=? WHERE id=? AND status='running'",
              (message[:600], code, store.now(), job_id))
    R.broadcast("job", {"id": job_id, "status": "failed"})
