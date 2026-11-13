"""The HTML deck path: the model writes each slide as HTML and CSS at 1920x1080 and chooses its own exhibits; Letterpress
adds what only it does.

    1. ``sanitize``   the model's markup is untrusted: scripts, event handlers, links, forms, frames, external
                      addresses and anything that can fetch are removed before a browser sees it;
    2. ``trace``      every number in the markup must sit inside an element that carries ``data-source="P3 P7"`` (the
                      passage ids it is cited to), and must be found in, or worked out from two numbers in, those
                      passages (the same ``checks.check_line`` every other Letterpress output uses). Chart marks carry
                      ``data-value`` and are traced the same way. Unsupported numbers come back as flags;
    3. ``render``     headless Chrome draws every slide (a screenshot per slide, one PDF), measures what the model
                      cannot see (text cut off, boxes outside the slide, type under the floor) and returns it;
    4. ``make``       the loop: the model writes, Letterpress renders, the model is shown the pictures and the problem
                      list and fixes what it sees, up to ``rounds`` times;
    5. ``pptx``       the slides as full-bleed pictures with the slide's notes and sources in the notes pane.

Chrome runs with its own scratch ``--user-data-dir`` and ``--mute-audio``; the folder is deleted afterward. The page
carries a Content-Security-Policy that allows no network, no script but Letterpress's own measuring script (by hash), and
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
    from . import browser as B
    from . import checks as C
    from . import childenv as CE
    from . import content as K
except ImportError:  # pragma: no cover
    import browser as B
    import checks as C
    import childenv as CE
    import content as K

# Every output Letterpress draws with this engine is a canvas of fixed pixels the model lays out itself.
FORMATS = {
    "deck": {"w": 1920, "h": 1080, "min": 26, "multi": True, "label": "slide", "body_px": 30},
    "onepager": {"w": 816, "h": 1056, "min": 12, "multi": False, "label": "page (US Letter at 96 px to the inch)", "body_px": 14},
    "graphic": {"w": 1080, "h": 1350, "min": 24, "multi": False, "label": "4:5 information graphic", "body_px": 30},
}
W, H = FORMATS["deck"]["w"], FORMATS["deck"]["h"]
# Kept for callers and tests that ask "is there a browser": the one found at import, else the usual Mac path.
CHROME = B.find() or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class NoBrowser(ValueError):
    """No Chrome, Chromium, Edge or Brave could be found. The message says what to do."""


def browser_path() -> str:
    """The browser to draw with, looked up now (so installing one, or setting LETTERPRESS_BROWSER, works without a restart)."""
    got = B.find()
    if not got:
        raise NoBrowser(B.NOT_FOUND)
    return got


def browser_available() -> bool:
    return B.find() is not None

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
_LOGO = "letterpress:logo"
_LOGO_BAND = "letterpress:logo-band"  # the logo as it goes on a brand-colour ground (the reversed or knocked-out mark)
_EARLIER_LOGO = "imprint:logo"  # the token in designs made before the rename (also the start of its -band form)


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
        if not (u.startswith("#") or u in (_LOGO, _LOGO_BAND)):
            return f"a picture or address ({u[:40]})"
    return None


def _clean_css(css: str, removed: list, where: str) -> str:
    """The style text as written (comments removed), or nothing: any CSS escape, ``<``, fetching or running construct,
    counter, or ``content`` other than none, normal, quote keywords or a plain string with no digit drops the whole block.
    ``url()`` survives only for an inline picture, a fragment (``#gradient``) or the logo."""
    css = re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)
    why = _forbidden(css)
    if not why:
        return css
    if "\\" not in css and "<" not in css:
        # One bad rule (a page number drawn with content:attr(), say) used to cost the slide its whole stylesheet, leaving
        # bare unstyled text. Keep the rules that pass on their own, each exactly as written, and drop the rest; the joined
        # text is checked again as a whole, so nothing the cut leaves behind can add up to a forbidden construct.
        kept, bad = [], []
        for rule in _top_rules(css):
            (bad if _forbidden(rule) else kept).append(rule)
        joined = "".join(kept)
        if kept and not _forbidden(joined):
            removed.append(f"{where}: {len(bad)} CSS rule{'s' if len(bad) != 1 else ''} dropped ({why})")
            return joined
    removed.append(f"{where}: CSS dropped ({why})")
    return ""


def _top_rules(css: str) -> list:
    """``css`` cut into its top-level rules (a selector and its block, or an @-block with what it nests), each exactly as
    written. Unbalanced braces give one piece, the whole text, so a broken sheet is judged whole."""
    out, depth, start = [], 0, 0
    quote = ""
    for i, ch in enumerate(css):
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return [css]
            if depth == 0:
                out.append(css[start:i + 1])
                start = i + 1
    if depth or quote or css[start:].strip():
        return [css]
    return out


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
                if tag == "img" and v in (_LOGO, _LOGO_BAND):
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
    p.feed((markup or "").replace(_EARLIER_LOGO, _LOGO))
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
  // a small shape with no text (a chart dot, a marker) drawn over text: a dot grid that spills onto its caption.
  // Text placed wholly inside a shape (a label in a badge) is on purpose and passes.
  var slideArea=sr.width*sr.height, shapes=0;
  s.querySelectorAll('div,span,i,b,circle,rect,ellipse,path,polygon').forEach(function(e){
    if(shapes>=6) return;
    if(e.textContent.trim()) return;
    var r=e.getBoundingClientRect(); if(r.width<4||r.height<4) return;
    if(r.width*r.height>slideArea*0.004) return;
    var t=e.tagName.toLowerCase(), cs=getComputedStyle(e);
    var painted=(t!=='div'&&t!=='span'&&t!=='i'&&t!=='b')||(cs.backgroundColor&&cs.backgroundColor!=='rgba(0, 0, 0, 0)'&&cs.backgroundColor!=='transparent')||cs.backgroundImage!=='none';
    if(!painted||cs.visibility==='hidden'||parseFloat(cs.opacity)===0) return;
    for(var k=0;k<boxes.length;k++){
      var q=boxes[k].b; if(boxes[k].e.contains(e)) continue;
      if(q.left>=r.left-1&&q.right<=r.right+1&&q.top>=r.top-1&&q.bottom<=r.bottom+1) continue;
      var ox=Math.min(r.right,q.right)-Math.max(r.left,q.left), oy=Math.min(r.bottom,q.bottom)-Math.max(r.top,q.top);
      if(ox>6&&oy>6&&ox*oy>r.width*r.height*0.25){
        out.push({slide:i,kind:'overlap',what:'a shape (y '+Math.round(r.top)+'-'+Math.round(r.bottom)+') is drawn over "'+boxes[k].t+'" (y '+Math.round(q.top)+'-'+Math.round(q.bottom)+')'});
        shapes++; break;
      }
    }
  });
  // a slide left mostly empty. Everything drawn (text, chart marks, painted panels; the ground, the logo and small foot
  // lines in the bottom quarter aside) is taken as vertical bands. Flagged: the lower part under the last band is empty
  // (more than 30%% of the height), or, on a slide with no statement-size figure, a band of more than 30%% of the height
  // inside the composition is empty, or everything together covers under 30%% of the height. Only measured for decks.
  if(__FILL__){
    var H0=sr.height, iv=[], big=0, labels=[];
    s.querySelectorAll('*').forEach(function(e){
      var t=e.tagName.toLowerCase(); if(t==='style'||t==='br'||t==='svg'||t==='g'||t==='defs'||t==='tspan') return;
      var r=e.getBoundingClientRect(); if(r.width<2||r.height<2) return;
      var own=''; for(var n2=e.firstChild;n2;n2=n2.nextSibling) if(n2.nodeType===3) own+=n2.textContent; own=own.trim();
      var cs=getComputedStyle(e);
      var shape=(t==='rect'||t==='circle'||t==='ellipse'||t==='path'||t==='line'||t==='polygon'||t==='polyline'||t==='img');
      var painted=!own&&!shape&&cs.backgroundColor&&cs.backgroundColor!=='rgba(0, 0, 0, 0)'&&cs.backgroundColor!=='transparent';
      if(!own&&!shape&&!painted) return;
      if(cs.visibility==='hidden'||parseFloat(cs.opacity)===0) return;
      if((shape||painted)&&r.width>sr.width*0.9&&r.height>sr.height*0.9) return;
      var fs=own?parseFloat(cs.fontSize):0;
      if(own&&fs<=floor+4&&r.top>sr.top+H0*0.75) return;
      if(t==='img'&&r.width<200&&r.height<200) return;
      if(fs>big) big=fs;
      var a=Math.max(0,r.top-sr.top), b=Math.min(H0,r.bottom-sr.top); if(b<=a) return;
      iv.push([a,b,(own||'').slice(0,24)]);
    });
    if(iv.length){
      iv.sort(function(p,q){return p[0]-q[0];});
      var m=[[iv[0][0],iv[0][1],iv[0][2],iv[0][2]]];
      for(var k2=1;k2<iv.length;k2++){var L=m[m.length-1]; if(iv[k2][0]<=L[1]){if(iv[k2][1]>L[1]){L[1]=iv[k2][1]; if(iv[k2][2]) L[3]=iv[k2][2];}} else m.push([iv[k2][0],iv[k2][1],iv[k2][2],iv[k2][2]]);}
      var bot=m[m.length-1][1], cover=0, gap=0, ga='', gb='';
      for(var k3=0;k3<m.length;k3++){cover+=m[k3][1]-m[k3][0]; if(k3&&m[k3][0]-m[k3-1][1]>gap){gap=m[k3][0]-m[k3-1][1]; ga=m[k3-1][3]; gb=m[k3][2];}}
      if(H0-bot>H0*0.30) out.push({slide:i,kind:'empty',what:'everything on the slide ends '+Math.round(100*bot/H0)+'%% of the way down; the lower '+Math.round(100*(H0-bot)/H0)+'%% is empty. Anchor the exhibit or a row of figures to the bottom margin, or set the content larger'});
      else if(big<150&&gap>H0*0.30) out.push({slide:i,kind:'empty',what:'an empty band '+Math.round(100*gap/H0)+'%% of the slide height sits between '+(ga?'"'+ga+'"':'one group')+' and '+(gb?'"'+gb+'"':'the next')+'. Close it up: set the content larger or give the exhibit the space'});
      else if(big<150&&cover<H0*0.30) out.push({slide:i,kind:'empty',what:'the content covers only '+Math.round(100*cover/H0)+'%% of the slide height. Set it larger or spread it to the margins'});
    }
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
 var pre=document.createElement('pre'); pre.id='letterpress-report'; pre.textContent=JSON.stringify(out); document.body.appendChild(pre);
 console.log('LETTERPRESSREPORT-__NONCE__:'+JSON.stringify(out)+':ENDREPORT-__NONCE__');
})();
"""


def _script_tag(floor: int = 26, nonce: str = "", fill: bool = False) -> tuple:
    js = (_MEASURE % floor).replace("__NONCE__", nonce).replace("__FILL__", "true" if fill else "false").replace("__TAGS__", json.dumps(sorted(_HTML_TAGS | _SVG_TAGS))).replace("__ATTRS__", json.dumps(sorted(_ATTRS)))
    digest = base64.b64encode(hashlib.sha256(js.encode()).digest()).decode()
    return f"<script>{js}</script>", digest


def page(slides: list, css: str, logo_data_uri: str = "", only: Optional[int] = None, measure: bool = False, kind: str = "deck", nonce: str = "") -> str:
    """A complete page: the brand CSS, the (already sanitized) slides, a policy that lets nothing out. ``logo_data_uri`` is
    one data URI, or ``{"paper": uri, "band": uri}`` when the kit has a logo for brand-colour grounds."""
    logos = logo_data_uri if isinstance(logo_data_uri, dict) else {"paper": logo_data_uri}
    paper = logos.get("paper") or next((v for v in logos.values() if v), "")
    band = logos.get("band") or paper
    body = []
    for i, sl in enumerate(slides, 1):
        if only and i != only:
            continue
        h = re.sub(r"<\s*/?\s*(?:meta|base|link|script|iframe|object|embed)\b[^>]*>", "", sl.get("html") or "", flags=re.I).replace(_EARLIER_LOGO, _LOGO)
        for tok, uri in ((_LOGO_BAND, band), (_LOGO, paper)):
            h = h.replace(f'src="{tok}"', f'src="{uri}"' if uri else 'src=""')
            h = h.replace(f"url({tok})", f"url({uri})" if uri else "none")
        body.append(f'<section class="slide" id="s{i}">{h}</section>')
    script, digest = _script_tag(FORMATS[kind]["min"], nonce, fill=kind == "deck") if measure else ("", "")
    csp = ("default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; "
           + (f"script-src 'sha256-{digest}'" if measure else "script-src 'none'"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{csp}">'
            f"<title>deck</title><style>{css}</style></head><body>{''.join(body)}{script}</body></html>")


def _chrome(args: list, timeout: int = 120) -> subprocess.CompletedProcess:
    exe = browser_path()  # before any scratch folder is made, so a missing browser leaves nothing behind
    scratch = tempfile.mkdtemp(prefix="letterpress-chrome-")
    try:
        return subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
                               "--disable-extensions", "--no-default-browser-check", "--force-device-scale-factor=1",
                               f"--user-data-dir={scratch}", *args], capture_output=True, text=True, timeout=timeout,
                              env=CE.child_env(),  # only the allowlisted names, never Hermes's keys
                              # with a full path and close_fds=False, subprocess starts the browser with posix_spawn, not fork:
                              # a forked child can crash in a macOS network-framework fork handler (see sitestyle._spawn).
                              # Descriptors stay close-on-exec, so the browser still gets only its own pipes.
                              close_fds=False)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _read_report(r, nonce: str, i: int) -> list:
    """The measuring script's report for slide ``i``: taken only from a console line of the page (not from anything else Chrome
    printed), only with this render's nonce, and only when there is exactly one. Zero or more than one fails closed: the slide
    is reported unsafe and thrown out, since a missing or doubled report is what a slide trying to hide a problem would cause."""
    pat = re.compile(r"LETTERPRESSREPORT-" + re.escape(nonce) + r":(.*?):ENDREPORT-" + re.escape(nonce))
    hits = [m.group(1) for line in (r.stderr or "").splitlines() if "CONSOLE" in line for m in pat.finditer(line)]
    if len(hits) != 1:
        return [{"slide": i, "kind": "unsafe", "what": "the page's own report was missing or appeared more than once"}]
    try:
        out = json.loads(hits[0])
        return [dict(p, slide=i) for p in out] if isinstance(out, list) else [{"slide": i, "kind": "unsafe", "what": "the page's report was not a list"}]
    except ValueError:
        return [{"slide": i, "kind": "unsafe", "what": "the page's report was unreadable"}]


RENDER_WORKERS = 4  # slides drawn at the same time; each is its own short-lived browser with its own scratch folder


def render(slides: list, css: str, out_dir, logo_data_uri: str = "", pdf: bool = True, kind: str = "deck", only=None) -> dict:
    """Draw every slide. Writes ``s01.png`` ..., ``deck.pdf`` into ``out_dir``. Returns ``{"png": [...], "pdf": path,
    "problems": [{slide, kind, what}]}`` where problems are what the measuring script found in the drawn page.
    ``only`` (slide numbers) draws just those slides, for a fix round that changed a few; the PDF is made only for a full draw."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    W, H = FORMATS[kind]["w"], FORMATS[kind]["h"]
    work = Path(tempfile.mkdtemp(prefix="letterpress-deckhtml-"))
    pngs, problems = [], []
    wanted = sorted(set(range(1, len(slides) + 1)) if only is None else {i for i in only if 1 <= i <= len(slides)})
    exe = browser_path()

    def draw(i: int):
        f = work / f"s{i}.html"
        nonce = secrets.token_hex(12)  # the slide cannot know it, so it cannot print a report of its own
        f.write_text(page(slides, css, logo_data_uri, only=i, measure=True, kind=kind, nonce=nonce), encoding="utf-8")
        png = out / f"s{i:02d}.png"
        r = _chrome([f"--window-size={W},{H}", "--virtual-time-budget=4000", "--enable-logging=stderr", "--v=0", f"--screenshot={png}", f.as_uri()])
        return i, png, _read_report(r, nonce, i)

    try:
        if len(wanted) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(RENDER_WORKERS, len(wanted))) as ex:
                drawn = list(ex.map(draw, wanted))  # in slide order, whatever order they finish in
        else:
            drawn = [draw(i) for i in wanted]
        for i, png, rep in drawn:
            problems += rep
            if png.exists():
                pngs.append(str(png))
        pdf_path = None
        if pdf and only is None:
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
    work = Path(tempfile.mkdtemp(prefix="letterpress-pdf-"))
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

Nothing may fetch anything: no links, no external images, no external fonts. The logo is <img src="letterpress:logo" alt="">."""


def rules(kind: str) -> str:
    f = FORMATS[kind]
    head = (f"Each {'slide' if kind == 'deck' else 'piece'} is one <div> (no <html>, <body> or <script>) on a {f['w']} x {f['h']} pixel "
            f"canvas ({f['label']}) that is already a positioned, clipped box. Lay it out yourself with CSS (grid, flex, absolute "
            f"positioning) in a <style> block that comes first; start every class name with the prefix s1- (deck slides: s1-, s2-, "
            f"and so on) so classes never collide. ")
    if kind == "deck":
        tail = ("Reading text is at least 30px and labels at least 26px. Margins at least 96px. Three or four points at most on a "
                "slide. No two slides share a layout and no side panel repeats. Source in small text (26px) at the foot of a slide "
                "that shows a figure. A title slide in CONTENT is always its own first slide (the DECK title, its subtitle, the "
                "logo); never fold it into another slide. The logo always stands out from the ground behind it; on a "
                "brand-colour ground never put it in a white box. Every word on a slide is text in the markup: never draw text, a "
                "slide number or a figure with CSS content, attr() or a counter (they are removed).\n\n"
                "Type scale: a slide uses at most four sizes, each at least 1.5 times the one below it, taken from this ladder: "
                "label 26, reading 30 to 34, deck line 44 to 52, headline 64 to 96, figure 160 to 400. Two sizes that are nearly the "
                "same (30 beside 36) read as a mistake. The headline is always the largest words on a slide; only a figure may be "
                "larger.\n\n"
                "Use the whole slide. The composition reaches all four margins: something is anchored to the bottom margin (the "
                "exhibit's baseline, a row of figures, a rule with the source line under it), never a headline and a few lines at "
                "the top over an empty lower half. White space is placed between groups, not left over under them. If a slide's "
                "content is thin, set it larger, not smaller. A slide whose content stops above the middle will be sent back.\n\n"
                "Text never touches a rule or a panel edge: keep at least 32px between a line of type and a rule above or below it.\n\n"
                "Charts make the point, not just the numbers: bars at least 64px thick, value labels in heading type at deck-line "
                "size or larger and heavier than category labels, the one mark the argument turns on in the accent, and the gap or "
                "change the headline claims drawn and labelled on the chart (a bracket or a rule with '212 more'). Two different "
                "measures (enrolled, waiting) never share one row of bars without a clear break and its own label. Two values "
                "within a fifth of each other are not a bar pair: show the difference as the figure and the two values as its "
                "caption.\n\n")
    elif kind == "onepager":
        tail = ("Reading text 14 to 16px, labels at least 12px. Margins 48px. It is read on paper in ten seconds and then in two "
                "minutes: the top third says the whole case; the rest backs it. Everything fits on the one page; cut words before "
                "you shrink type. The last line of the page, small, is the organisation's required closing line if the BRAND "
                "gives one. Two values within a fifth of each other (a budget against last year's spending) are not a bar pair: "
                "set the difference as the figure and the two values as its caption, or draw a bridge from one to the other with "
                "the difference as the labelled step.\n\n")
    else:
        tail = ("Reading text at least 30px and labels at least 24px. Margins 72px. It is seen as a thumbnail on a phone first: one "
                "headline, one exhibit, one source line, the logo. Nothing else.\n\n")
    return head + tail + _RULES_COMMON


# Three genuinely different ways to lay out the same checked content. Brand-neutral: they name roles, never colours.
DIRECTIONS = {
    "deck": {
        "editorial": {"name": "Editorial", "brief": (
            "A magazine feature, set like a printed annual report. THE HEADLINES ARE IN THE BODY FACE (var(--font-body), the "
            "serif), regular weight, 72 to 96px, tight leading (1.05), brand colour or ink; the heading face is kept for "
            "figures, small caps labels (26px, letter-spacing .12em, uppercase) and chart labels. This is what sets this "
            "option apart: it reads as typeset, not as slideware. Paper ground on every slide except the title and the close, "
            "which are full-bleed brand colour with paper type. A 12-column grid with a 96px margin: a narrow left rail (2 "
            "columns) carries a small caps kicker and the slide number over a short accent rule; the headline runs across "
            "columns 3 to 10; the exhibit sits below it on a baseline anchored to the bottom margin. Hairline rules (1 to 2px, "
            "var(--rule)) organise the page; no boxes, no cards, no tinted panels, no bands. Figures are set huge and plain "
            "(200px and up) with a one-line serif caption. Charts are quiet but large: thick plain bars, direct labels, no "
            "gridlines, no legend. The quote is body italic at 76px or more across ten columns with a hanging opening mark. "
            "The accent colour appears on exactly one element per slide, the single number that matters; every other figure is brand colour or ink. Figures are set in the body face too "
            "(lining numerals, regular or semibold) at 200 to 320px, so the whole deck reads as one typeset serif page; the heading face only "
            "ever appears at label size. Headlines 80 to 96px. The title slide is the most typographic slide in the deck: the "
            "deck title at 128 to 160px in the body face, set low across ten columns, the subtitle at 44px under a hairline, "
            "the kicker and the logo small in the left rail. A slide with three or more figures is a ruled table (figure "
            "column, label column, hairline between rows), never a grid of tiles.")},
        "databoard": {"name": "Data board", "brief": (
            "A board-room dashboard. Every slide is a grid of panels and the exhibit is the largest panel, at least half the "
            "canvas: a column chart with an axis line and value labels, a ruled table with a totals row, a before and after "
            "pair, a ladder of figures, a dot matrix of 100 for a percentage. The ground is var(--brand-tint); panels are paper "
            "rectangles with square corners and 40px padding, set on a 24px gutter, so the slide reads as a board of tiles. "
            "There is NO band across the top: the headline is plain heading-face type, 64 to 72px, brand colour, top left, "
            "directly on the tinted ground, with a small caps label above it naming the measure. One narrower panel in "
            "brand-colour fill with paper type holds the 'so what': the one figure or sentence the board should leave with. "
            "All type is the heading face except source lines. Chart marks in brand colour, the comparison mark in "
            "var(--brand-mid), the one bar or row the argument turns on in the accent. Vary the exhibit and the panel "
            "arrangement from slide to slide (wide chart over three figure tiles; tall chart beside a table; four equal "
            "tiles); never the same grid twice in a row. The title slide is a board too: the deck title at 96px on the tinted "
            "ground, then one wide hero tile holding the single figure the whole case rests on (set at 200px or more with its "
            "label) beside a brand-fill tile with the subtitle; never an empty tile and never the logo as a tile of its own. "
            "Where CONTENT gives a slide two points that are one comparison, merge them into one exhibit.")},
        "statement": {"name": "Statement", "brief": (
            "A keynote statement deck: one idea per slide on a plain ground, nothing else. Alternate full-bleed brand-colour "
            "slides (background var(--band), type var(--band-text), logo letterpress:logo-band) with paper slides (background "
            "var(--paper), type var(--brand), logo letterpress:logo); never two of the same ground in a row. Each slide holds at most "
            "four things: one large figure or statement (160 to 320px, var(--font-heading), weight 800, line-height 0.95), one "
            "line of 44 to 52px directly under it saying what it means, the source at 26px on the bottom margin, and the logo. "
            "Set the large element flush left on the 96px margin in the lower half of the slide, like a poster. Where CONTENT "
            "gives a slide several figures, set the one the headline is about large and put the others in the 44px line. A "
            "quote is the large element in var(--font-body) italic at 88px, five lines at most. A chart is at most three thick "
            "bars labelled at 44px. No panels, tiles, boxes, bands, grids or paragraphs, and no slide number. The title slide "
            "sets the deck title at 160 to 200px, three lines at most, low on a brand-colour slide, with the subtitle at 44px.")},
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


def fix_prompt(brand_text: str, sources_text: str, slides: list, report: dict, direction: str, paths: list, kind: str = "deck",
               only=None) -> tuple:
    """``only`` (slide numbers) shows the model just those slides and their pictures: a later round has nothing to say about a
    slide that is already clean, and sending it again costs time. ``paths`` are the pictures of the shown slides, in order."""
    d = DIRECTIONS[kind][direction]
    shown = list(range(1, len(slides) + 1)) if only is None else sorted(only)
    lines = [f"slide {p['slide']}: {p['kind']}: {p['what']}" for p in report.get("problems", [])]
    lines += [f"slide {f['slide']}: number {f['value']} is {f['status']} (in: {f['text'][:60]})" for f in report.get("flags", [])]
    body = (f"BRAND\n{brand_text}\n\nSOURCES\n{sources_text}\n\nPROBLEMS FOUND BY MEASURING THE RENDER AND TRACING NUMBERS\n"
            + ("\n".join(lines) or "none") + "\n\nPICTURES OF THE RENDER (open each with the Read tool and look at it)\n"
            + "\n".join(paths) + "\n\nCURRENT MARKUP\n"
            + "\n".join(f"--- slide {i}\n{slides[i - 1]['html']}" for i in shown))
    if only is None:
        instr = (f"DESIGN DIRECTION: {d['name']}. {d['brief']}\n\nLook at the pictures. Fix every problem listed, and anything else you "
                 f"can see: text cut off or crowding an edge, weak hierarchy, an empty or crowded area, a layout repeated from "
                 f"another slide, a repeated side panel, a chart not drawn to scale, a figure with no source. Change only what needs "
                 f"it, keep the numbers and their data-source, and stay in the design direction. {rules(kind)}\n\nReturn JSON only: "
                 '{"slides":[{"index":1,"html":"<div>...</div>"}]} with only the entries you changed.')
    else:
        nums = ", ".join(str(i) for i in shown)
        instr = (f"DESIGN DIRECTION: {d['name']}. {d['brief']}\n\nThis is a second look. Only slide{'s' if len(shown) > 1 else ''} {nums} "
                 f"still {'have' if len(shown) > 1 else 'has'} a problem; the other slides are fine and are not shown. Look at the "
                 f"{'pictures' if len(shown) > 1 else 'picture'} and fix every problem listed for {'them' if len(shown) > 1 else 'it'}, "
                 f"keeping the look of the design. Change only what needs it, keep the numbers and their data-source, and stay in the "
                 f"design direction. {rules(kind)}\n\nReturn JSON only: "
                 '{"slides":[{"index":1,"html":"<div>...</div>"}]} with only the entries you changed, each with its own slide number as index.')
    return SYSTEM, instr, body


def _image_block(png: str) -> dict:
    """The picture as Letterpress's runtime passes an image to the model (the same block the pictures lane uses)."""
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


def render_safe(slides: list, css: str, out_dir, logo_data_uri: str = "", kind: str = "deck", pdf: bool = False, only=None) -> dict:
    """Draw ``slides``; any slide the browser's own parse finds unsafe is blanked and the deck is drawn again, until the
    pictures and the PDF are of exactly the slides that remain (and that are traced). Never returns stale output.
    With ``only`` (slide numbers) just those slides are drawn and reported: ``png`` and ``problems`` then cover those slides."""
    mine = set(range(1, len(slides) + 1)) if only is None else {i for i in only if 1 <= i <= len(slides)}
    result = render(slides, css, out_dir, logo_data_uri, pdf=pdf, kind=kind, only=only)
    for _ in range(len(slides)):
        bad = {p["slide"] for p in result["problems"] if p["kind"] == "unsafe" and slides[p["slide"] - 1]["html"].strip()}
        if not bad:
            break
        for i in bad:
            slides[i - 1]["html"] = ""
        result = render(slides, css, out_dir, logo_data_uri, pdf=pdf, kind=kind, only=only)
    result["problems"] = [p for p in result["problems"] if p["kind"] != "unsafe"] + [
        {"slide": i, "kind": "rejected", "what": "the markup was not accepted (see what was removed); write it again with plain HTML"}
        for i, sl in enumerate(slides, 1) if i in mine and not sl["html"].strip()]
    return result


HARD = ("overlap", "cut", "cut-sideways", "outside", "small", "rejected")


async def make(llm, brand: dict, brand_text: str, passages: dict, content: str, out_dir, direction: str = "editorial",
               logo_data_uri: str = "", rounds: int = 2, kind: str = "deck", step=None, style_hint: str = "") -> dict:
    """The loop for one design option. ``llm.structured(system=, instructions=, body=, schema=, purpose=, images=)`` is
    Letterpress's runtime. Round 0 writes; each later round renders, measures, traces, shows the model its pictures and takes
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
    out_path = Path(out_dir)
    result = tr = None
    rnd = 0
    changed = None          # slide numbers the last fix changed; None means draw every slide
    prev_hard = None        # hard problems left after the round before
    while True:
        say("drawing" if rnd == 0 else f"looking, round {rnd}")
        drawn = await loop.run_in_executor(None, lambda: render_safe(slides, css, out_dir, logo_data_uri, kind, only=changed))
        if changed is None:
            result = drawn
        else:  # unchanged slides keep the picture and the measurements they already have
            kept = [p for p in result["problems"] if p["slide"] not in changed]
            result = {"png": sorted(str(p) for p in out_path.glob("s[0-9][0-9].png"))[:len(slides)], "pdf": None, "problems": kept + drawn["problems"]}
        tr = trace(slides, passages)
        report = {"problems": result["problems"], "flags": tr["flags"]}
        hard_n = sum(1 for p in result["problems"] if p["kind"] in HARD)
        if rnd > 0 and not result["problems"] and not tr["flags"]:
            break  # nothing left to fix
        if rnd >= rounds:
            # Extra rounds are only for hard layout problems, and only while the last fix was making headway on them.
            if not hard_n or rnd >= rounds + 2 or (prev_hard is not None and hard_n >= prev_hard):
                break
        prev_hard = hard_n
        rnd += 1
        say(f"fixing, round {rnd}")
        if rnd == 1:
            shown = None  # the first look is at the whole piece: the model judges hierarchy, repetition and balance across slides
        else:
            shown = sorted({p["slide"] for p in result["problems"]} | {f["slide"] for f in tr["flags"]})
            shown = [i for i in shown if 1 <= i <= len(slides)] or None
        paths = result["png"] if shown is None else [str(out_path / f"s{i:02d}.png") for i in shown]
        sysm, instr, body = fix_prompt(brand_text, sources_text, slides, report, direction, paths, kind, only=shown)
        n_out = len(slides) if shown is None else len(shown)
        fixed = await llm.structured(system=sysm, instructions=instr, body=body, schema=None, purpose="htmldeck.fix",
                                     max_tokens=min(32000, 6000 + 3500 * n_out), timeout=480, images=[_image_block(p) for p in paths if Path(p).exists()])
        before = [s["html"] for s in slides]
        _take(fixed.get("slides"), slides, removed, replace=True)
        changed = [i + 1 for i, (a, b) in enumerate(zip(before, slides)) if a != b["html"]]
        if not changed:
            break  # the model changed nothing, so another look at the same pictures would say the same
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


# ---------------------------------------------------------------- the guard: a broken design is never offered --

_STYLE_BLOCK = re.compile(r"<style>(.*?)</style>", re.S | re.I)
_INLINE_STYLE = re.compile(r'\sstyle="[^"]*\S[^"]*"', re.I)


def unstyled(markup: str) -> bool:
    """True when a slide has markup but no CSS reaches it: its <style> blocks hold no rule and no element carries a style.
    That is what a slide looks like after its stylesheet was dropped: bare default text in the top-left corner."""
    if not (markup or "").strip():
        return False
    css = "".join(_STYLE_BLOCK.findall(markup))
    outside_svg = re.sub(r"<svg\b.*?</svg>", "", markup, flags=re.S | re.I)  # a styled chart does not lay out the slide's text
    return "{" not in css and not _INLINE_STYLE.search(outside_svg)


def broken(slides: list, problems: list) -> list:
    """Why this design must not be offered as drawn, or ``[]``. Conservative, from what the loop already measures: a slide
    left empty (its markup was rejected), a slide with no styling at all, or hard layout problems at more than two a slide
    (a design that came back right averages well under one)."""
    n = len(slides)
    if not n:
        return ["no slides came back"]
    why = []
    empty = [i for i, s in enumerate(slides, 1) if not (s.get("html") or "").strip()]
    bare = [i for i, s in enumerate(slides, 1) if unstyled(s.get("html") or "")]
    hard = sum(1 for p in problems or [] if p.get("kind") in HARD)
    if empty:
        why.append("slide " + ", ".join(map(str, empty)) + " came back empty")
    if bare:
        why.append("slide " + ", ".join(map(str, bare)) + " has no styling")
    if hard > 2 * n:
        why.append(f"{hard} layout problems on {n} slides")
    return why


_TPL = {  # the built-in layout, in each direction's ground and type, as far as one fixed layout allows
    "editorial": {"ground": lambda i: "paper", "head": "var(--font-body)", "hw": 400, "big": "var(--font-body)", "bw": 400},
    "databoard": {"ground": lambda i: "tint", "head": "var(--font-heading)", "hw": 700, "big": "var(--font-heading)", "bw": 800},
    "statement": {"ground": lambda i: "band" if i % 2 else "paper", "head": "var(--font-heading)", "hw": 800, "big": "var(--font-heading)", "bw": 800},
}
_GROUND = {"paper": ("var(--paper)", "var(--brand)", "var(--ink)", _LOGO), "tint": ("var(--brand-tint)", "var(--brand)", "var(--ink)", _LOGO),
           "band": ("var(--band)", "var(--band-text)", "var(--band-text)", _LOGO_BAND)}


def _tpl_parts(s: dict) -> tuple:
    """``(headline, big figure, its line, other lines, refs)`` from one checked content slide, every number as written."""
    e = _html.escape
    refs = " ".join(s.get("refs") or [])
    head = s.get("heading") or s.get("title") or ""
    big = line = ""
    rest = []
    if s.get("quote"):
        return "", "", e("“" + s["quote"].strip().strip("“”\"") + "”"), [e(s.get("who") or "")] if s.get("who") else [], refs
    if s.get("value"):
        big, line = s["value"], s.get("label") or s.get("context") or ""
    figs = s.get("figures") or []
    if figs and not big:
        big, line = figs[0].get("value") or "", figs[0].get("label") or ""
        rest = [f"{f.get('value', '')} {f.get('label', '')}".strip() for f in figs[1:]]
    bars = s.get("bars") or []
    if bars and not big:
        lead = next((b for b in bars if b.get("accent")), bars[-1])
        big, line = lead.get("value") or "", lead.get("label") or ""
        rest = [f"{b.get('label', '')}: {b.get('value', '')}" for b in bars if b is not lead]
        if s.get("subhead"):
            rest.insert(0, s["subhead"])
    for r in s.get("rows") or []:
        if isinstance(r, dict):
            rest.append(f"{r.get('label', '')}: {r.get('left', '')} → {r.get('right', '')}".strip(": "))
    for b in s.get("bullets") or []:
        rest.append((b.get("text") or "") + (f" ({b['figure']})" if b.get("figure") else ""))
    for k in ("text", "cta"):
        if s.get(k):
            rest.append(s[k])
    if not head and not big:
        head = s.get("subhead") or ""
    return e(head), e(big), e(line), [e(x) for x in rest if x][:5], refs


def template_slides(doc: dict, direction: str = "statement") -> list:
    """The deck as Letterpress's own fixed layout, in ``direction``'s ground and type: a title slide, then one slide per content
    point with its headline, its figure and its lines. No model call. Used only when the drawn design came back broken twice."""
    t = _TPL.get(direction) or _TPL["statement"]
    e = _html.escape
    out = []
    pts = [{"_title": True}] + list(doc.get("slides") or [])
    for i, s in enumerate(pts, 1):
        p = f"s{i}-"
        g = "band" if s.get("_title") else t["ground"](i)
        bg, hc, tc, logo = _GROUND[g]
        if s.get("_title"):
            head, big, line, rest, refs = e(doc.get("title") or ""), "", e(doc.get("subtitle") or ""), [], ""
        else:
            head, big, line, rest, refs = _tpl_parts(s)
        hs = 128 if s.get("_title") else (72 if big else 88)
        if len(head) > 110:
            hs = min(hs, 64)
        bs = 200 if not rest else 160
        ls = 44 if len(line) < 120 else 34
        css = (f".{p}slide{{position:relative;width:1920px;height:1080px;box-sizing:border-box;padding:96px;display:flex;flex-direction:column;"
               f"justify-content:flex-end;gap:32px;background:{bg};color:{tc};overflow:hidden}}"
               f".{p}logo{{position:absolute;right:96px;top:96px;width:180px}}"
               f".{p}head{{margin:0;max-width:1600px;font-family:{t['head']};font-weight:{t['hw']};font-size:{hs}px;line-height:1.05;color:{hc}}}"
               f".{p}big{{margin:0;font-family:{t['big']};font-weight:{t['bw']};font-size:{bs}px;line-height:.95;color:{hc}}}"
               f".{p}line{{margin:0;max-width:1500px;font-family:var(--font-body);font-size:{ls}px;line-height:1.25}}"
               f".{p}list{{margin:0;padding:0;list-style:none;font-family:var(--font-body);font-size:32px;line-height:1.3}}")
        src = f' data-source="{e(refs)}"' if refs else ""
        quote = bool(s.get("quote"))
        parts = [f'<div class="{p}slide"><style>{css}</style><img class="{p}logo" src="{logo}" alt="">']
        if head:
            parts.append(f'<h2 class="{p}head"{src}>{head}</h2>')
        if big:
            parts.append(f'<p class="{p}big"{src}>{big}</p>')
        if line:
            parts.append(f'<p class="{p}{"head" if quote else "line"}"{src}>{line}</p>')
        if rest:
            parts.append(f'<ul class="{p}list"{src}>' + "".join(f"<li>{x}</li>" for x in rest) + "</ul>")
        parts.append("</div>")
        out.append({"html": sanitize("".join(parts))[0], "notes": ""})
    return out


def from_template(doc: dict, direction: str, css: str, out_dir, logo_data_uri="", passages=None) -> dict:
    """``make``'s result shape for the template version of ``direction`` (deck only), drawn and traced, marked ``template``."""
    slides = template_slides(doc, direction)
    result = render_safe(slides, css, out_dir, logo_data_uri, "deck")
    tr = trace(slides, passages or {})
    return {"slides": slides, "render": result, "trace": tr, "removed": [], "rounds": 0, "template": True}
