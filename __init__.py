"""Imprint for Hermes (``imprint``).

Your sources, set in your look. Imprint keeps each brand as a kit (colors with roles checked for
contrast, fonts, logo, voice rules, a layout family and rules for every page), writes the content once
from a chosen source set, rewrites only the wording per kit, renders the result through two kits side
by side, and checks every number and quote against the source passages before anything exports.

Modules (loaded as one package by ``dashboard/plugin_api.py``):

- ``runtime``  the bridge to Hermes: the plugin context, the model, tool dispatch, events, data folder
- ``store``    SQLite index (sources, passages, outputs, renders, jobs, chats, usage, looks)
- ``ingest``   reading PDF, DOCX, TXT, MD, transcripts, web pages and pasted text into passages
- ``colors``   WCAG contrast and color roles
- ``fonts``    the bundled OFL fonts, uploaded fonts, and honest font resolution
- ``kits``     the kit model, the starter library, versioning, the recent-looks record
- ``sitekit``  reading a kit from a website's own CSS
- ``guide``    "help me build a kit": fixed and free, the subject, references, three proposals
- ``content``  the content schema, the writing prompts, the voice pass and its fact check
- ``checks``   grounding, contrast, never-say, required lines, font substitutions
- ``layout``   the proof tree each layout family builds (shared by the preview and the HTML export)
- ``render_pdf`` / ``render_html``  the exports
- ``jobs``     background jobs that survive a pane reload

``register(ctx)`` registers one auxiliary task, ``imprint_write``, so the user can point Imprint's
writing at any model under Settings, Models, Auxiliary. It registers no tools and no hooks, matching
``plugin.yaml``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

PLUGIN_ID = "imprint"
AUX_TASK = "imprint_write"
TOOLS: tuple = ()
HOOKS: tuple = ()
SHARED_PACKAGE = "imprint_plugin_package"

_log = logging.getLogger("hermes.plugins.imprint")


def shared_package():
    """The plugin's modules as one package under a fixed name, shared by ``register`` and the routes.

    Hermes imports this file once for ``register(ctx)`` and the dashboard imports ``plugin_api.py`` on
    its own. Both reach the same package object through this name, so the routes can use the context
    that ``register`` received."""
    pkg = sys.modules.get(SHARED_PACKAGE)
    if pkg is None:
        root = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location(SHARED_PACKAGE, root / "__init__.py",
                                                      submodule_search_locations=[str(root)])
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load the Imprint package")
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[SHARED_PACKAGE] = pkg
        spec.loader.exec_module(pkg)
    return pkg


def register(ctx) -> None:
    """Register Imprint's writing task and hand the context to the routes. Nothing runs in the agent."""
    try:
        ctx.register_auxiliary_task(
            AUX_TASK,
            display_name="Imprint writing",
            description="Writes Imprint's briefs, decks and audio scripts from your sources, and rewrites them in each kit's voice.",
        )
    except Exception as exc:  # an older Hermes or a duplicate registration: the main model still works
        _log.warning("imprint: could not register the %s task (%s); using the main model", AUX_TASK, exc)
    try:
        from importlib import import_module
        runtime = import_module(f"{shared_package().__name__}.runtime")
        runtime.set_context(ctx)
    except Exception:
        _log.exception("imprint: could not share the plugin context with the page routes")
    _log.info("imprint: the Imprint page is available in the desktop app")
