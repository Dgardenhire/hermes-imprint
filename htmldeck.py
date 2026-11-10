"""The HTML deck path: the model writes each slide as HTML and CSS at 1920x1080 and chooses its own exhibits; Imprint
adds what only it does.

    1. ``sanitize``   the model's markup is untrusted: scripts, event handlers, links, forms, frames, external
                      addresses and anything that can fetch are removed before a browser sees it;
    2. ``trace``      every number in the markup must sit inside an element that carries ``data-source="P3 P7"`` (the
                      passage ids it is cited to), and must be found in, or worked out from two numbers in, those
                      passages (the same ``checks.check_line`` every other Imprint output uses). Chart marks carry
                      ``data-value`` and are traced the same way. Unsupported numbers come back as flags;
    3. ``render``     headless Chrome draws every slide (a screenshot per slide, one PDF), measures what the model
                      cannot see (text cut off, boxes outside the slide, type under the floor) and returns it;
    4. ``make``       the loop: the model writes, Imprint renders, the model is shown the pictures and the problem
                      list and fixes what it sees, up to ``rounds`` times;
    5. ``pptx``       the slides as full-bleed pictures with the slide's notes and sources in the notes pane.

Chrome runs with its own scratch ``--user-data-dir`` and ``--mute-audio``; the folder is deleted afterward. The page
carries a Content-Security-Policy that allows no network, no script but Imprint's own measuring script (by hash), and
only inline styles, ``data:`` fonts and ``data:`` pictures."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html as _html
import json
import re
import shutil
import subprocess
import secrets
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

try:  # package import (Hermes) or flat import (tests)
    from . import checks as C
    from . import content as K
except ImportError:  # pragma: no cover
    import checks as C
    import content as K

# Every output Imprint draws with this engine is a canvas of fixed pixels the model lays out itself.
FORMATS = {
    "deck": {"w": 1920, "h": 1080, "min": 26, "multi": True, "label": "slide", "body_px": 30},
    "onepager": {"w": 816, "h": 1056, "min": 12, "multi": False, "label": "page (US Letter at 96 px to the inch)", "body_px": 14},
    "graphic": {"w": 1080, "h": 1350, "min": 24, "multi": False, "label": "4:5 information graphic", "body_px": 30},
}
W, H = FORMATS["deck"]["w"], FORMATS["deck"]["h"]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ---------------------------------------------------------------- 1. sanitize --

_HTML_TAGS = {"div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "b", "i", "br", "hr",
              "blockquote", "cite", "figure", "figcaption", "section", "header", "footer", "main", "aside", "small", "sup",
              "sub", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col", "img", "dl", "dt",
              "dd", "style", "mark", "abbr", "time"}
_SVG_TAGS = {"svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "tspan", "title", "desc",
             "defs", "lineargradient", "radialgradient", "stop", "clippath", "mask", "pattern", "marker", "symbol"}
_DROP_WITH_CONTENT = {"script", "iframe", "frame", "frameset", "object", "embed", "applet", "template", "noscript", "foreignobject",
                      "audio", "video", "canvas", "math", "head", "title_html"}
_SVG_VOID = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "stop"}
_VOID = {"br", "hr", "img", "col"} | _SVG_VOID
_ATTRS = {"class", "id", "style", "role", "alt", "lang", "colspan", "rowspan", "scope", "width", "height", "src",
          # svg presentation and geometry
          "viewbox", "preserveaspectratio", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "d", "points",
          "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
          "stroke-dasharray", "stroke-dashoffset", "stroke-opacity", "opacity", "transform", "text-anchor",
          "dominant-baseline", "font-family", "font-size", "font-weight", "font-style", "letter-spacing", "offset",
          "stop-color", "stop-opacity", "gradientunits", "gradienttransform", "xmlns", "clip-path", "dx", "dy",
          "vector-effect", "marker-end", "marker-start", "patternunits", "textlength"}
_URL = re.compile(r"url\s*\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
_BAD_CSS = re.compile(r"@import|expression\s*\(|javascript:|vbscript:|behavior\s*:|-moz-binding|@namespace|@font-face|image-set\s*\(|"
                      r"element\s*\(|cross-fade\s*\(|attr\s*\(|src\s*:", re.I)
_DATA_IMG = re.compile(r"^data:image/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)
_LOGO = "imprint:logo"


_CONTENT = re.compile(r"(?<![\w-])content\s*:\s*([^;}]*)", re.I)
_CONTENT_OK = re.compile(r"""^\s*(?:none|normal|(?:(?:"[^"\d]*"|'[^'\d]*'|open-quote|close-quote|no-open-quote|no-close-quote)\s*)+)\s*(?:!important\s*)?$""", re.I)
_COUNTER_USE = re.compile(r"\bcounters?\s*\(", re.I)
_COUNTER_PROP = re.compile(r"counter-(?:reset|set|increment)\s*:[^;}]*;?", re.I)


def _forbidden(css: str) -> Optional[str]:
    """Why ``css`` is not allowed, or ``None``. Checked on the text as written: a block is kept whole or dropped whole, never
    rewritten, so there is no decoded copy to write out and no deletion that can rebuild a forbidden word."""
    if "\\" in css:
        return "a backslash escape"
    if "<" in css:
        return "'<'"
    m = _BAD_CSS.search(css)
    if m:
        return m.group(0).strip()
    if _COUNTER_USE.search(css) or _COUNTER_PROP.search(css):
        return "a counter"
    for c in _CONTENT.finditer(css):
        if not _CONTENT_OK.match(c.group(1)):
            return "content other than none or a plain string with no digit"
    for m in _URL.finditer(css):
        u = m.group(2).strip()
        if not (u.startswith("#") or u == _LOGO):
            return f"a picture or address ({u[:40]})"
    return None


def _clean_css(css: str, removed: list, where: str) -> str:
    """The style text as written (comments removed), or nothing: any CSS escape, ``<``, fetching or running construct,
    counter, or ``content`` other than none, normal, quote keywords or a plain string with no digit drops the whole block.
    ``url()`` survives only for an inline picture, a fragment (``#gradient``) or the logo."""
    css = re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)
    why = _forbidden(css)
    if why:
        removed.append(f"{where}: CSS dropped ({why})")
        return ""
    return css


class _Clean(HTMLParser):
    def __init__(self, removed: list):
        super().__init__(convert_charrefs=True)
        self.out: list = []
        self.removed = removed
        self.skip = 0          # depth inside a tag dropped with its content
        self.svg = 0           # depth inside <svg>: a <style> there parses differently, so it is never kept
        self.in_style = False
        self.style_buf: list = []

    # attributes ---------------------------------------------------------
    def _attrs(self, tag, attrs):
        keep = []
        for k, v in attrs:
            k = (k or "").lower()
            v = "" if v is None else v
            if k.startswith("on"):
                self.removed.append(f"<{tag}>: event handler {k}")
                continue
            if k.startswith("data-") or k.startswith("aria-"):
                keep.append((k, v))
                continue
            if k in ("href", "xlink:href", "action", "formaction", "srcset", "poster", "background", "ping", "target", "rel"):
                self.removed.append(f"<{tag}>: {k}={v[:40]!r}")
                continue
            if k == "src":
                if tag == "img" and v == _LOGO:
                    keep.append((k, v.strip()))
                else:
                    self.removed.append(f"<{tag}>: picture from {v[:40]!r}")
                continue
            if k == "style":
                v = _clean_css(v, self.removed, f"<{tag}> style")
                keep.append((k, v))
                continue
            if k in _ATTRS:
                if re.search(r"javascript:|vbscript:|url\s*\(\s*['\"]?(?!#)", v, re.I):
                    self.removed.append(f"<{tag}>: {k} with an address")
                    continue
                keep.append((k, v))
            # anything else (an unknown attribute) is dropped without comment
        return keep

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip:
            if tag not in _VOID:
                self.skip += 1
            return
        if tag in _DROP_WITH_CONTENT:
            self.removed.append(f"<{tag}> element and everything in it")
            if tag not in _VOID:
                self.skip = 1
            return
        if tag == "style":
            if self.svg:
                self.removed.append("<style> inside <svg> element and everything in it")
                self.skip = 1
                return
            self.in_style = True
            self.style_buf = []
            return
        if tag not in _HTML_TAGS and tag not in _SVG_TAGS:
            self.removed.append(f"<{tag}> tag (its text is kept)")
            return
        if tag == "svg":
            self.svg += 1
        at = "".join(f' {k}="{_html.escape(v, quote=True)}"' for k, v in self._attrs(tag, attrs))
        self.out.append(f"<{tag}{at}/>" if tag in _SVG_VOID else f"<{tag}{at}>")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self.skip or tag in _DROP_WITH_CONTENT:
            if tag in _DROP_WITH_CONTENT and not self.skip:
                self.removed.append(f"<{tag}> element and everything in it")
            return
        if tag == "style":
            return
        if tag not in _HTML_TAGS and tag not in _SVG_TAGS:
            self.removed.append(f"<{tag}> tag (its text is kept)")
            return
        at = "".join(f' {k}="{_html.escape(v, quote=True)}"' for k, v in self._attrs(tag, attrs))
        self.out.append(f"<{tag}{at}/>" if tag in _SVG_VOID else (f"<{tag}{at}>" if tag in _VOID else f"<{tag}{at}></{tag}>"))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            self.skip -= 1
            return
        if tag == "style":
            if self.in_style:
                self.out.append("<style>" + _clean_css("".join(self.style_buf), self.removed, "<style>") + "</style>")
            self.in_style = False
            return
        if tag in _VOID or (tag not in _HTML_TAGS and tag not in _SVG_TAGS):
            return
        if tag == "svg":
            self.svg = max(0, self.svg - 1)
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_style:
            self.style_buf.append(data)
            return
        self.out.append(_html.escape(data, quote=False))

    def handle_comment(self, data):
        pass  # comments can hide conditional markup

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass


def sanitize(markup: str) -> tuple:
    """``(clean markup, what was removed)`` for the model's slide markup. The result holds only allowed tags and
    attributes, no script, no event handler, no link, no form, no frame, no address a browser could fetch."""
    removed: list = []
    p = _Clean(removed)
    p.feed(markup or "")
    p.close()
    out = "".join(p.out)
    # A second pass must change nothing: markup whose meaning shifts when it is read again is not kept.
    p2 = _Clean([])
    p2.feed(out)
    p2.close()
    if "".join(p2.out) != out or "</style" in re.sub(r"<style>.*?</style>", "", out, flags=re.S).lower():
        removed.append("markup that does not parse the same way twice was dropped")
        return "", list(dict.fromkeys(removed))
    return out, list(dict.fromkeys(removed))


# ---------------------------------------------------------------- 2. trace --

_REFS = re.compile(r"P\d+")


class _Walk(HTMLParser):
    """Visible text of a slide, each run tagged with the passage ids of its nearest ``data-source`` ancestor, plus every
    ``data-value`` (a chart mark's number, which no one reads as text)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list = []   # (tag, refs or None)
        self.runs: list = []    # (refs, text)
        self.values: list = []  # (refs, value)
        self.hidden = 0

    def _refs(self):
        for _t, r in reversed(self.stack):
            if r is not None:
                return r
        return []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        refs = _REFS.findall(a.get("data-source") or "") if "data-source" in a else None
        if tag not in _VOID:
            self.stack.append((tag, refs))
        if "data-value" in a:
            self.values.append((refs if refs is not None else self._refs(), a["data-value"]))
        if tag in ("style", "title", "desc"):
            self.hidden += 1

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if "data-value" in a:
            refs = _REFS.findall(a.get("data-source") or "") if "data-source" in a else self._refs()
            self.values.append((refs, a["data-value"]))

    def handle_endtag(self, tag):
        if tag in ("style", "title", "desc"):
            self.hidden = max(0, self.hidden - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        self.runs.append((self._refs(), data))


def _sentences(runs: list) -> list:
    """Adjacent runs under the same refs are joined, so "$" + "640,000" is one claim and one check."""
    out: list = []
    for refs, text in runs:
        if out and out[-1][0] == refs:
            out[-1][1] += " " + text
        else:
            out.append([refs, text])
    return [(r, " ".join(t.split())) for r, t in out]


def _spelled(text: str, refs: list, passages: dict) -> list:
    """Numbers written as words ("twelve weeks", "in half") are claims too: each must be in a passage the element cites.
    The shared checker lets a spelled number pass unchecked in prose; a designed slide has no such room."""
    out = []
    held = set()
    for r in refs:
        held |= C._num_set((passages.get(r) or {}).get("text", ""))
    for raw, value, a, b in K.spelled_spans(text):
        if C.is_date_number(text, a, b) or value in ("1", "1/2") and raw.lower() in ("one", "half"):
            continue
        if value in held or any(C.same_value(value, h) for h in held):
            continue
        elsewhere = [pid for pid, v in passages.items() if value in C._num_set(v.get("text", ""))]
        out.append({"value": raw, "status": "moved" if elsewhere else "missing", "ref": elsewhere[0] if elsewhere else None})
    return out


def trace(slides: list, passages: dict) -> dict:
    """Check every slide. ``slides`` is ``[{"html": clean markup, ...}]``; ``passages`` is ``{"P3": {"text": ...}}``.

    Returns ``{"ok", "counts", "items", "flags"}``. ``items`` lists every number found with the slide, the text it sits
    in, the passage ids it is cited to and its status (``exact``, ``computed``, ``moved``, ``missing``, ``unsourced``).
    ``unsourced`` is a number in an element that cites nothing; ``moved`` is cited elsewhere in the corpus (the ref is
    added, and it is a flag: the element should name the passage it really came from)."""
    items, flags = [], []
    for si, sl in enumerate(slides, 1):
        w = _Walk()
        w.feed(sl.get("html") or "")
        own = re.compile(rf"0?{si}(?:\s*(?:/|of)\s*{len(slides)})?")
        runs = [(r, t) for r, t in w.runs if not own.fullmatch(t.strip())]  # the slide's own number is not a claim
        for refs, text in _sentences(runs):
            refs = [r for r in refs if r in passages]
            res = C.check_line(text, refs, passages, all_ids=list(passages.keys()))
            for it in res["items"] + _spelled(text, refs, passages):
                row = {"slide": si, "text": text[:140], "value": it["value"], "status": it["status"], "refs": list(refs),
                       "found_in": it.get("ref")}
                if not refs and it["status"] in ("moved", "missing"):
                    row["status"] = "unsourced"
                if row["status"] in ("moved", "unsourced", "missing"):
                    flags.append(row)
                items.append(row)
        for refs, val in w.values:
            refs = [r for r in refs if r in passages]
            res = C.check_line(val, refs, passages, all_ids=list(passages.keys()))
            if not res["ok"] and re.fullmatch(r"\d+(?:\.\d+)?", val.strip()):  # a mark's bare 68 may be the 68% a passage spells out
                alt = C.check_line(val.strip() + "%", refs, passages, all_ids=list(passages.keys()))
                if alt["ok"]:
                    res = alt
            for it in res["items"]:
                st = it["status"] if refs else ("unsourced" if it["status"] in ("moved", "exact", "computed") else "missing")
                row = {"slide": si, "text": f"data-value={val}", "value": it["value"], "status": st, "refs": list(refs),
                       "found_in": it.get("ref")}
                if st in ("moved", "unsourced", "missing"):
                    flags.append(row)
                items.append(row)
    counts: dict = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {"ok": not flags, "counts": counts, "items": items, "flags": flags}


# ---------------------------------------------------------------- 3. page and render --

def _b64(path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def kit_css(brand: dict, kind: str = "deck") -> str:
    """The brand as CSS: bundled faces as ``data:`` fonts and the colours as variables on ``:root``. ``brand`` is
    ``{"fonts": [{"family", "weight", "style", "file"}], "vars": {"--teal": "#0e5e6f"}, "heading": "...", "body": "..."}``."""
    faces = []
    for f in brand.get("fonts") or []:
        faces.append("@font-face{font-family:'%s';font-weight:%s;font-style:%s;src:url(data:font/ttf;base64,%s) format('truetype');}"
                     % (f["family"], f.get("weight", 400), f.get("style", "normal"), _b64(f["file"])))
    v = "".join(f"{k}:{val};" for k, val in (brand.get("vars") or {}).items())
    W, H = FORMATS[kind]["w"], FORMATS[kind]["h"]
    return ("".join(faces) + f":root{{{v}--font-heading:'{brand.get('heading', 'Montserrat')}',Arial,sans-serif;"
            f"--font-body:'{brand.get('body', 'Lora')}',Georgia,serif;}}"
            "*{box-sizing:border-box;margin:0;padding:0}html,body{background:#888}"
            f".slide{{width:{W}px;height:{H}px;position:relative;overflow:hidden;font-family:var(--font-body);"
            "-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;page-break-after:always;break-after:page}"
            f"@page{{size:{W}px {H}px;margin:0}}@media print{{html,body{{background:none}}}}")


_MEASURE = r"""
(function(){
 var out=[],floor=%d;
 document.querySelectorAll('.slide').forEach(function(s,si){
  var sr=s.getBoundingClientRect(), i=si+1;
  s.querySelectorAll('*').forEach(function(e){
   var t=e.tagName.toLowerCase(); if(t==='style'||t==='br') return;
   var r=e.getBoundingClientRect(); if(r.width<1||r.height<1) return;
   var own=''; for(var n=e.firstChild;n;n=n.nextSibling) if(n.nodeType===3) own+=n.textContent;
   own=own.trim();
   var cs=getComputedStyle(e);
   if(r.right>sr.right+2||r.bottom>sr.bottom+2||r.left<sr.left-2||r.top<sr.top-2)
     out.push({slide:i,kind:'outside',what:(own||t).slice(0,50)});
   if(own && e.scrollHeight>e.clientHeight+3 && cs.overflow!=='visible' && t!=='svg')
     out.push({slide:i,kind:'cut',what:own.slice(0,50)});
   if(own && e.scrollWidth>e.clientWidth+3 && cs.overflow!=='visible' && t!=='svg' && cs.display!=='inline')
     out.push({slide:i,kind:'cut-sideways',what:own.slice(0,50)});
   var fs=parseFloat(cs.fontSize);
   if(own && t!=='text' && !e.closest('svg') && fs<floor) out.push({slide:i,kind:'small',what:own.slice(0,40)+' ('+Math.round(fs)+'px)'});
   if(own && e.closest('svg') && t==='text'){var sc=e.getBoundingClientRect().height; if(sc<floor*0.62) out.push({slide:i,kind:'small',what:own.slice(0,40)+' (chart text)'});}
  });
  // two text blocks drawn over each other
  var boxes=[]; s.querySelectorAll('h1,h2,h3,p,li,td,th,figcaption,blockquote,cite,span,div,text').forEach(function(e){
    var own=''; for(var n=e.firstChild;n;n=n.nextSibling) if(n.nodeType===3) own+=n.textContent; own=own.trim(); if(!own) return;
    var rg=document.createRange(); rg.selectNodeContents(e); var rs=rg.getClientRects(); if(!rs.length) return;
    var b=rg.getBoundingClientRect(); boxes.push({b:b,t:own.slice(0,30),e:e});});
  for(var a=0;a<boxes.length;a++)for(var c=a+1;c<boxes.length;c++){
    var p=boxes[a].b,q=boxes[c].b; if(boxes[a].e.contains(boxes[c].e)||boxes[c].e.contains(boxes[a].e)) continue;
    var ox=Math.min(p.right,q.right)-Math.max(p.left,q.left), oy=Math.min(p.bottom,q.bottom)-Math.max(p.top,q.top);
    if(ox>8&&oy>8) out.push({slide:i,kind:'overlap',what:'"'+boxes[a].t+'" (y '+Math.round(p.top)+'-'+Math.round(p.bottom)+') is drawn over "'+boxes[c].t+'" (y '+Math.round(q.top)+'-'+Math.round(q.bottom)+')'});
  }
 });
 // what the browser's own HTML5 parser made of the cleaned markup: anything the allowlist does not name is unsafe
 var okTags=__TAGS__, okAttrs=__ATTRS__;
 document.querySelectorAll('.slide *').forEach(function(e){
   var t=e.localName.toLowerCase(), bad=null;
   if(okTags.indexOf(t)<0) bad='<'+t+'>';
   if(!bad && t==='style' && e.closest('svg')) bad='<style> inside svg';
   if(!bad) for(var k=0;k<e.attributes.length;k++){var a=e.attributes[k].name.toLowerCase();
     if(a.indexOf('data-')===0||a.indexOf('aria-')===0) continue;
     if(okAttrs.indexOf(a)<0){bad=a;break;}}
   if(bad) out.push({slide:1,kind:'unsafe',what:bad});
 });
 var pre=document.createElement('pre'); pre.id='imprint-report'; pre.textContent=JSON.stringify(out); document.body.appendChild(pre);
 console.log('IMPRINTREPORT-__NONCE__:'+JSON.stringify(out)+':ENDREPORT-__NONCE__');
})();
"""


def _script_tag(floor: int = 26, nonce: str = "") -> tuple:
    js = (_MEASURE % floor).replace("__NONCE__", nonce).replace("__TAGS__", json.dumps(sorted(_HTML_TAGS | _SVG_TAGS))).replace("__ATTRS__", json.dumps(sorted(_ATTRS)))
    digest = base64.b64encode(hashlib.sha256(js.encode()).digest()).decode()
    return f"<script>{js}</script>", digest


def page(slides: list, css: str, logo_data_uri: str = "", only: Optional[int] = None, measure: bool = False, kind: str = "deck", nonce: str = "") -> str:
    """A complete page: the brand CSS, the (already sanitized) slides, a policy that lets nothing out."""
    body = []
    for i, sl in enumerate(slides, 1):
        if only and i != only:
            continue
        h = re.sub(r"<\s*/?\s*(?:meta|base|link|script|iframe|object|embed)\b[^>]*>", "", sl.get("html") or "", flags=re.I)
        h = h.replace(f'src="{_LOGO}"', f'src="{logo_data_uri}"' if logo_data_uri else 'src=""')
        h = h.replace(f"url({_LOGO})", f"url({logo_data_uri})" if logo_data_uri else "none")
        body.append(f'<section class="slide" id="s{i}">{h}</section>')
    script, digest = _script_tag(FORMATS[kind]["min"], nonce) if measure else ("", "")
    csp = ("default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; "
           + (f"script-src 'sha256-{digest}'" if measure else "script-src 'none'"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{csp}">'
            f"<title>deck</title><style>{css}</style></head><body>{''.join(body)}{script}</body></html>")


def _chrome(args: list, timeout: int = 120) -> subprocess.CompletedProcess:
    scratch = tempfile.mkdtemp(prefix="imprint-chrome-")
    try:
        return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
                               "--disable-extensions", "--no-default-browser-check", "--force-device-scale-factor=1",
                               f"--user-data-dir={scratch}", *args], capture_output=True, text=True, timeout=timeout)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _read_report(r, nonce: str, i: int) -> list:
    """The measuring script's report for slide ``i``: taken only from a console line of the page (not from anything else Chrome
    printed), only with this render's nonce, and only when there is exactly one. Zero or more than one fails closed: the slide
    is reported unsafe and thrown out, since a missing or doubled report is what a slide trying to hide a problem would cause."""
    pat = re.compile(r"IMPRINTREPORT-" + re.escape(nonce) + r":(.*?):ENDREPORT-" + re.escape(nonce))
    hits = [m.group(1) for line in (r.stderr or "").splitlines() if "CONSOLE" in line for m in pat.finditer(line)]
    if len(hits) != 1:
        return [{"slide": i, "kind": "unsafe", "what": "the page's own report was missing or appeared more than once"}]
    try:
        out = json.loads(hits[0])
        return [dict(p, slide=i) for p in out] if isinstance(out, list) else [{"slide": i, "kind": "unsafe", "what": "the page's report was not a list"}]
    except ValueError:
        return [{"slide": i, "kind": "unsafe", "what": "the page's report was unreadable"}]


def render(slides: list, css: str, out_dir, logo_data_uri: str = "", pdf: bool = True, kind: str = "deck") -> dict:
    """Draw every slide. Writes ``s01.png`` ..., ``deck.pdf`` into ``out_dir``. Returns ``{"png": [...], "pdf": path,
    "problems": [{slide, kind, what}]}`` where problems are what the measuring script found in the drawn page."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    W, H = FORMATS[kind]["w"], FORMATS[kind]["h"]
    work = Path(tempfile.mkdtemp(prefix="imprint-deckhtml-"))
    pngs, problems = [], []
    try:
        for i in range(1, len(slides) + 1):
            f = work / f"s{i}.html"
            nonce = secrets.token_hex(12)  # the slide cannot know it, so it cannot print a report of its own
            f.write_text(page(slides, css, logo_data_uri, only=i, measure=True, kind=kind, nonce=nonce), encoding="utf-8")
            png = out / f"s{i:02d}.png"
            r = _chrome([f"--window-size={W},{H}", "--virtual-time-budget=4000", "--enable-logging=stderr", "--v=0", f"--screenshot={png}", f.as_uri()])
            problems += _read_report(r, nonce, i)
            if png.exists():
                pngs.append(str(png))
        pdf_path = None
        if pdf:
            f = work / "deck.html"
            f.write_text(page(slides, css, logo_data_uri, kind=kind), encoding="utf-8")
            pdf_path = out / "deck.pdf"
            _chrome(["--virtual-time-budget=4000", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", f.as_uri()])
            pdf_path = str(pdf_path) if pdf_path.exists() else None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    seen, uniq = set(), []
    for p in problems:
        k = (p["slide"], p["kind"], p["what"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return {"png": pngs, "pdf": pdf_path, "problems": uniq}


def export_pdf(slides: list, css: str, path, logo_data_uri: str = "", kind: str = "deck") -> str:
    """One PDF of the slides as they stand: vector text, the brand's own fonts embedded, one page per slide."""
    work = Path(tempfile.mkdtemp(prefix="imprint-pdf-"))
    try:
        f = work / "deck.html"
        f.write_text(page(slides, css, logo_data_uri, kind=kind), encoding="utf-8")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _chrome(["--virtual-time-budget=4000", "--no-pdf-header-footer", f"--print-to-pdf={path}", f.as_uri()])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return str(path)


# ---------------------------------------------------------------- 5. pptx --

def pptx(pngs: list, slides: list, path, title: str = "Deck") -> str:
    """The slides as full-bleed pictures, each with its notes and the passages it cites in the notes pane."""
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)  # 13.333 x 7.5 in
    blank = prs.slide_layouts[6]
    for png, sl in zip(pngs, slides):
        s = prs.slides.add_slide(blank)
        s.shapes.add_picture(str(png), 0, 0, prs.slide_width, prs.slide_height)
        refs = sorted({r for m in re.finditer(r'data-source="([^"]*)"', sl.get("html") or "") for r in _REFS.findall(m.group(1))},
                      key=lambda r: int(r[1:]))
        note = (sl.get("notes") or "").strip()
        if refs:
            note += ("\n\n" if note else "") + "Sources: " + ", ".join(refs)
        s.notes_slide.notes_text_frame.text = note
    prs.core_properties.title = title
    prs.save(str(path))
    return str(path)


# ---------------------------------------------------------------- 4. the loop --

SYSTEM = (
    "You are a presentation designer for a premium strategy consultancy. Your decks are shown to boards, funders and "
    "executives. Every slide earns its place: no filler, no overview slide that says nothing. You think in visual "
    "structure (a big figure, a chart drawn to scale, a table, a quote set large), never a wall of text. You write each "
    "slide as HTML and CSS, then you are shown the render and you fix what is wrong with it.")

_RULES_COMMON = """Brand: colour only from the CSS variables listed under BRAND; type only from var(--font-heading) (headlines, figures,
labels) and var(--font-body) (reading text). Pick the exhibit the data wants: one number is a big figure; a comparison is bars
or columns drawn as inline <svg> to scale (a bar's length proportional to its value); several figures with units are a table;
a quote is set large. The headline states the one point as a full sentence in active voice, never a topic label. Numbers over
adjectives, names over categories.

Numbers: every number you write, in text or in a chart label, comes from the CONTENT or a passage under SOURCES, and the
element that holds it (or an ancestor) carries data-source="P1" (several: data-source="P1 P4"). A chart mark carries
data-value="936" and a data-source of its own. If a number is worked out from two others (212 = 1,148 - 936), cite both
passages on that element and say in words what it is ("212 more than the year before"). Never write a number, date, name or
claim the sources do not support. Years and dates need no source.

Nothing may fetch anything: no links, no external images, no external fonts. The logo is <img src="imprint:logo" alt="">."""


def rules(kind: str) -> str:
    f = FORMATS[kind]
    head = (f"Each {'slide' if kind == 'deck' else 'piece'} is one <div> (no <html>, <body> or <script>) on a {f['w']} x {f['h']} pixel "
            f"canvas ({f['label']}) that is already a positioned, clipped box. Lay it out yourself with CSS (grid, flex, absolute "
            f"positioning) in a <style> block that comes first; start every class name with the prefix s1- (deck slides: s1-, s2-, "
            f"and so on) so classes never collide. ")
    if kind == "deck":
        tail = ("Reading text is at least 30px and labels at least 26px. Margins at least 96px. Three or four points at most on a "
                "slide. No two slides share a layout and no side panel repeats. Source in small text (26px) at the foot of a slide "
                "that shows a figure.\n\n")
    elif kind == "onepager":
        tail = ("Reading text 14 to 16px, labels at least 12px. Margins 48px. It is read on paper in ten seconds and then in two "
                "minutes: the top third says the whole case; the rest backs it. Everything fits on the one page; cut words before "
                "you shrink type. The last line of the page, small, is the organisation's required closing line if the BRAND "
                "gives one.\n\n")
    else:
        tail = ("Reading text at least 30px and labels at least 24px. Margins 72px. It is seen as a thumbnail on a phone first: one "
                "headline, one exhibit, one source line, the logo. Nothing else.\n\n")
    return head + tail + _RULES_COMMON


# Three genuinely different ways to lay out the same checked content. Brand-neutral: they name roles, never colours.
DIRECTIONS = {
    "deck": {
        "editorial": {"name": "Editorial", "brief": (
            "Annual-report editorial. Paper ground on most slides, the brand colour for headlines, one dark slide at the open and "
            "one at the close. Headlines left-aligned, large, in heading type, a column of 1100px at most; generous white space; "
            "thin hairline rules instead of boxes; an asymmetrical composition per slide (a 5/12 headline column beside a 7/12 "
            "exhibit, or a headline over a wide exhibit). Figures are set huge and plain with a one-line caption under them. "
            "Charts are quiet: thin bars, direct labels on the bars, no gridlines, no legends. The accent colour is used once per "
            "slide, on the single number that matters. No cards, no tinted panels.")},
        "databoard": {"name": "Data board", "brief": (
            "A board-room data deck. Every slide is built around its exhibit, and the exhibit fills at least half the canvas: a "
            "bar or column chart to scale with axis and value labels, a ruled table with a totals row, a before and after pair, a "
            "ladder of figures. The headline sits in a slim band across the top, the exhibit below it, one 'so what' sentence in "
            "the right margin. Brand colour fills for chart marks and the top band; paper for the ground; the accent for the one "
            "bar or row the argument turns on. Strong grids and consistent baselines. Vary the exhibit from slide to slide "
            "(columns, horizontal bars, table, ledger, a dot matrix of 100).")},
        "statement": {"name": "Statement", "brief": (
            "Keynote statement deck. One idea per slide and almost no furniture. Alternate full-bleed brand-colour slides (paper "
            "text) with paper slides (brand-colour text). Headlines or a single figure at 140 to 320px in heading type, flush left "
            "or centered on a very wide measure, one short line beneath. The quote is a full-slide statement in body italic at "
            "90px. Charts, when needed, are reduced to a single drawn comparison of two or three marks labelled at the same giant "
            "scale. Page number and logo are the only small elements. Fewer words than the other directions; some slides hold "
            "only a number and a phrase.")},
    },
    "onepager": {
        "editorial": {"name": "Editorial", "brief": (
            "A magazine page. A big headline and a two-sentence dek across the top, a single large figure beside the dek, then "
            "two columns of body text in the body face with small heading-face subheads and hairline rules between sections; the "
            "quote pulled out in italic across a column; one small chart in the margin. Paper ground, brand colour for the "
            "headline and rules, the accent once.")},
        "databoard": {"name": "Data board", "brief": (
            "A briefing sheet built on exhibits. A brand-colour band across the top with the headline in paper; directly under "
            "it a row of three or four figures with labels; then a wide bar chart to scale with value labels on the left half "
            "and a ruled table of the numbers on the right half; the request and the next step in a closing strip at the foot. "
            "Strong grid, small caps labels in heading type.")},
        "statement": {"name": "Statement", "brief": (
            "A poster-like page. The upper half is a full-width brand-colour field carrying one giant figure and the point it "
            "proves in one sentence. The lower half is paper with the request stated in a short paragraph, three short evidence "
            "lines each with their own figure at the left, and the next step. Very few words; very large type for the page.")},
    },
    "graphic": {
        "editorial": {"name": "Editorial", "brief": (
            "A quiet magazine plate. Paper ground. Kicker in small heading-face caps, a large headline, a two-line dek, one "
            "chart drawn thin and direct-labelled with the key bar in the accent, the takeaway in italic body face under a "
            "hairline, source line and logo at the foot.")},
        "databoard": {"name": "Data board", "brief": (
            "A chart card. A brand-colour header block with the headline in paper, the chart filling the middle half of the "
            "card with gridlines, axis labels and value labels, a takeaway strip beneath it, source and logo in the footer.")},
        "statement": {"name": "Statement", "brief": (
            "A single-number poster. A brand-colour field. One figure at 380px or more, one line saying what it counts, one "
            "line saying what to do about it, logo at the foot. The comparison it rests on is a single thin bar pair under "
            "the figure, labelled.")},
    },
}


def content_text(doc: dict, kind: str = "deck") -> str:
    """The checked content as plain text for the designer: every point and figure with its passage id."""
    if kind != "deck":
        return json.dumps(doc, ensure_ascii=False, indent=1)
    lines = [f"DECK: {doc.get('title', '')} | {doc.get('subtitle', '')}"]
    for i, s in enumerate(doc.get("slides") or [], 1):
        head = s.get("heading") or s.get("title") or s.get("quote") or ""
        lines.append(f"\nSLIDE {i} ({s.get('type')}): {head}  [cite {' '.join(s.get('refs') or [])}]")
        for k in ("subhead", "who", "note", "text", "cta", "unit"):
            if s.get(k):
                lines.append(f"  {k}: {s[k]}")
        for b in s.get("bars") or []:
            lines.append(f"  bar: {b.get('label')} = {b.get('value')} [{b.get('ref')}]{' (the point of the chart)' if b.get('accent') else ''}")
        for b in s.get("bullets") or []:
            lines.append(f"  point: {b.get('text')}" + (f" | figure {b.get('figure')}" if b.get("figure") else "") + f" [{b.get('ref')}]")
        for f in s.get("figures") or []:
            lines.append(f"  figure: {f.get('value')} | {f.get('label')} | {f.get('context')} [{f.get('ref')}]")
        for r in s.get("rows") or []:
            lines.append(f"  row: {r}")
    return "\n".join(lines)


def write_prompt(brand_text: str, sources_text: str, content: str, direction: str, kind: str = "deck") -> tuple:
    d = DIRECTIONS[kind][direction]
    what = {"deck": "deck (one slide per point unless a slide plainly needs two, or two can share)",
            "onepager": "one-page brief (every section's claim appears; combine and cut wording, never numbers)",
            "graphic": "single information graphic"}[kind]
    body = (f"BRAND\n{brand_text}\n\nCONTENT (the checked points; designed as a {what})\n{content}\n\n"
            f"SOURCES (each paragraph has an id; cite by id)\n{sources_text}\n")
    instr = (f"DESIGN DIRECTION: {d['name']}. {d['brief']}\n\nDesign the {kind} from CONTENT. Keep every number as given and change "
             f"nothing about what the points claim. {rules(kind)}\n\nReturn JSON only: "
             + ('{"slides":[{"html":"<div>...</div>","notes":"what the speaker says, 2 to 3 sentences"}]}' if kind == "deck"
                else '{"slides":[{"html":"<div>...</div>","notes":""}]} with exactly one entry'))
    return SYSTEM, instr, body


def fix_prompt(brand_text: str, sources_text: str, slides: list, report: dict, direction: str, paths: list, kind: str = "deck") -> tuple:
    d = DIRECTIONS[kind][direction]
    lines = [f"slide {p['slide']}: {p['kind']}: {p['what']}" for p in report.get("problems", [])]
    lines += [f"slide {f['slide']}: number {f['value']} is {f['status']} (in: {f['text'][:60]})" for f in report.get("flags", [])]
    body = (f"BRAND\n{brand_text}\n\nSOURCES\n{sources_text}\n\nPROBLEMS FOUND BY MEASURING THE RENDER AND TRACING NUMBERS\n"
            + ("\n".join(lines) or "none") + "\n\nPICTURES OF THE RENDER (open each with the Read tool and look at it)\n"
            + "\n".join(paths) + "\n\nCURRENT MARKUP\n"
            + "\n".join(f"--- slide {i}\n{s['html']}" for i, s in enumerate(slides, 1)))
    instr = (f"DESIGN DIRECTION: {d['name']}. {d['brief']}\n\nLook at the pictures. Fix every problem listed, and anything else you "
             f"can see: text cut off or crowding an edge, weak hierarchy, an empty or crowded area, a layout repeated from "
             f"another slide, a repeated side panel, a chart not drawn to scale, a figure with no source. Change only what needs "
             f"it, keep the numbers and their data-source, and stay in the design direction. {rules(kind)}\n\nReturn JSON only: "
             '{"slides":[{"index":1,"html":"<div>...</div>"}]} with only the entries you changed.')
    return SYSTEM, instr, body


def _image_block(png: str) -> dict:
    """The picture as Imprint's runtime passes an image to the model (the same block the pictures lane uses)."""
    return {"type": "image", "data": Path(png).read_bytes(), "mime_type": "image/png", "file_name": Path(png).name}


def _take(items, slides, removed, replace=False):
    for s in items or []:
        if not isinstance(s, dict) or not isinstance(s.get("html"), str):
            continue
        clean, rm = sanitize(s["html"])
        removed += rm
        notes = s.get("notes") if isinstance(s.get("notes"), str) else ""
        if replace:
            i = s.get("index")
            if isinstance(i, int) and 1 <= i <= len(slides):
                slides[i - 1] = {"html": clean, "notes": slides[i - 1]["notes"]}  # speaker notes are the first draft's
        elif len(slides) < 24:
            slides.append({"html": clean, "notes": notes})


def render_safe(slides: list, css: str, out_dir, logo_data_uri: str = "", kind: str = "deck", pdf: bool = False) -> dict:
    """Draw ``slides``; any slide the browser's own parse finds unsafe is blanked and the deck is drawn again, until the
    pictures and the PDF are of exactly the slides that remain (and that are traced). Never returns stale output."""
    for _ in range(len(slides) + 1):
        result = render(slides, css, out_dir, logo_data_uri, pdf=pdf, kind=kind)
        bad = {p["slide"] for p in result["problems"] if p["kind"] == "unsafe" and slides[p["slide"] - 1]["html"].strip()}
        if not bad:
            break
        for i in bad:
            slides[i - 1]["html"] = ""
    result["problems"] = [p for p in result["problems"] if p["kind"] != "unsafe"] + [
        {"slide": i, "kind": "rejected", "what": "the markup was not accepted (see what was removed); write it again with plain HTML"}
        for i, sl in enumerate(slides, 1) if not sl["html"].strip()]
    return result


HARD = ("overlap", "cut", "cut-sideways", "outside", "small", "rejected")


async def make(llm, brand: dict, brand_text: str, passages: dict, content: str, out_dir, direction: str = "editorial",
               logo_data_uri: str = "", rounds: int = 2, kind: str = "deck", step=None, style_hint: str = "") -> dict:
    """The loop for one design option. ``llm.structured(system=, instructions=, body=, schema=, purpose=, images=)`` is
    Imprint's runtime. Round 0 writes; each later round renders, measures, traces, shows the model its pictures and takes
    its fixes. The markup is sanitized every time it comes back. Hard layout problems (text over text, cut off, outside the
    canvas, type under the floor) earn up to two more rounds past ``rounds``; whatever is left is returned, never hidden.
    ``step(text)`` is told where it is, for a progress line."""
    say = step or (lambda t: None)
    sources_text = "\n\n".join(f"[{k}] {v['text']}" for k, v in passages.items())
    css = kit_css(brand, kind)
    sysm, instr, body = write_prompt(brand_text, sources_text, content, direction, kind)
    if style_hint:
        instr = style_hint + "\n\n" + instr
    say("writing")
    first = await llm.structured(system=sysm, instructions=instr, body=body, schema=None, purpose="htmldeck.write", max_tokens=32000, timeout=480)
    slides, removed = [], []
    _take(first.get("slides"), slides, removed)
    loop = asyncio.get_event_loop()
    result = tr = None
    rnd = 0
    while True:
        say("drawing" if rnd == 0 else f"looking, round {rnd}")
        result = await loop.run_in_executor(None, lambda: render_safe(slides, css, out_dir, logo_data_uri, kind))
        tr = trace(slides, passages)
        report = {"problems": result["problems"], "flags": tr["flags"]}
        hard = any(p["kind"] in HARD for p in result["problems"])
        if rnd >= rounds + (2 if hard else 0) or (rnd >= rounds and not hard) or (rnd > 0 and not result["problems"] and not tr["flags"]):
            break
        rnd += 1
        say(f"fixing, round {rnd}")
        sysm, instr, body = fix_prompt(brand_text, sources_text, slides, report, direction, result["png"], kind)
        fixed = await llm.structured(system=sysm, instructions=instr, body=body, schema=None, purpose="htmldeck.fix",
                                     max_tokens=32000, timeout=480, images=[_image_block(p) for p in result["png"]])
        _take(fixed.get("slides"), slides, removed, replace=True)
    return {"slides": slides, "render": result, "trace": tr, "removed": list(dict.fromkeys(removed)), "rounds": rnd}


def revise_prompt(brand_text: str, sources_text: str, slides: list, instruction: str, report: dict, paths: list, kind: str = "deck") -> tuple:
    lines = [f"slide {p['slide']}: {p['kind']}: {p['what']}" for p in report.get("problems", [])]
    lines += [f"slide {f['slide']}: number {f['value']} is {f['status']} (in: {f['text'][:60]})" for f in report.get("flags", [])]
    body = (f"BRAND\n{brand_text}\n\nSOURCES\n{sources_text}\n\nOPEN PROBLEMS\n" + ("\n".join(lines) or "none")
            + "\n\nPICTURES OF THE CURRENT RENDER (open each with the Read tool if you cannot see them)\n" + "\n".join(paths)
            + "\n\nCURRENT MARKUP\n" + "\n".join(f"--- slide {i}\n{s['html']}" for i, s in enumerate(slides, 1)))
    instr = (f"THE PERSON ASKED: {instruction}\n\nMake that change and nothing else. Keep every other slide, every number and its "
             f"data-source exactly as they are, and keep the look of the slides you change. Fix any open problem that sits on a slide "
             f"you touch. {rules(kind)}\n\nReturn JSON only: "
             '{"slides":[{"index":1,"html":"<div>...</div>"}]} with only the entries you changed.')
    return SYSTEM, instr, body


async def revise(llm, brand_text: str, passages: dict, slides: list, instruction: str, css: str, out_dir, logo_data_uri: str = "",
                 kind: str = "deck", step=None) -> dict:
    """One revision on the slides as they stand: the model changes what was asked, the result is cleaned, drawn and traced."""
    say = step or (lambda t: None)
    sources_text = "\n\n".join(f"[{k}] {v['text']}" for k, v in passages.items())
    loop = asyncio.get_event_loop()
    say("looking")
    cur = await loop.run_in_executor(None, lambda: render_safe(slides, css, out_dir, logo_data_uri, kind))
    report = {"problems": cur["problems"], "flags": trace(slides, passages)["flags"]}
    sysm, instr, body = revise_prompt(brand_text, sources_text, slides, instruction, report, cur["png"], kind)
    say("revising")
    fixed = await llm.structured(system=sysm, instructions=instr, body=body, schema=None, purpose="htmldeck.revise",
                                 max_tokens=32000, timeout=480, images=[_image_block(p) for p in cur["png"]])
    new = [dict(s) for s in slides]
    removed: list = []
    _take(fixed.get("slides"), new, removed, replace=True)
    say("drawing")
    result = await loop.run_in_executor(None, lambda: render_safe(new, css, out_dir, logo_data_uri, kind))
    tr = trace(new, passages)
    changed = [i + 1 for i, (a, b) in enumerate(zip(slides, new)) if a["html"] != b["html"]]
    return {"slides": new, "render": result, "trace": tr, "removed": list(dict.fromkeys(removed)), "changed": changed}


# ---------------------------------------------------------------- mixing and element edits --

_CLASS_ATTR = re.compile(r'class="([^"]*)"')


def scope_classes(markup: str, prefix: str) -> str:
    """Give every class name in a slide the slide's own prefix, in its attributes and in its <style> selectors, so a slide
    from one design can sit beside a slide from another without one's CSS reaching the other."""
    names = {n for m in _CLASS_ATTR.finditer(markup) for n in m.group(1).split()}
    if not names:
        return markup
    names = sorted(names, key=len, reverse=True)
    pat = re.compile(r"(?<![\w-])\.(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])")
    markup = _CLASS_ATTR.sub(lambda m: 'class="' + " ".join(prefix + n for n in m.group(1).split()) + '"', markup)

    def style(m):
        return m.group(1) + pat.sub(lambda k: "." + prefix + k.group(1), m.group(2)) + m.group(3)
    return re.sub(r"(<style>)(.*?)(</style>)", style, markup, flags=re.S)


class _Elements(HTMLParser):
    """Walks the markup and finds the elements that own visible text; optionally rewrites one of them."""

    def __init__(self, target: Optional[int] = None, text: str = ""):
        super().__init__(convert_charrefs=False)
        self.out: list = []
        self.n = -1
        self.target, self.text = target, text
        self.stack: list = []
        self.found: list = []   # {index, tag, text}
        self.hidden = 0
        self._replaced = False

    def handle_starttag(self, tag, attrs):
        self.stack.append({"tag": tag, "idx": None})
        if tag in ("style", "title", "desc"):
            self.hidden += 1
        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in ("style", "title", "desc"):
            self.hidden = max(0, self.hidden - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.hidden or not data.strip() or not self.stack:
            self.out.append(data)
            return
        top = self.stack[-1]
        if top["idx"] is None:
            self.n += 1
            top["idx"] = self.n
            self.found.append({"index": self.n, "tag": top["tag"], "text": " ".join(data.split())})
            if self.target == self.n:
                self.out.append(_html.escape(self.text, quote=False))
                self._replaced = True
                return
        elif self.target == top["idx"]:
            return  # a second text run in the element being replaced
        self.out.append(data)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")


def elements(markup: str) -> list:
    """``[{index, tag, text}]``: every element that owns visible text, in reading order. The index is what ``set_text`` takes."""
    p = _Elements()
    p.feed(markup or "")
    return p.found


def set_text(markup: str, index: int, text: str) -> tuple:
    """The markup with element ``index``'s own text replaced by ``text`` (escaped), cleaned again. ``(markup, changed)``."""
    p = _Elements(index, str(text)[:600])
    p.feed(markup or "")
    if not p._replaced:
        return markup, False
    clean, _rm = sanitize("".join(p.out))
    return clean, bool(clean)
