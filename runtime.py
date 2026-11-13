"""The bridge to Hermes. Everything Letterpress takes from the host goes through this file.

- ``set_context`` / ``context``: the ``PluginContext`` that ``register(ctx)`` received, when this process
  ran it. The routes use it for ``ctx.llm`` and ``ctx.dispatch_tool``.
- ``data_dir``: ``plugins.plugin_storage.plugin_data_dir("letterpress")``, or ``LETTERPRESS_DATA_DIR`` in tests
  and the harness, so they can never touch a real profile.
- ``Model``: the writing calls, over the user's own Hermes model, with plain-English failures, a token
  meter fed from each ``result.usage``, and an optional daily cap.
- ``dispatch``: one of the user's own Hermes tools, through ``ctx.dispatch_tool`` or the public tool registry.
  Letterpress calls exactly one, ``text_to_speech``, with a fixed name and its own arguments (service.speak); images
  reach the model as blocks in the writing call, never through a tool, and nothing a model writes picks a tool.
- ``broadcast``: ``plugin.letterpress.<event>`` to every open window, for job progress.
- ``redact``: Hermes's secret redactor, run on source text before a model sees it.
"""

from __future__ import annotations

import asyncio
import time
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from . import carryover
except ImportError:  # loaded loose
    import carryover  # type: ignore

PLUGIN_ID = "letterpress"
EARLIER_ID = "imprint"  # the plugin's name before Nov 12, 2026; its data folder is copied in once (carryover.py)
DATA_DIR_VAR = "LETTERPRESS_DATA_DIR"
EARLIER_DATA_DIR_VAR = "IMPRINT_DATA_DIR"  # still read, so a folder set under the earlier name keeps working
AUX_TASK = "letterpress_write"
_log = logging.getLogger("hermes.plugins.letterpress")

_ctx = None
_ctx_lock = threading.Lock()


def set_context(ctx) -> None:
    global _ctx
    with _ctx_lock:
        _ctx = ctx


def context():
    return _ctx


SAMPLE_DIR = "sample"
SAMPLE_FLAG = "sample-open"


def data_dir_override() -> str:
    """The data folder named in the environment (tests, the harness, or a person who set one), else empty."""
    return os.environ.get(DATA_DIR_VAR) or os.environ.get(EARLIER_DATA_DIR_VAR) or ""


def base_dir() -> Path:
    """The person's own data folder."""
    override = data_dir_override()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    from plugins.plugin_storage import plugin_data_dir  # inside Hermes
    path = plugin_data_dir(PLUGIN_ID)
    try:
        carryover.carry_over_once(path, path.parent / EARLIER_ID)  # data kept under the earlier name, copied in once
    except Exception:  # noqa: BLE001 - never block the plugin over this
        _log.warning("letterpress: earlier data not carried over", exc_info=True)
    return path


def sample_open() -> bool:
    try:
        return (base_dir() / SAMPLE_FLAG).exists()
    except OSError:
        return False


def data_dir() -> Path:
    """Where Letterpress reads and writes right now: the person's own folder, or ``<it>/sample/`` while the sample
    notebook is open (the person's own files are never touched while it is)."""
    base = base_dir()
    if (base / SAMPLE_FLAG).exists():
        path = base / SAMPLE_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path
    return base


def redact(text: str) -> str:
    """Hermes's own secret redactor, forced on. Outside Hermes the text passes through unchanged."""
    try:
        from agent.redact import redact_sensitive_text
    except Exception:
        return text
    try:
        return redact_sensitive_text(text, force=True)
    except TypeError:  # an older signature without force
        try:
            return redact_sensitive_text(text)
        except Exception:
            return text
    except Exception:
        return text


def broadcast(event: str, payload: Optional[dict] = None) -> None:
    """Push ``plugin.letterpress.<event>``; polling still works when this does nothing."""
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
    except Exception:
        return
    try:
        broadcast_plugin_event(PLUGIN_ID, event, payload or {})
    except Exception:
        _log.debug("letterpress: event %s not delivered", event, exc_info=True)


# ---------------------------------------------------------------- model --

class ModelError(RuntimeError):
    """A failure the page shows as is. ``code`` lets the page pick the right next step."""

    def __init__(self, message: str, code: str = "model"):
        super().__init__(message)
        self.code = code


NO_MODEL = "Letterpress couldn't reach your Hermes model. Check Settings, then press Retry."
BUSY = "Your model is busy right now. Wait a minute, then press Retry."
NOT_ALLOWED = "Hermes did not let Letterpress use the model. Check Letterpress's settings under Plugins, then press Retry."
CUT_OFF = "Your model stopped before the answer was finished. Press Retry; if it happens again, ask for a shorter piece."
TIMED_OUT = "Your model took too long to answer. Press Retry, or try fewer sources."
CAP_REACHED = "Today's token limit for Letterpress is used up. Raise it in Letterpress's settings, or try again tomorrow."


def model_error(e: BaseException) -> ModelError:
    if isinstance(e, ModelError):
        return e
    name = type(e).__name__
    msg = str(e).lower()
    _log.warning("letterpress: model call failed: %s: %s", name, str(e)[:300])
    if name == "PluginLlmTrustError":
        return ModelError(NOT_ALLOWED, "not_allowed")
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)) or "timed out" in msg or "timeout" in msg:
        return ModelError(TIMED_OUT, "timeout")
    if "429" in msg or "rate limit" in msg or "overloaded" in msg or "529" in msg:
        return ModelError(BUSY, "busy")
    return ModelError(NO_MODEL, "no_model")


def trace(line: str) -> None:
    """A one-line note in the plugin's own data folder (shape and error class only, never the person's words). It is
    how a failure that logs nothing gets explained; it keeps the last 200 lines."""
    try:
        f = data_dir() / "debug.log"
        old = f.read_text("utf-8").splitlines()[-199:] if f.exists() else []
        f.write_text("\n".join(old + [time.strftime("%H:%M:%S ") + line[:400]]) + "\n", "utf-8")
    except Exception:
        pass


def format_refused(e: BaseException) -> bool:
    """True when the provider rejected the structured-output request itself, not the answer."""
    msg = str(e).lower()
    if "only json_schema structured output is supported" in msg or "structured output is supported" in msg:
        return True  # Hermes itself declines json_mode for this provider, before any call is made
    return ("400" in msg or "invalid_request" in msg) and any(k in msg for k in ("additionalproperties", "output_config", "response_format", "json_schema", "structured output"))


def _usage_of(result) -> dict:
    u = getattr(result, "usage", None)
    if u is None:
        return {"input": 0, "output": 0}
    get = (lambda k: u.get(k)) if isinstance(u, dict) else (lambda k: getattr(u, k, None))
    inp = get("input_tokens") or get("prompt_tokens") or 0
    out = get("output_tokens") or get("completion_tokens") or 0
    try:
        return {"input": int(inp or 0), "output": int(out or 0)}
    except (TypeError, ValueError):
        return {"input": 0, "output": 0}


def parse_json(text: str):
    """The first JSON object in ``text``. Raises ModelError(CUT_OFF) when none parses."""
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        raise ModelError(CUT_OFF, "cut_off")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
    raise ModelError(CUT_OFF, "cut_off")


class Model:
    """Letterpress's model calls over Hermes's plugin LLM facade.

    ``llm`` is ``ctx.llm`` when ``register`` ran in this process, else a ``PluginLlm`` for this plugin
    (the Debate Workbench pattern), or a stand-in with the same async methods in tests. Calls route
    through Letterpress's own auxiliary task; if Hermes refuses the task key (an older Hermes, or the task
    was not registered in this process), the call runs once more on the main model."""

    def __init__(self, llm=None, meter: Optional[Callable[[str, dict], None]] = None,
                 cap: Optional[Callable[[], Optional[int]]] = None, used_today: Optional[Callable[[], int]] = None):
        self._llm = llm
        self.meter = meter
        self.cap = cap
        self.used_today = used_today
        self.use_task = True
        self.plain = False

    @property
    def llm(self):
        if self._llm is None:
            ctx = context()
            llm = getattr(ctx, "llm", None) if ctx is not None else None
            if llm is None:
                from agent.plugin_llm import PluginLlm  # inside Hermes only
                llm = PluginLlm(plugin_id=PLUGIN_ID)
            self._llm = llm
        return self._llm

    def _check_cap(self):
        if not self.cap or not self.used_today:
            return
        limit = self.cap()
        if limit and self.used_today() >= limit:
            raise ModelError(CAP_REACHED, "cap")

    async def _call(self, fn, kwargs):
        if self.use_task:
            try:
                return await fn(task=AUX_TASK, **kwargs)
            except Exception as e:
                if type(e).__name__ == "PluginLlmTrustError" and "task" in str(e).lower():
                    _log.info("letterpress: %s task not accepted here; using the main model", AUX_TASK)
                    self.use_task = False
                else:
                    raise
        return await fn(**kwargs)

    @staticmethod
    def _plain_hint(schema: Optional[dict]) -> str:
        hint = "\n\nReply with one complete JSON object and nothing else: no code fence, no commentary."
        if schema is not None:
            hint += " It must fit this JSON Schema: " + json.dumps(schema, separators=(",", ":"))
        return hint

    async def structured(self, *, system: str, instructions: str, body: str, schema: Optional[dict],
                         purpose: str, max_tokens: int = 6000, timeout: float = 240.0, images=None) -> dict:
        """A JSON answer that matches ``schema``. One repair attempt when the reply is cut off or broken."""
        self._check_cap()
        blocks: list = [{"type": "text", "text": body}]
        for img in images or []:
            blocks.append(img)
        last_err: Optional[BaseException] = None
        started_plain = self.plain  # three designs call at once; each judges from the mode it began in
        for attempt in range(2):
            instr = instructions if attempt == 0 else (
                instructions + "\n\nYour last reply was cut off or was not valid JSON. Reply again with shorter text in every field, as one complete JSON object.")
            if self.plain:  # no format request at all: the prompt asks for the JSON and Letterpress reads it
                instr += self._plain_hint(schema)
            try:
                result = await asyncio.wait_for(self._call(self.llm.acomplete_structured, dict(
                    instructions=instr, input=blocks, system_prompt=system,
                    json_schema=None if self.plain else schema, json_mode=False if self.plain else schema is None,
                    max_tokens=max_tokens, timeout=timeout,
                    purpose=f"letterpress.{purpose}")), timeout=timeout + 15)
            except ValueError as e:  # Hermes refused the format request, or validated the reply against the schema and it did not match
                if not started_plain and format_refused(e):
                    trace(f"{purpose}: the provider refuses this format request; asking in plain text from here on")
                    self.plain = True
                    return await self.structured(system=system, instructions=instructions, body=body, schema=schema,
                                                 purpose=purpose, max_tokens=max_tokens, timeout=timeout, images=images)
                last_err = ModelError(CUT_OFF, "cut_off")
                trace(f"{purpose} attempt {attempt} plain={self.plain}: ValueError {str(e)[:200]}")
                _log.warning("letterpress: %s reply did not match the schema (%s)", purpose, str(e)[:200])
                continue
            except Exception as e:
                trace(f"{purpose} attempt {attempt} plain={self.plain}: {type(e).__name__} {str(e)[:250]}")
                if not started_plain and format_refused(e):
                    # Some providers (Claude's strict output mode) refuse the format request itself. Ask in plain
                    # words from here on, the way a plain prompt does, and read the JSON out of the reply.
                    _log.info("letterpress: the provider refused a format request; asking for JSON in plain text")
                    self.plain = True
                    last_err = None
                    return await self.structured(system=system, instructions=instructions, body=body, schema=schema,
                                                 purpose=purpose, max_tokens=max_tokens, timeout=timeout, images=images)
                raise model_error(e)
            if self.meter:
                try:
                    self.meter(purpose, _usage_of(result))
                except Exception:
                    _log.debug("letterpress: usage not recorded", exc_info=True)
            parsed = getattr(result, "parsed", None)
            trace(f"{purpose} attempt {attempt} plain={self.plain}: got parsed={type(parsed).__name__} text={len(getattr(result, 'text', '') or '')} chars")
            if isinstance(parsed, dict):
                return parsed
            try:
                return parse_json(getattr(result, "text", "") or "")
            except ModelError as e:
                txt = getattr(result, "text", "") or ""
                # Shape only, never the words: the reply is built from the person's own documents.
                _log.warning("letterpress: %s reply was not readable JSON (%d characters; opens with %s; ends with %s; braces %d open, %d closed)",
                             purpose, len(txt), "a code fence" if txt.lstrip().startswith("```") else ("{" if txt.lstrip().startswith("{") else "other text"),
                             "}" if txt.rstrip().endswith("}") else ("a code fence" if txt.rstrip().endswith("```") else "other text"),
                             txt.count("{"), txt.count("}"))
                last_err = e
                continue
        raise last_err or ModelError(CUT_OFF, "cut_off")


# ---------------------------------------------------------------- tools --

class ToolUnavailable(RuntimeError):
    pass


def dispatch(tool: str, args: dict, timeout: float = 180.0) -> Any:
    """Run one of the user's Hermes tools and return its parsed JSON result.

    Raises ToolUnavailable when the tool is not set up here (unknown tool, or it reported an error)."""
    ctx = context()
    raw = None
    try:
        if ctx is not None and hasattr(ctx, "dispatch_tool"):
            raw = ctx.dispatch_tool(tool, args)
        else:
            from tools.registry import registry  # public module
            raw = registry.dispatch(tool, args)
    except ToolUnavailable:
        raise
    except Exception as e:
        raise ToolUnavailable(f"{tool} failed: {type(e).__name__}") from e
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"text": raw}
    if isinstance(data, dict) and (data.get("error") or data.get("success") is False):
        raise ToolUnavailable(str(data.get("error") or data.get("message") or f"{tool} is not available")[:300])
    return data


def dispatch_bounded(tool: str, args: dict, timeout: float) -> Any:
    """``dispatch`` with a hard time limit. The tool runs on its own daemon thread; if it has not answered
    after ``timeout`` seconds, this raises ToolUnavailable("timed out") and the caller moves on (the
    stray call can finish or not, it holds nothing of Letterpress's)."""
    box: dict = {}

    def work():
        try:
            box["ok"] = dispatch(tool, args, timeout)
        except BaseException as e:  # handed back to the caller below
            box["err"] = e

    import contextvars
    th = threading.Thread(target=contextvars.copy_context().run, args=(work,), name=f"letterpress-tool-{tool}", daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        _log.warning("letterpress: %s did not answer within %ss", tool, int(timeout))
        raise ToolUnavailable("timed out")
    if "err" in box:
        raise box["err"]
    return box.get("ok")
