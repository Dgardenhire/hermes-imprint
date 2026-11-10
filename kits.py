"""Kits: the brand as an object Imprint can hold, check and enforce.

A kit (``kit.json``) holds:

- ``name``, ``origin`` (starter, hand, site, guided) and ``origin_note``
- ``paper`` and ``ink``: the page and its body text. Fixed by the brand, never derived.
- ``colors``: 1 to 8 ``{hex, role, name}``. Roles: head, accent, accent2, band, fill, highlight, rule.
  Imprint measures each against the paper (``colors.usage``) and never lets a color do a job its
  contrast can't carry: a 2.2:1 cyan stays a rule, and the text on a band uses whichever of paper or
  ink reads best on it.
- ``type``: ``heading`` and ``body`` as ``{family, stack, weight, style, case}``, and a ``scale`` ratio
- ``layout``: banner, headline, margin, letter or bulletin
- ``density``: airy, medium or dense
- ``voice``: ``notes``, ``delivery`` (for the narrator), ``never`` (words), ``pairs`` (say / not)
- ``rules``: ``sources``, ``page_numbers``, ``date`` (show or not), ``required`` (lines every page carries)
- ``logo``: ``{file, kind}`` or none; ``fonts``: uploaded faces ``{family, weight, style, file}``
- ``version``: bumped on every edit. Each render records the version it used.

Starter kits live in ``starter_kits.py`` and are read-only. Editing one makes the user's own copy.
User kits live in ``<data>/kits/<id>/``. There is no limit on how many.
"""

from __future__ import annotations

import base64
import copy
import re
import shutil
from pathlib import Path
from typing import Optional

try:
    from . import colors as C
    from . import fonts as F
    from . import store
    from .starter_kits import STARTERS
except ImportError:  # loaded loose
    import colors as C  # type: ignore
    import fonts as F  # type: ignore
    import store  # type: ignore
    from starter_kits import STARTERS  # type: ignore

LAYOUTS = {
    "banner": "Banner",
    "headline": "Headline",
    "margin": "Margin rail",
    "letter": "Letter",
    "bulletin": "Bulletin",
    "flyer": "Flyer or menu",
    "report": "Report",
}
# How a kit's decks and graphics are composed (systems.py). A kit without one gets the system that suits its
# page layout (``deck_system``).
DECK_SYSTEMS = {
    "exhibit": "Exhibit: action titles, charts labeled directly, a source line on every slide",
    "broadsheet": "Chart room: a tab marker, a headline and a standfirst, gridlines, data in two colors",
    "stage": "Stage: one idea per slide, very large type, a dark ground",
    "folio": "Folio: a book's page, generous margins, centered openers, folios",
    "grid": "Grid: flush-left type on a visible column grid, one color field",
}
ROLES = ("head", "accent", "accent2", "band", "fill", "highlight", "rule")
DENSITIES = ("airy", "medium", "dense")
MAX_COLORS = 8
MAX_LOGO = 2 * 1024 * 1024
MAX_FONT = 8 * 1024 * 1024
STARTER_IDS = {k["id"] for k in STARTERS}


class KitError(ValueError):
    pass


# ---------------------------------------------------------------- normalize --

def _text(v, limit, name, required=False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise KitError(f"{name} must be text.")
    v = v.strip()
    if len(v) > limit:
        raise KitError(f"{name} is too long (the limit is {limit} characters).")
    if required and not v:
        raise KitError(f"Give the kit a {name.lower()}.")
    return v


def _words(v, limit_items=40, limit_each=60) -> list:
    if isinstance(v, str):
        v = re.split(r"[,\n]", v)
    out = []
    for w in v or []:
        if not isinstance(w, str):
            continue
        w = w.strip()
        if w and w.lower() not in [x.lower() for x in out]:
            out.append(w[:limit_each])
    return out[:limit_items]


def _face(v, default_family: str, default_stack: str) -> dict:
    v = v if isinstance(v, dict) else {}
    family = _text(v.get("family") or default_family, 80, "Font name") or default_family
    stack = _text(v.get("stack") or "", 300, "Font stack") or f"{family}, {default_stack}"
    weight = v.get("weight") or 400
    try:
        weight = max(100, min(900, int(weight)))
    except (TypeError, ValueError):
        weight = 400
    face = {"family": family, "stack": stack, "weight": weight}
    if v.get("style") == "italic":
        face["style"] = "italic"
    if v.get("case") == "upper":
        face["case"] = "upper"
    if v.get("stands_in") is True:
        face["stands_in"] = True  # an open font standing in for a licensed one (adapted starter kits)
    return face


def normalize(raw: dict) -> dict:
    """A clean kit from what the page or the model sent. Raises KitError with a plain reason."""
    if not isinstance(raw, dict):
        raise KitError("That kit is not in a form Imprint can read.")
    kit = {}
    kit["name"] = _text(raw.get("name"), 60, "Name", required=True)
    kit["origin"] = raw.get("origin") if raw.get("origin") in ("starter", "hand", "site", "guided", "copy", "import") else "hand"
    kit["origin_note"] = _text(raw.get("origin_note"), 200, "Origin note")
    kit["org"] = _text(raw.get("org"), 80, "Organization name")
    kit["subject"] = _text(raw.get("subject"), 400, "Subject")
    kit["signature"] = _text(raw.get("signature"), 240, "Signature")
    paper = C.norm(raw.get("paper") or "#ffffff")
    ink = C.norm(raw.get("ink") or "#1b1b1b")
    if not paper or not ink:
        raise KitError("Paper and ink must be hex colors like #ffffff.")
    if C.contrast(ink, paper) < C.AA_TEXT:
        raise KitError(f"The ink and paper are too close ({C.ratio_text(ink, paper)}). Body text needs at least 4.5:1.")
    kit["paper"], kit["ink"] = paper, ink
    cols = []
    for c in (raw.get("colors") or [])[:MAX_COLORS]:
        if not isinstance(c, dict):
            continue
        h = C.norm(c.get("hex", ""))
        if not h:
            continue
        role = c.get("role") if c.get("role") in ROLES else "accent"
        cols.append({"hex": h, "role": role, "name": _text(c.get("name"), 40, "Color name")})
    if not cols:
        raise KitError("Add at least one brand color besides paper and ink.")
    kit["colors"] = cols
    t = raw.get("type") if isinstance(raw.get("type"), dict) else {}
    kit["type"] = {
        "heading": _face(t.get("heading"), "Inter", "Helvetica, Arial, sans-serif"),
        "body": _face(t.get("body"), "Inter", "Helvetica, Arial, sans-serif"),
        "scale": _scale(t.get("scale")),
    }
    if isinstance(t.get("label"), dict) and t["label"].get("family"):
        kit["type"]["label"] = _face(t.get("label"), "Inter", "Helvetica, Arial, sans-serif")
    kit["layout"] = raw.get("layout") if raw.get("layout") in LAYOUTS else "banner"
    if raw.get("deck") in DECK_SYSTEMS:
        kit["deck"] = raw["deck"]
    kit["density"] = raw.get("density") if raw.get("density") in DENSITIES else "medium"
    v = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}
    pairs = []
    for p in (v.get("pairs") or [])[:30]:
        if isinstance(p, dict):
            say, no = _text(p.get("say"), 60, "Say"), _text(p.get("not"), 60, "Not")
            if say and no and say.lower() != no.lower():
                pairs.append({"say": say, "not": no})
    kit["voice"] = {
        "notes": _text(v.get("notes"), 1200, "Voice notes"),
        "delivery": _text(v.get("delivery"), 400, "Delivery notes"),
        "never": _words(v.get("never")),
        "pairs": pairs,
        "draft": bool(v.get("draft")),
    }
    r = raw.get("rules") if isinstance(raw.get("rules"), dict) else {}
    kit["rules"] = {
        "sources": bool(r.get("sources", True)),
        "page_numbers": bool(r.get("page_numbers", True)),
        "date": bool(r.get("date", True)),
        "required": [x[:200] for x in _words(r.get("required"), limit_items=4, limit_each=200)],
    }
    imp = raw.get("imported_from")
    if isinstance(imp, dict):
        kit["imported_from"] = {k: (str(imp[k])[:120] if isinstance(imp[k], str) else imp[k])
                                for k in ("kind", "label", "ref", "sha256", "license_note", "brand_named", "mode", "imported_at")
                                if k in imp and isinstance(imp[k], (str, bool, int, float))}
    sb = safe_style_brief(raw.get("style_brief"))
    if sb:
        kit["style_brief"] = sb
    kit["logo"] = safe_logo(raw.get("logo"))
    kit["logo_alt"] = safe_logo(raw.get("logo_alt"), "logo-reversed")
    kit["fonts"] = safe_fonts(raw.get("fonts"))
    return kit


BRIEF_KEYS = ("layout", "type", "imagery", "shapes", "color", "components", "tone", "avoid")


def safe_style_brief(v) -> Optional[dict]:
    """The style brief written from a site's look (sitestyle.py), or by hand: eight plain-text fields of at most 700 characters with no
    markup characters, and where it came from. Anything else is dropped."""
    if not isinstance(v, dict):
        return None
    out = {}
    for k in BRIEF_KEYS:
        t = re.sub(r"[<>`\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v.get(k) or ""))
        out[k] = re.sub(r"[ \t]+", " ", t).strip()[:700]
    if not any(out.values()):
        return None
    for k, n in (("source", 300), ("at", 20)):
        if isinstance(v.get(k), str):
            out[k] = re.sub(r"[^\w:/.\-~%?=&#@+ ]", "", v[k])[:n]
    if isinstance(v.get("pages"), list):
        out["pages"] = [re.sub(r"[^\w:/.\-~%?=&#@+]", "", p)[:300] for p in v["pages"][:4] if isinstance(p, str)]
    return out


LOGO_KINDS = ("png", "svg", "jpg")
FONT_FILE = re.compile(r"[a-z0-9][a-z0-9-]{0,160}\.ttf")


def safe_logo(v, stem: str = "logo") -> Optional[dict]:
    """A logo entry only in the one shape Imprint writes (``logo.<kind>``, or ``logo-reversed.<kind>`` for the
    kit's knockout version, in the kit's own folder). Anything else from the page or a model (a path, another
    file name) is dropped, so no route can read outside the kit."""
    if stem not in ("logo", "logo-reversed"):
        return None
    if not isinstance(v, dict) or v.get("kind") not in LOGO_KINDS or v.get("file") != f"{stem}.{v.get('kind')}":
        return None
    return {"file": v["file"], "kind": v["kind"]}


def safe_fonts(v) -> list:
    """Font entries only with a file name Imprint itself writes (``fonts/<family-weight-style>.ttf``)."""
    out = []
    for f in (v if isinstance(v, list) else [])[:12]:
        if not isinstance(f, dict) or not isinstance(f.get("file"), str) or not FONT_FILE.fullmatch(f["file"]):
            continue
        try:
            weight = max(100, min(900, int(f.get("weight") or 400)))
        except (TypeError, ValueError):
            weight = 400
        out.append({"family": str(f.get("family") or "")[:80], "weight": weight,
                    "style": "italic" if f.get("style") == "italic" else "normal", "file": f["file"]})
    return out


def inside(folder: Path, name: str) -> Optional[Path]:
    """``folder / name`` only when it stays inside ``folder``."""
    try:
        p = (folder / name).resolve()
        if p.is_relative_to(folder.resolve()):
            return p
    except (OSError, ValueError, TypeError):
        pass
    return None


def _scale(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 1.25
    return max(1.1, min(1.6, v))


# ---------------------------------------------------------------- palette --

def palette(kit: dict) -> dict:
    """What each role may do on this kit's paper, with the measured ratios.

    Returns the tokens every renderer uses: paper, ink, head, accent (for big numbers and marks),
    accent_text (safe for small text), band and band_text, fill and fill_text, highlight, rule, the color
    bar, and ``swatches`` (each color with its usage and ratio) for the Kits tab."""
    paper, ink = kit["paper"], kit["ink"]
    by_role = {}
    for c in kit.get("colors", []):
        by_role.setdefault(c["role"], c["hex"])
    swatches = []
    for c in kit.get("colors", []):
        use = C.usage(c["hex"], paper, ink)
        if use in ("fill", "rule"):  # too light for text: the declared role decides between the two
            if c["role"] == "rule":
                use = "rule"
            elif c["role"] in ("fill", "highlight", "band") and C.contrast(ink, c["hex"]) >= C.AA_TEXT:
                use = "fill"
        swatches.append({**c, "usage": use, "label": C.ROLE_LABEL[use], "ratio": round(C.contrast(c["hex"], paper), 2)})
    use_of = {s["hex"]: s["usage"] for s in swatches}

    def text_safe(hexcolor, large=False):
        if not hexcolor:
            return None
        u = use_of.get(hexcolor) or C.usage(hexcolor, paper, ink)
        return hexcolor if (u == "text" or (large and u in ("text", "large"))) else None

    head = text_safe(by_role.get("head"), large=True) or ink
    accent_raw = by_role.get("accent") or by_role.get("head") or ink
    accent = text_safe(accent_raw, large=True) or head
    accent_text = text_safe(accent_raw) or (head if C.contrast(head, paper) >= C.AA_TEXT else ink)
    band = by_role.get("band")
    band_text = None
    if band:
        band_text, ratio = C.best_text_on(band, [paper, ink, "#ffffff", "#111111"])
        if ratio < C.AA_LARGE:
            band, band_text = None, None
    fill = by_role.get("fill")
    fill_text = None
    if fill:
        fill_text, ratio = C.best_text_on(fill, [ink, head, paper])
        if ratio < C.AA_TEXT:
            fill, fill_text = None, None
    highlight = by_role.get("highlight") or by_role.get("fill")
    rule = by_role.get("rule") or C.mix(ink, paper, 0.75)
    bar = []
    for c in [paper, ink] + [x["hex"] for x in kit.get("colors", [])]:
        if c not in bar:
            bar.append(c)
    pairs = [{"what": "Body text on paper", "fg": ink, "bg": paper}, {"what": "Headings on paper", "fg": head, "bg": paper, "large": True}]
    if accent_text != ink:
        pairs.append({"what": "Accent text on paper", "fg": accent_text, "bg": paper})
    if band:
        pairs.append({"what": "Masthead text on band", "fg": band_text, "bg": band, "large": True})
    if fill:
        pairs.append({"what": "Text on fill", "fg": fill_text, "bg": fill})
    for p in pairs:
        p["ratio"] = round(C.contrast(p["fg"], p["bg"]), 2)
        p["passes"] = p["ratio"] >= (C.AA_LARGE if p.get("large") else C.AA_TEXT)
    downgraded = []
    for role in ("head", "accent"):
        raw = by_role.get(role)
        if raw and use_of.get(raw) in ("fill", "rule"):
            downgraded.append({"role": role, "hex": raw, "ratio": round(C.contrast(raw, paper), 2), "label": use_of.get(raw)})
    return {"paper": paper, "ink": ink, "head": head, "accent": accent, "accent_text": accent_text,
            "accent2": text_safe(by_role.get("accent2"), large=True),
            "band": band, "band_text": band_text, "fill": fill, "fill_text": fill_text, "highlight": highlight,
            "rule": rule, "bar": bar, "swatches": swatches, "pairs": pairs, "downgraded": downgraded,
            "dark": C.luminance(paper) < 0.2}


# ---------------------------------------------------------------- storage --

def kits_dir() -> Path:
    d = store.root() / "kits"
    d.mkdir(parents=True, exist_ok=True)
    return d


def kit_dir(kit_id: str) -> Optional[Path]:
    if kit_id in STARTER_IDS:
        return None
    if not re.fullmatch(r"k_[a-f0-9]{12}", kit_id or ""):
        raise KitError("That kit is gone. It may have been deleted.")
    return kits_dir() / kit_id


def _starter(kit_id: str) -> Optional[dict]:
    for k in STARTERS:
        if k["id"] == kit_id:
            raw = copy.deepcopy(k)
            raw["origin"] = "starter"
            kit = normalize(raw)
            kit.update({"id": kit_id, "version": 1, "starter": True, "created_at": 0, "updated_at": 0,
                        "featured": bool(k.get("featured")), "credit": k.get("credit") or "",
                        "studio": bool(k.get("studio")), "tier": "studio" if k.get("studio") else "classic",
                        "method": k.get("method") or ""})
            return kit
    return None


def get(kit_id: str) -> dict:
    s = _starter(kit_id)
    if s:
        return s
    d = kit_dir(kit_id)
    kit = store.read_json(d / "kit.json") if d else None
    if not kit:
        raise KitError("That kit is gone. It may have been deleted.")
    kit["starter"] = False
    return kit


def list_all() -> list:
    out = []
    for k in STARTERS:
        out.append(summary(_starter(k["id"])))
    users = []
    for d in kits_dir().iterdir() if kits_dir().exists() else []:
        kit = store.read_json(d / "kit.json")
        if kit and kit.get("id"):
            kit["starter"] = False
            users.append(summary(kit))
    users.sort(key=lambda k: -(k.get("updated_at") or 0))
    return users + out


def summary(kit: dict) -> dict:
    pal = palette(kit)
    fc = faces(kit)
    return {"head_css": fc["heading"].get("css"), "body_css": fc["body"].get("css"),
            "head_style": fc["heading"].get("style"), "head_weight": fc["heading"].get("weight"),
            "head_case": (kit["type"]["heading"].get("case") or "none"),
            "font_keys": sorted({f["key"] for f in (fc["heading"], fc["body"]) if f.get("key")}),
            "id": kit["id"], "name": kit["name"], "starter": bool(kit.get("starter")), "origin": kit.get("origin"),
            "origin_note": kit.get("origin_note", ""), "layout": kit["layout"], "layout_label": LAYOUTS[kit["layout"]],
            "paper": kit["paper"], "ink": kit["ink"], "bar": pal["bar"], "head": pal["head"], "accent": pal["accent"],
            "band": pal["band"], "band_text": pal["band_text"],
            "heading_family": kit["type"]["heading"]["family"], "body_family": kit["type"]["body"]["family"],
            "version": kit.get("version", 1), "updated_at": kit.get("updated_at", 0), "has_logo": bool(kit.get("logo")),
            "subject": kit.get("subject", ""), "featured": bool(kit.get("featured")), "credit": kit.get("credit") or "",
            "signature": kit.get("signature", ""), "method": kit.get("method", ""), "deck": deck_system(kit), "studio": bool(kit.get("studio")),
            "tier": kit.get("tier") or ("studio" if kit.get("studio") else "classic" if kit.get("starter") else "own"),
            "label_css": fc.get("label", {}).get("css"),
            "all_font_keys": sorted({f["key"] for f in fc.values() if f.get("key")})}


def deck_system(kit: dict) -> str:
    """The composition system for this kit's decks and graphics: its own choice, or the one its page layout and
    ground suggest (a dark paper gets the stage; a report or banner page gets exhibits; a letter or margin page gets
    the folio; a headline or flyer page gets the grid; a bulletin gets the chart room)."""
    if kit.get("deck") in DECK_SYSTEMS:
        return kit["deck"]
    if C.luminance(kit.get("paper") or "#ffffff") < 0.2:
        return "stage"
    return {"banner": "exhibit", "report": "exhibit", "letter": "folio", "margin": "folio", "headline": "grid",
            "flyer": "grid", "bulletin": "broadsheet"}.get(kit.get("layout") or "banner", "exhibit")


def save_new(raw: dict) -> dict:
    kit = normalize(raw)
    kit["logo"], kit["logo_alt"], kit["fonts"] = None, None, []  # a new kit's folder is empty; set_logo, add_font and duplicate fill these
    kit["id"] = store.new_id("k")
    kit["version"] = 1
    kit["created_at"] = kit["updated_at"] = store.now()
    d = kits_dir() / kit["id"]
    d.mkdir(parents=True, exist_ok=True)
    store.write_json(d / "kit.json", kit)
    return get(kit["id"])


def update(kit_id: str, raw: dict) -> dict:
    if kit_id in STARTER_IDS:
        base = get(kit_id)
        merged = {**base, **raw, "origin": "copy", "origin_note": f"Your copy of {base['name']}"}
        if raw.get("name") in (None, base["name"]):
            merged["name"] = f"{base['name']} (yours)"
        return save_new(merged)
    old = get(kit_id)
    merged = {**old, **raw}
    kit = normalize(merged)
    kit["logo"], kit["logo_alt"], kit["fonts"] = old.get("logo"), old.get("logo_alt"), old.get("fonts") or []
    kit.update({"id": kit_id, "version": int(old.get("version") or 1) + 1, "created_at": old.get("created_at"),
                "updated_at": store.now()})
    store.write_json(kit_dir(kit_id) / "kit.json", kit)
    return get(kit_id)


def duplicate(kit_id: str) -> dict:
    base = get(kit_id)
    raw = {**base, "name": f"{base['name']} copy"[:60], "origin": "copy", "origin_note": f"Copied from {base['name']}"}
    new = save_new(raw)
    src = kit_dir(kit_id)
    if src and src.exists():
        dst = kit_dir(new["id"])
        for sub in ("fonts",):
            if (src / sub).exists():
                shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
        kept = {}
        for field, stem in (("logo", "logo"), ("logo_alt", "logo-reversed")):
            lg = safe_logo(base.get(field), stem)
            if lg and (src / lg["file"]).is_file():
                shutil.copy2(src / lg["file"], dst / lg["file"])
                kept[field] = lg
        cur = store.read_json(dst / "kit.json")
        cur["logo"], cur["logo_alt"], cur["fonts"] = kept.get("logo"), kept.get("logo_alt"), safe_fonts(base.get("fonts"))
        store.write_json(dst / "kit.json", cur)
    return get(new["id"])


def delete(kit_id: str) -> None:
    if kit_id in STARTER_IDS:
        raise KitError("Starter kits can't be deleted. Make a copy to change one.")
    d = kit_dir(kit_id)
    if not d or not d.exists():
        raise KitError("That kit is gone already.")
    shutil.rmtree(d)


# ---------------------------------------------------------------- assets --

def _own(kit_id: str) -> Path:
    if kit_id in STARTER_IDS:
        raise KitError("Make your own copy of this starter kit first, then add a logo or fonts to it.")
    d = kit_dir(kit_id)
    if not d or not (d / "kit.json").exists():
        raise KitError("That kit is gone. It may have been deleted.")
    return d


def set_logo(kit_id: str, filename: str, data: bytes, alt: bool = False) -> dict:
    """The kit's logo, or with ``alt`` its reversed (knockout) version for dark bands and slides."""
    d = _own(kit_id)
    stem, field = ("logo-reversed", "logo_alt") if alt else ("logo", "logo")
    ext = Path(filename or "").suffix.lower()
    if ext not in (".png", ".svg", ".jpg", ".jpeg"):
        raise KitError("Add the logo as an SVG, PNG or JPG file.")
    if len(data) > MAX_LOGO:
        raise KitError("That logo file is over 2 MB. Export a smaller PNG or an SVG.")
    try:
        from . import imports as IM
    except ImportError:
        import imports as IM  # type: ignore
    if ext == ".svg":
        why = IM.svg_problem(data)
        if why:
            raise KitError(f"Imprint won't use that SVG: {why}. Export a plain SVG or a PNG.")
    else:
        why = IM.png_problem(data) if ext == ".png" else IM.jpg_problem(data)
        if why:
            raise KitError(f"Imprint won't use that logo: {why}. Export a PNG at most 4096 pixels wide, or an SVG.")
    kind = "jpg" if ext in (".jpg", ".jpeg") else ext[1:]
    for old in d.glob(f"{stem}.*"):
        old.unlink()
    store.write_bytes(d / f"{stem}.{kind}", data)
    kit = store.read_json(d / "kit.json")
    kit[field] = {"file": f"{stem}.{kind}", "kind": kind}
    kit["version"] = int(kit.get("version") or 1) + 1
    kit["updated_at"] = store.now()
    store.write_json(d / "kit.json", kit)
    return get(kit_id)


def remove_logo(kit_id: str, alt: bool = False) -> dict:
    d = _own(kit_id)
    stem, field = ("logo-reversed", "logo_alt") if alt else ("logo", "logo")
    for old in d.glob(f"{stem}.*"):
        old.unlink()
    kit = store.read_json(d / "kit.json")
    kit[field] = None
    kit["version"] = int(kit.get("version") or 1) + 1
    store.write_json(d / "kit.json", kit)
    return get(kit_id)


def logo_data_url(kit: dict, alt: bool = False) -> Optional[str]:
    p = logo_path(kit, alt)
    if p is None:
        return None
    entry = kit["logo_alt"] if alt else kit["logo"]
    mime = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg"}.get(entry["kind"], "image/png")
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def logo_path(kit: dict, alt: bool = False) -> Optional[Path]:
    logo = safe_logo(kit.get("logo_alt" if alt else "logo"), "logo-reversed" if alt else "logo")
    if not logo or kit.get("starter"):
        return None
    p = inside(kit_dir(kit["id"]), logo["file"])
    return p if p is not None and p.is_file() else None


def logo_variants(kit: dict, pal: Optional[dict] = None) -> dict:
    """The logo for each ground this kit puts it on, knocked out or swapped for the reversed logo where the
    main mark would vanish (logos.py)."""
    try:
        from . import logos as LG
    except ImportError:
        import logos as LG  # type: ignore
    return LG.for_kit(logo_path(kit), kit, pal or palette(kit), alt=logo_path(kit, alt=True))


def add_font(kit_id: str, filename: str, data: bytes) -> dict:
    d = _own(kit_id)
    ext = Path(filename or "").suffix.lower()
    if ext not in (".ttf", ".otf"):
        raise KitError("Add fonts as .ttf files (or .otf files with TrueType outlines).")
    if len(data) > MAX_FONT:
        raise KitError("That font file is over 8 MB.")
    try:
        names = F.read_ttf_names(data)
    except ValueError as e:
        raise KitError(str(e))
    safe = re.sub(r"[^a-z0-9]+", "-", f"{names['family']}"[:100].lower()).strip("-") or "font"
    safe = f"{safe}-{int(names['weight'])}-{'italic' if names['style'] == 'italic' else 'normal'}"
    store.write_bytes(d / "fonts" / f"{safe}.ttf", data)
    kit = store.read_json(d / "kit.json")
    faces = [f for f in kit.get("fonts") or [] if f.get("file") != f"{safe}.ttf"]
    faces.append({"family": names["family"], "weight": names["weight"], "style": names["style"], "file": f"{safe}.ttf"})
    kit["fonts"] = faces
    kit["version"] = int(kit.get("version") or 1) + 1
    kit["updated_at"] = store.now()
    store.write_json(d / "kit.json", kit)
    return get(kit_id)


def faces(kit: dict) -> dict:
    return F.resolve_kit(kit, kit_dir(kit["id"]) if not kit.get("starter") else None)


# ---------------------------------------------------------------- looks --

def look_of(kit: dict) -> dict:
    """The parts of a kit's look worth remembering, so new kits and outputs don't repeat them."""
    pal = palette(kit)
    t = kit["type"]
    return {"layout": kit["layout"], "ground": C.describe(kit["paper"]),
            "type_pair": f"{t['heading']['family']} / {t['body']['family']}",
            "accent": C.describe(pal["accent"]) if pal["accent"] != kit["ink"] else "none",
            "signature": kit.get("signature", "")[:160]}


def record_look(kit: dict, kind: str) -> None:
    lk = look_of(kit)
    store.run("INSERT INTO looks(kit_id, kind, layout, ground, type_pair, accent, signature, created_at) VALUES(?,?,?,?,?,?,?,?)",
              (kit["id"], kind, lk["layout"], lk["ground"], lk["type_pair"], lk["accent"], lk["signature"], store.now()))
    rows = store.q("SELECT id FROM looks ORDER BY id DESC LIMIT 1 OFFSET 199")
    if rows:
        store.run("DELETE FROM looks WHERE id <= ?", (rows[0]["id"],))


def recent_looks(n: int = 12) -> list:
    return store.q("SELECT kit_id, kind, layout, ground, type_pair, accent, signature, created_at FROM looks ORDER BY id DESC LIMIT ?", (n,))


def repeats(n: int = 12) -> dict:
    """How often each layout, ground, type pair and accent came up in the last ``n`` looks."""
    rows = recent_looks(n)
    out = {"layout": {}, "ground": {}, "type_pair": {}, "accent": {}, "count": len(rows)}
    for r in rows:
        for k in ("layout", "ground", "type_pair", "accent"):
            out[k][r[k]] = out[k].get(r[k], 0) + 1
    return out
