"""Finding a browser Letterpress can drive headless: Chrome, Chromium, Edge or Brave, on Mac, Windows or Linux.

One answer for everything Letterpress draws (the three designs, PDF and image export, reading a website's look). Order:

    1. the ``LETTERPRESS_BROWSER`` environment variable (a full path to a browser program), if the file exists;
    2. the usual install paths for the running system;
    3. program names on ``PATH``.

Chrome is preferred over Chromium, Edge and Brave when more than one is installed, because Letterpress's pages were drawn and
checked against it."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

ENV_VAR = "LETTERPRESS_BROWSER"
EARLIER_ENV_VAR = "IMPRINT_BROWSER"  # the name before Nov 12, 2026, still read

_MAC = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)
_LINUX_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
                "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave")
_WIN_REL = (
    ("Google", "Chrome", "Application", "chrome.exe"),
    ("Chromium", "Application", "chrome.exe"),
    ("Microsoft", "Edge", "Application", "msedge.exe"),
    ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
)
_WIN_NAMES = ("chrome.exe", "chrome", "msedge.exe", "msedge", "brave.exe", "brave")

NOT_FOUND = ("Letterpress could not find a browser to draw with. Install Google Chrome (or Chromium, Microsoft Edge or Brave), "
             "or set the LETTERPRESS_BROWSER environment variable to the full path of the browser program, then try again. "
             "Until then the Template version still works.")


def _platform() -> str:
    p = sys.platform
    return "mac" if p == "darwin" else "win" if p.startswith(("win", "cygwin")) else "linux"


def candidates(platform: Optional[str] = None, environ: Optional[dict] = None) -> list:
    """Every path worth trying, in order: the override first, then install paths, then names on PATH are tried by ``find``."""
    plat = platform or _platform()
    env = os.environ if environ is None else environ
    out = []
    if plat == "mac":
        home = env.get("HOME") or str(Path.home())
        out += list(_MAC) + [str(Path(home) / p.lstrip("/")) for p in _MAC]
    elif plat == "win":
        roots = [env.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "ProgramW6432")]
        roots += [r"C:\Program Files", r"C:\Program Files (x86)"]
        seen = set()
        for rel in _WIN_REL:
            for root in roots:
                if root:
                    p = str(Path(root).joinpath(*rel)) if os.name == "nt" else root.rstrip("\\/") + "\\" + "\\".join(rel)
                    if p not in seen:
                        seen.add(p)
                        out.append(p)
    return out


def find(platform: Optional[str] = None, environ: Optional[dict] = None, exists: Optional[Callable] = None,
         which: Optional[Callable] = None) -> Optional[str]:
    """The path of a browser to use, or ``None``. ``exists`` and ``which`` can be replaced (tests do)."""
    plat = platform or _platform()
    env = os.environ if environ is None else environ
    exists = exists or (lambda p: Path(p).is_file())
    which = which or shutil.which
    override = (env.get(ENV_VAR) or env.get(EARLIER_ENV_VAR) or "").strip().strip('"')
    if override:
        if exists(override):
            return override
        got = which(override)  # a bare program name is allowed too
        if got:
            return got
    for p in candidates(plat, env):
        if exists(p):
            return p
    names = _LINUX_NAMES if plat != "win" else _WIN_NAMES
    for n in names:
        got = which(n)
        if got:
            return got
    return None
