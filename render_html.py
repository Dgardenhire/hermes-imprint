"""The HTML export: the proof tree written as a self-contained page.

The same nodes and the same stylesheet the pane uses (layout.py), with the kit's fonts embedded as data
URLs. One file, no network, opens anywhere.

The exported page is the finished document, not the proof: no per-number trace marks, no color bar and
no colophon (those belong on the proof). Source marks are field-level footnotes that link to the
numbered source list, and a kit that hides its source list (a menu, a flyer) gets no marks at all. The
page reflows to one column on a phone.
"""

from __future__ import annotations

import html
import re

try:
    from . import fonts as F
    from . import layout as L
except ImportError:  # loaded loose
    import fonts as F  # type: ignore
    import layout as L  # type: ignore

VOID = {"img", "hr"}
SAFE_CSS_VAR = re.compile(r"^--[a-z0-9-]+$")
SAFE_ID = re.compile(r"^ip-src-\d{1,3}$")


def _attrs(node: dict) -> str:
    out = []
    if node.get("c"):
        out.append(f'class="{html.escape(node["c"], quote=True)}"')
    a = node.get("a") or {}
    if node["t"] == "img" and isinstance(a.get("src"), str) and a["src"].startswith("data:image/"):
        out.append(f'src="{html.escape(a["src"], quote=True)}" alt=""')
    if isinstance(a.get("id"), str) and SAFE_ID.match(a["id"]):
        out.append(f'id="{a["id"]}"')
    style = a.get("style")
    if isinstance(style, dict):
        decl = ";".join(f"{k}:{_css_value(v)}" for k, v in style.items() if SAFE_CSS_VAR.match(k))
        out.append(f'style="{html.escape(decl, quote=True)}"')
    return (" " + " ".join(out)) if out else ""


LOADS = re.compile(r"url\s*\(|image(?:-set)?\s*\(|@import|expression\s*\(|\\", re.I)


def _css_value(v) -> str:
    """A custom property's value with no way out of its declaration and nothing that could load: the export
    promises no network, and ``background:var(--k-band)`` would fetch a ``url()`` if one ever reached a token.
    Today every token is a checked hex color, number or font stack; this holds if that ever changes."""
    v = re.sub(r"[;{}<>]", "", str(v))
    return "" if LOADS.search(v) else v


def _is_mark(node: dict) -> bool:
    return node.get("t") == "sup" and "ip-ref" in (node.get("c") or "").split()


def _ends_in_figure(node: dict) -> bool:
    text = L.text_of(node).rstrip()
    return bool(text) and (text[-1].isdigit() or text[-1] == "%")


def node_html(node: dict, links: bool = False) -> str:
    """One node as markup. ``links`` makes each source mark a footnote link to its line in the source list,
    with a no-break space before it when the text ends in a figure, so "$3" never reads as "$31"."""
    t = node.get("t")
    if t not in L.TAGS:
        return ""
    if t in VOID:
        if t == "img" and not ((node.get("a") or {}).get("src") or "").startswith("data:image/"):
            return ""
        return f"<{t}{_attrs(node)}>"
    if links and _is_mark(node):
        nums = [x.strip() for x in (node.get("x") or "").split(",") if x.strip().isdigit()]
        inner = ",".join(f'<a href="#ip-src-{x}">{x}</a>' for x in nums)
        return f"<{t}{_attrs(node)}>{inner}</{t}>"
    parts, prev = [html.escape(node.get("x") or "")], None
    for c in node.get("k") or []:
        if links and _is_mark(c) and prev is not None and _ends_in_figure(prev):
            parts.append("&nbsp;")
        parts.append(node_html(c, links))
        prev = c
    return f"<{t}{_attrs(node)}>{''.join(parts)}</{t}>"


def strip_marks(node: dict) -> dict:
    """The tree without any source marks (a kit that lists no sources, like a menu or a flyer)."""
    kids = [strip_marks(c) for c in node.get("k") or [] if not _is_mark(c)]
    out = {k: v for k, v in node.items() if k != "k"}
    if node.get("k") is not None:
        out["k"] = kids
    return out


def font_faces_css(faces: dict) -> str:
    out, seen = [], set()
    for f in faces.values():
        if f.get("file") and f.get("key") and f["key"] not in seen:
            seen.add(f["key"])
            out.append("@font-face{font-family:\"imp-%s\";src:url(data:font/ttf;base64,%s) format(\"truetype\");font-weight:%s;font-style:%s}"
                       % (f["key"], F.font_bytes_b64(f["file"]), f.get("weight", 400), f.get("style", "normal")))
    return "\n".join(out)


EXPORT_CSS = """
html,body{margin:0;background:#e9e9e7}
body{padding:32px 16px}
.sheet{max-width:8.5in;margin:0 auto;box-shadow:0 1px 3px rgba(0,0,0,.18)}
.sheet .ip-page{--ip-base:16px;overflow-wrap:anywhere}
.sheet img{max-width:100%;height:auto}
.sheet .ip-page *{min-width:0}
.ip-ref a{color:inherit;text-decoration:none}
.ip-ref a:hover,.ip-ref a:focus-visible{text-decoration:underline}
.ip-sources-list li:target{outline:2px solid var(--k-accent);outline-offset:2px}
@media (max-width:700px){html,body{background:none} body{padding:0} .sheet{box-shadow:none;max-width:none}
  .sheet .ip-page{--ip-base:16px} .ip-title,.ip-title-big{font-size:min(2.1em,9vw)!important}
  .ip-inner,.ip-band,.ip-main,.ip-rail{padding-left:20px!important;padding-right:20px!important}
  .ip-banner-grid,.ip-bulletin-grid,.ip-head-row,.ip-tiles,.ip-margin-grid,.ip-flyer-cols,.ip-figures,.ip-report-row{grid-template-columns:minmax(0,1fr)!important}
  .ip-bulletin-cols,.ip-flyer-cols{columns:1!important}
  .ip-date{margin-left:0}}
@media print{html,body{background:none} body{padding:0} .sheet{box-shadow:none;max-width:none}
  .sheet .ip-page{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .ip-section,.ip-stat,.ip-quote,.ip-menu-item{break-inside:avoid} .ip-h2{break-after:avoid} p{orphans:3;widows:3}}
"""


def _scene_css(tree: dict) -> str:
    """A one-pager set as a scene (studio kits): the scene stylesheet and a letter-wide sheet."""
    if "ip-scene" not in (tree.get("c") or "").split():
        return ""
    try:
        from . import scene as SC
    except ImportError:  # loaded loose
        import scene as SC  # type: ignore
    return SC.SCENE_CSS + "\n.sheet>.ip-scene{max-width:8.5in;margin:0 auto;box-shadow:none} .sheet .ip-scene img{height:calc(var(--h)*1%)}\n" \
        "@media print{@page{size:letter;margin:0} .sheet>.ip-scene{max-width:none;width:8.5in}}"


def export_page(tree: dict, faces: dict, title: str, marks: bool = True) -> str:
    """The finished page: no trace marks, no proof furniture, footnote marks that link to the sources."""
    if not marks:
        tree = strip_marks(tree)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{font_faces_css(faces)}
{L.PROOF_CSS}
{EXPORT_CSS}
{_scene_css(tree)}
</style></head>
<body><main class="sheet">{node_html(tree, links=marks)}</main></body></html>
"""


def page(tree: dict, faces: dict, bar: list, colophon: str, title: str) -> str:
    """The proof as a page, with the kit's color bar and the colophon in the slug (harness and proofs)."""
    bar_html = "".join(f'<span style="background:{html.escape(c)}"></span>' for c in bar)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{font_faces_css(faces)}
{L.PROOF_CSS}
html,body{{margin:0;background:#e9e9e7}}
body{{padding:32px 16px}}
.sheet{{max-width:8.5in;margin:0 auto;box-shadow:0 1px 3px rgba(0,0,0,.18)}}
.sheet .ip-page{{--ip-base:16px;min-height:11in}}
.slug{{max-width:8.5in;margin:10px auto 0;font:13px/1.4 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#1f2328}}
.bar{{display:flex;height:10px}} .bar span{{flex:1}}
.colophon{{margin-top:6px}}
@media (max-width:700px){{body{{padding:0}} .sheet .ip-page{{--ip-base:15px;min-height:0}} .slug{{padding:0 12px 16px}}}}
@media print{{html,body{{background:none}} body{{padding:0}} .sheet{{box-shadow:none;max-width:none}}
  .sheet .ip-page{{-webkit-print-color-adjust:exact;print-color-adjust:exact}} .slug{{color:#000}}
  .ip-section,.ip-stat,.ip-quote{{break-inside:avoid}} .ip-h2{{break-after:avoid}} p{{orphans:3;widows:3}}}}
</style></head>
<body><div class="sheet">{node_html(tree)}</div>
<div class="slug"><div class="bar">{bar_html}</div><p class="colophon">{html.escape(colophon)}</p></div>
</body></html>
"""
