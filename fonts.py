"""Fonts: the bundled OFL set, fonts a user adds to a kit, and honest resolution.

A kit asks for a family (``Merriweather``) with a fallback stack (``Georgia, serif``). Imprint looks in
this order: the kit's own uploaded files, then the bundled set, then each name in the stack, then the
PDF's built-in faces (Times, Helvetica, Courier) by the stack's generic class. The same answer is used
for the preview, the PDF and the HTML, so what you see is what exports, and every substitution is
named in the colophon ("Set in Times in place of Garamond").

Uploaded fonts are read with reportlab's TrueType parser, which is also what embeds them in the PDF:
a file it can't parse (a PostScript-outline OTF, a damaged file) is refused at upload with the reason.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
BUNDLED_DIR = HERE / "fonts"

# family, weight, style, file, class
BUNDLED = [
    ("Inter", 400, "normal", "inter-400.ttf", "sans"),
    ("Inter", 700, "normal", "inter-700.ttf", "sans"),
    ("Barlow", 400, "normal", "barlow-400.ttf", "sans"),
    ("Barlow", 600, "normal", "barlow-600.ttf", "sans"),
    ("Barlow Condensed", 700, "normal", "barlow-condensed-700.ttf", "sans"),
    ("Barlow Condensed", 900, "normal", "barlow-condensed-900.ttf", "sans"),
    ("Libre Caslon Display", 400, "normal", "libre-caslon-display-400.ttf", "serif"),
    ("Instrument Serif", 400, "italic", "instrument-serif-400-italic.ttf", "serif"),
    ("Anton", 400, "normal", "anton-400.ttf", "sans"),
    ("Courier Prime", 400, "normal", "courier-prime-400.ttf", "mono"),
    ("Courier Prime", 700, "normal", "courier-prime-700.ttf", "mono"),
    ("Crimson Pro", 400, "normal", "crimson-pro-400.ttf", "serif"),
    ("Crimson Pro", 400, "italic", "crimson-pro-400-italic.ttf", "serif"),
    ("Merriweather", 400, "normal", "merriweather-400.ttf", "serif"),
    ("Merriweather", 700, "normal", "merriweather-700.ttf", "serif"),
    ("Public Sans", 400, "normal", "public-sans-400.ttf", "sans"),
    ("Public Sans", 700, "normal", "public-sans-700.ttf", "sans"),
    ("Public Sans", 400, "italic", "public-sans-400-italic.ttf", "sans"),
    ("Source Serif 4", 400, "normal", "source-serif-4-400.ttf", "serif"),
    ("Source Serif 4", 600, "normal", "source-serif-4-600.ttf", "serif"),
    ("Source Sans 3", 400, "normal", "source-sans-3-400.ttf", "sans"),
    ("Source Sans 3", 600, "normal", "source-sans-3-600.ttf", "sans"),
    ("DM Serif Display", 400, "normal", "dm-serif-display-400.ttf", "serif"),
    ("Montserrat", 400, "normal", "montserrat-400.ttf", "sans"),
    ("Montserrat", 600, "normal", "montserrat-600.ttf", "sans"),
    ("Montserrat", 700, "normal", "montserrat-700.ttf", "sans"),
    ("Montserrat", 800, "normal", "montserrat-800.ttf", "sans"),
    ("Lora", 400, "normal", "lora-400.ttf", "serif"),
    ("Lora", 400, "italic", "lora-400-italic.ttf", "serif"),
]

# The PDF's built-in faces, and the closest screen fonts for the preview.
BUILTIN = {
    "serif": {"name": "Times", "pdf": {(400, "normal"): "Times-Roman", (700, "normal"): "Times-Bold",
                                       (400, "italic"): "Times-Italic", (700, "italic"): "Times-BoldItalic"},
              "css": '"Times New Roman", Times, serif'},
    "sans": {"name": "Helvetica", "pdf": {(400, "normal"): "Helvetica", (700, "normal"): "Helvetica-Bold",
                                          (400, "italic"): "Helvetica-Oblique", (700, "italic"): "Helvetica-BoldOblique"},
             "css": 'Helvetica, Arial, "Liberation Sans", sans-serif'},
    "mono": {"name": "Courier", "pdf": {(400, "normal"): "Courier", (700, "normal"): "Courier-Bold",
                                        (400, "italic"): "Courier-Oblique", (700, "italic"): "Courier-BoldOblique"},
             "css": '"Courier New", Courier, monospace'},
}
BUILTIN_ALIASES = {
    "times": "serif", "times new roman": "serif", "georgia": None, "helvetica": "sans", "helvetica neue": "sans",
    "arial": "sans", "courier": "mono", "courier new": "mono",
}
GENERIC = {"serif": "serif", "sans-serif": "sans", "sans": "sans", "monospace": "mono", "mono": "mono",
           "system-ui": "sans", "ui-sans-serif": "sans", "ui-serif": "serif", "ui-monospace": "mono",
           "-apple-system": "sans", "blinkmacsystemfont": "sans", "cursive": "serif", "fantasy": "sans"}


def split_stack(stack: str) -> list:
    out = []
    for part in (stack or "").split(","):
        name = part.strip().strip("'\"").strip()
        if name:
            out.append(name)
    return out


def generic_class(stack: list, default: str = "sans") -> str:
    for name in reversed(stack):
        g = GENERIC.get(name.lower())
        if g:
            return g
    for name in stack:
        low = name.lower()
        if any(w in low for w in ("serif", "garamond", "caslon", "georgia", "times", "merriweather", "baskerville",
                                  "playfair", "lora", "crimson", "minion", "book")) and "sans" not in low:
            return "serif"
        if any(w in low for w in ("mono", "courier", "code", "consol")):
            return "mono"
    return default


def read_ttf_names(data: bytes) -> dict:
    """``{family, style, weight}`` from a TrueType file, using reportlab (the PDF embedder)."""
    try:
        from reportlab.pdfbase.ttfonts import TTFontFile
    except ImportError:
        raise ValueError("Adding fonts needs the reportlab library, which isn't installed. Reinstall Imprint to add it.")
    import io
    try:
        f = TTFontFile(io.BytesIO(data))
    except Exception as e:
        msg = str(e).lower()
        if "postscript" in msg or "cff" in msg or "otto" in msg:
            raise ValueError("That font uses PostScript outlines, which can't be embedded in a PDF here. Add the .ttf version of the font.")
        if "restrict" in msg or "embed" in msg:
            raise ValueError("That font's license doesn't allow embedding it in documents.")
        raise ValueError("Imprint couldn't read that font file. Add a TrueType (.ttf) font.")

    def text(v):
        return (v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v or "")).strip()

    family = text(getattr(f, "familyName", "")) or "Untitled font"
    style = text(getattr(f, "styleName", "")) or "Regular"
    weight = 700 if re.search(r"bold|black|heavy|semibold|extrabold", style, re.I) else 400
    italic = "italic" if re.search(r"italic|oblique", style, re.I) or (getattr(f, "italicAngle", 0) or 0) != 0 else "normal"
    return {"family": family, "style": italic, "weight": weight, "style_name": style}


def kit_fonts(kit_dir: Optional[Path], kit: dict) -> list:
    """The kit's uploaded fonts as ``(family, weight, style, path)``."""
    out = []
    for f in (kit.get("fonts") or []):
        if not kit_dir:
            continue
        name = f.get("file") if isinstance(f.get("file"), str) else ""
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,160}\.ttf", name):
            continue
        p = kit_dir / "fonts" / name
        if p.is_file():
            out.append((f.get("family", ""), int(f.get("weight") or 400), f.get("style") or "normal", p))
    return out


def _nearest(cands: list, weight: int, style: str):
    """Best of ``[(weight, style, payload)]``: same style first, then nearest weight."""
    if not cands:
        return None
    def score(c):
        return (0 if c[1] == style else 1, abs(c[0] - weight))
    return min(cands, key=score)


def resolve(spec: dict, kit: dict, kit_dir: Optional[Path] = None, weight: Optional[int] = None,
            style: Optional[str] = None) -> dict:
    """Which face to use for one role (heading or body), and the truth about it.

    Returns ``{role, wanted, used, file, pdf, css, key, substituted, note}``. ``file`` is a path for an
    embedded TrueType face; ``pdf`` is the built-in PDF face name when no file is used."""
    spec = spec or {}
    out = _resolve(spec, kit, kit_dir, weight, style)
    if spec.get("stands_in") and not out.get("substituted") and out.get("source") in ("bundled", "upload"):
        out["stands_in"] = True
    return out


def _resolve(spec: dict, kit: dict, kit_dir: Optional[Path], weight: Optional[int], style: Optional[str]) -> dict:
    wanted = (spec.get("family") or "").strip()
    stack = [wanted] + [n for n in split_stack(spec.get("stack", "")) if n.lower() != wanted.lower()]
    stack = [n for n in stack if n]
    w = int(weight or spec.get("weight") or 400)
    st = style or spec.get("style") or "normal"
    uploaded = kit_fonts(kit_dir, kit)

    for name in stack:
        low = name.lower()
        if low in GENERIC:
            break
        cands = [(fw, fs, ("upload", p)) for fam, fw, fs, p in uploaded if fam.lower() == low]
        cands += [(bw, bs, ("bundled", BUNDLED_DIR / fn)) for fam, bw, bs, fn, _c in BUNDLED if fam.lower() == low]
        pick = _nearest(cands, w, st)
        if pick:
            source, path = pick[2]
            key = f"{'u' if source == 'upload' else 'b'}-{re.sub(r'[^a-z0-9]+', '-', low)}-{pick[0]}-{pick[1]}"
            note = ""
            if pick[1] != st:
                note = f"{name} has no {st} face here, so the {pick[1]} one is used."
            return {"wanted": wanted or name, "used": name, "file": str(path), "pdf": None, "key": key,
                    "css": f'"imp-{key}", {_css_stack(stack)}', "weight": pick[0], "style": pick[1],
                    "substituted": bool(wanted) and name.lower() != wanted.lower(), "note": note, "source": source}
        alias = BUILTIN_ALIASES.get(low, "missing")
        if alias not in ("missing", None):
            exact = name.lower() == (wanted or name).lower()
            if not exact:
                # The family the kit wants is missing and its stack falls back to a system face (Arial, Helvetica
                # Neue). The preview and the PNG draw a bundled face there, so the PDF embeds that same face rather
                # than an unembedded base-14 one: what you see is what exports.
                near = nearest_bundled(stack, alias, w, st)
                if near:
                    return _bundled_stand_in(near, wanted, stack)
            return _builtin(alias, wanted or name, w, st, exact=exact, shown=name)
    cls = generic_class(stack, default=spec.get("class") or "sans")
    near = nearest_bundled(stack, cls, w, st)
    if near and wanted:
        return _bundled_stand_in(near, wanted, stack)
    return _builtin(cls, wanted or BUILTIN[cls]["name"], w, st, exact=False)


def _bundled_stand_in(near: tuple, wanted: str, stack: list) -> dict:
    fam, bw, bs, fn = near
    key = f"b-{re.sub(r'[^a-z0-9]+', '-', fam.lower())}-{bw}-{bs}"
    return {"wanted": wanted, "used": fam, "file": str(BUNDLED_DIR / fn), "pdf": None, "key": key,
            "css": f'"imp-{key}", {_css_stack(stack)}', "weight": bw, "style": bs, "substituted": True, "note": "",
            "source": "bundled"}


DISPLAY_SERIF = ("playfair", "fraunces", "dm serif", "bodoni", "didot", "abril", "display", "cormorant", "prata", "yeseva")
OLDSTYLE = ("garamond", "caslon", "crimson", "minion", "lora", "baskerville", "sabon", "jenson", "spectral", "eb ")
CONDENSED = ("condensed", "oswald", "bebas", "anton", "league gothic", "compressed", "narrow", "big shoulders")


def nearest_bundled(stack: list, cls: str, weight: int, style: str) -> Optional[tuple]:
    """The bundled open font nearest a family Imprint doesn't have, by kind of type, so a missing Playfair
    Display sets in Libre Caslon Display rather than Times, and a missing Montserrat in Inter rather than
    Helvetica. ``(family, weight, style, file)`` or ``None`` (mono and anything unknown keep the built-in)."""
    names = " ".join(n.lower() for n in stack)
    if cls == "mono":
        fam = "Courier Prime"
    elif any(k in names for k in CONDENSED):
        fam = "Barlow Condensed"
    elif cls == "serif" and any(k in names for k in DISPLAY_SERIF) and weight >= 500:
        fam = "Libre Caslon Display"
    elif cls == "serif" and any(k in names for k in OLDSTYLE + DISPLAY_SERIF):
        fam = "Crimson Pro"
    elif cls == "serif":
        fam = "Merriweather"
    else:
        fam = "Inter"
    cands = [(bw, bs, (f, bw, bs, fn)) for f, bw, bs, fn, _c in BUNDLED if f == fam]
    pick = _nearest(cands, weight, style)
    return pick[2] if pick else None


SAME_AS_BUILTIN = {"serif": {"times", "times new roman", "times roman"}, "sans": {"helvetica"},
                   "mono": {"courier", "courier new"}}


def _builtin(cls: str, wanted: str, weight: int, style: str, exact: bool = False, shown: Optional[str] = None) -> dict:
    b = BUILTIN[cls]
    wkey = 700 if weight >= 600 else 400
    face = b["pdf"][(wkey, "italic" if style == "italic" else "normal")]
    used = b["name"]
    substituted = wanted.lower() not in SAME_AS_BUILTIN[cls]
    return {"wanted": wanted, "used": used, "file": None, "pdf": face, "key": None, "css": b["css"],
            "weight": wkey, "style": style, "substituted": substituted, "note": "", "source": "builtin"}


def _css_stack(stack: list) -> str:
    out = []
    for n in stack:
        out.append(n if n.lower() in GENERIC else f'"{n}"')
    if not any(n.lower() in GENERIC for n in stack):
        out.append("sans-serif")
    return ", ".join(out)


def resolve_kit(kit: dict, kit_dir: Optional[Path] = None) -> dict:
    """Faces for every role a renderer needs: heading, body, body bold, body italic."""
    t = kit.get("type") or {}
    head = t.get("heading") or {}
    body = t.get("body") or {}
    out = {
        "heading": resolve(head, kit, kit_dir),
        "body": resolve(body, kit, kit_dir, weight=400, style="normal"),
        "body_bold": resolve(body, kit, kit_dir, weight=700, style="normal"),
        "body_italic": resolve(body, kit, kit_dir, weight=400, style="italic"),
    }
    # Labels, figures and source lines: the kit's own label face when it names one (the studio kits do), else the
    # body's bold. Used by decks and graphics; the one-pager keeps its two faces.
    label = t.get("label") if isinstance(t.get("label"), dict) else None
    out["label"] = resolve(label, kit, kit_dir) if label and label.get("family") else out["body_bold"]
    return out


def colophon(faces: dict, source_count: int) -> str:
    """The proof's honest line: what it was set in, what was substituted, how many sources."""
    parts = []
    seen = set()
    for role in ("heading", "body"):
        f = faces.get(role) or {}
        used, wanted = f.get("used"), f.get("wanted")
        if not used or (used, wanted) in seen:
            continue
        seen.add((used, wanted))
        if f.get("substituted") and wanted and wanted.lower() != used.lower():
            parts.append(f"{used} in place of {wanted}")
        elif f.get("stands_in"):
            parts.append(f"{used} (an open font standing in for a licensed one)")
        else:
            parts.append(used)
    uniq = []
    for p in parts:
        if p not in uniq:
            uniq.append(p)
    if len(uniq) == 1:
        text = f"Set in {uniq[0]}"
    else:
        text = f"Set in {', '.join(uniq[:-1])}, and {uniq[-1]}" if any(" in place of " in p for p in uniq) else f"Set in {uniq[0]} and {uniq[1]}"
    n = int(source_count or 0)
    text += f". Drawn from {n} source{'s' if n != 1 else ''}."
    return text


def substitutions(faces: dict) -> list:
    out = []
    for role in ("heading", "body"):
        f = faces.get(role) or {}
        if f.get("substituted") and f.get("wanted") and f.get("used") and f["wanted"].lower() != f["used"].lower():
            out.append({"role": role, "wanted": f["wanted"], "used": f["used"]})
        if f.get("note"):
            out.append({"role": role, "wanted": f.get("wanted"), "used": f.get("used"), "note": f["note"]})
    return out


def stands_in(faces: dict) -> list:
    """Open fonts a kit uses in place of a licensed typeface, by family, for the Fonts check."""
    return [f["used"] for r in ("heading", "body") for f in [faces.get(r) or {}] if f.get("stands_in") and f.get("used")]


def font_bytes_b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def bundled_families() -> list:
    out = {}
    for fam, w, s, fn, cls in BUNDLED:
        out.setdefault(fam, {"family": fam, "class": cls, "faces": []})["faces"].append({"weight": w, "style": s})
    return list(out.values())
