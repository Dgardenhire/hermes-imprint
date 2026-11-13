"""The environment every program the plugin starts gets: a short allowlist, never Hermes's own environment.

Hermes keeps provider keys and other secrets in its environment. The headless browser loads third-party pages and
``sips`` reads files the plugin wrote, so neither gets any of that: ``child_env()`` copies only the names below from
the current environment, and leaves out everything else.

Every platform:
- ``PATH``  so a program can find its own helpers (falls back to ``os.defpath`` when unset)
- ``HOME``  the browser resolves its default folders from it, even with ``--user-data-dir``
- ``TMPDIR``, ``TEMP``, ``TMP``  where the program writes scratch files
- ``LANG`` and every ``LC_*``  text encoding and locale, so file names and page text decode the same way

Linux, also:
- ``DISPLAY``, ``WAYLAND_DISPLAY``, ``XDG_RUNTIME_DIR``  harmless for ``--headless=new``, and needed if a browser
  build still opens a display connection at start

Windows, also:
- ``SYSTEMROOT``, ``WINDIR``  a Windows program without them can fail to load system libraries or start networking
- ``USERPROFILE``, ``LOCALAPPDATA``, ``APPDATA``  the browser resolves its own folders from them at start

Left out on purpose: ``DBUS_SESSION_BUS_ADDRESS`` (headless Chrome starts without it and only logs that the bus is
missing), ``PROGRAMFILES`` (used to find the browser, which happens in this process, not in the child), and every
variable the person or Hermes set for themselves, including provider keys and the plugin's own settings."""

from __future__ import annotations

import os
import sys
from typing import Mapping, Optional

COMMON = ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG")
PREFIXES = ("LC_",)
LINUX = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR")
WINDOWS = ("SYSTEMROOT", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA")


def _platform() -> str:
    p = sys.platform
    return "mac" if p == "darwin" else "win" if p.startswith(("win", "cygwin")) else "linux"


def allowed_names(platform: Optional[str] = None) -> tuple:
    """The exact names (besides the ``LC_`` prefix) a child may receive on ``platform``."""
    plat = platform or _platform()
    return COMMON + (LINUX if plat == "linux" else WINDOWS if plat == "win" else ())


def child_env(environ: Optional[Mapping[str, str]] = None, platform: Optional[str] = None) -> dict:
    """A new dict holding only the allowed names that are set in ``environ`` (default: this process's environment)."""
    plat = platform or _platform()
    src = os.environ if environ is None else environ
    names = allowed_names(plat)
    fold = plat == "win"  # Windows variable names are not case sensitive
    wanted = {n.upper() for n in names} if fold else set(names)
    out = {}
    for key, value in src.items():
        k = key.upper() if fold else key
        if k in wanted or any(k.startswith(p) for p in PREFIXES):
            out[key] = value
    if not any((k.upper() if fold else k) == "PATH" for k in out):
        out["PATH"] = os.defpath
    return out
