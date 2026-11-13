"""Reading sources into passages. Every passage keeps a locator a reader can find again.

Accepted: PDF (``p. 4``), Word ``.docx`` (the heading it sits under), ``.txt`` and ``.md`` (heading or
paragraph), transcripts ``.vtt`` and ``.srt`` (``[12:40]``, with the speaker when the file names one),
web pages (heading), and pasted text. Refused at the door, never half-read: files over 25 MB, audio and
video, encrypted PDFs, PDFs with no text layer, unknown types, and anything with no readable text.

Files are deduplicated by SHA-256. A source keeps at most 400,000 characters; past that it is cut and
says so. ``corpus`` builds the text one model call sees: about 120,000 characters, each source getting a
fair share, each passage labeled ``[P12]`` so every claim can point back at it.
"""

from __future__ import annotations

import hashlib
import html
import io
import re
import time
import zlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS = 400_000
CORPUS_CHARS = 120_000
PASSAGE_TARGET = 900
PASSAGE_MAX = 1600
MAX_PASTE = 400_000
MAX_PDF_PAGES = 2000
PDF_SECONDS = 90  # the whole read of one source PDF; a real report reads in a few seconds


class _PdfStop(BaseException):
    """Raised from inside pypdf's text walk to stop it. A BaseException, so pypdf's own ``except Exception``
    around each form XObject can't swallow it and carry on to the next one."""


def pdf_page_text(page, max_chars: int, deadline: float) -> tuple:
    """One page's text, ``(text, stopped)``: the walk stops once the page has given ``max_chars`` or the clock
    passes ``deadline``. A form XObject painted thousands of times (pypdf allows 5,000 per page), or forms
    nested inside forms, make a 20 KB page extract for hours and hold its whole text in memory; the checks
    run on every operator and every piece of text, inside forms too. What was read before the stop is kept."""
    parts, got = [], [0]

    def on_op(*_a):
        if time.monotonic() > deadline:
            raise _PdfStop()

    def on_text(text, *_a):
        if text:
            parts.append(text)
            got[0] += len(text)
            if got[0] > max_chars:
                raise _PdfStop()

    try:
        return page.extract_text(visitor_operand_before=on_op, visitor_text=on_text) or "", False
    except _PdfStop:
        return "".join(parts)[:max_chars], True

AUDIO_VIDEO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov", ".m4v", ".webm",
               ".mkv", ".avi", ".wma"}
TEXT_EXT = {".txt", ".md", ".markdown"}
TRANSCRIPT_EXT = {".vtt", ".srt"}
ACCEPTED = {".pdf", ".docx"} | TEXT_EXT | TRANSCRIPT_EXT


class Refused(ValueError):
    """A source Letterpress will not take, with the reason a person can act on."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def base_name(name: str) -> str:
    """The file's own name from whatever the system sent: ``C:\\Users\\me\\deck.pptx``, ``/home/me/deck.pptx`` and
    ``deck.pptx`` all give ``deck.pptx``, on Mac, Windows and Linux alike."""
    tail = re.split(r"[\\/]", str(name or ""))[-1]
    tail = re.sub(r"^[a-zA-Z]:", "", tail).strip()
    return "" if tail in (".", "..") else tail


def ext_of(name: str) -> str:
    return Path(base_name(name)).suffix.lower()


def check_upload(filename: str, size: int) -> str:
    ext = ext_of(filename)
    if ext in AUDIO_VIDEO:
        raise Refused("Letterpress can't listen to audio or video. Add its transcript (.vtt, .srt or .txt) instead.")
    if ext == ".doc":
        raise Refused("That is an older Word file. Save it as .docx, then add it again.")
    if ext not in ACCEPTED:
        raise Refused(f"Letterpress can't read {ext or 'that kind of'} files. Add a PDF, Word (.docx), text, Markdown, or transcript file.")
    if size > MAX_BYTES:
        raise Refused("That file is over the 25 MB limit. Split it, or add the pages you need.")
    if size == 0:
        raise Refused("That file is empty.")
    return ext


# ---------------------------------------------------------------- text tools --

_ws = re.compile("[ \t\u00a0]+")


def tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ws.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_long(text: str, limit: int = PASSAGE_MAX) -> list:
    """Split text at sentence ends into pieces no longer than ``limit``."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(sent) + 1 > limit and cur:
            out.append(cur.strip())
            cur = ""
        while len(sent) > limit:
            out.append(sent[:limit])
            sent = sent[limit:]
        cur = f"{cur} {sent}" if cur else sent
    if cur.strip():
        out.append(cur.strip())
    return out


def pack(blocks: list) -> list:
    """Join short blocks that share a locator into passages near PASSAGE_TARGET characters.

    ``blocks`` is ``[(locator, text)]``; returns the same shape."""
    out: list = []
    cur_loc, cur = None, ""
    for loc, text in blocks:
        text = (text or "").strip()
        if not text:
            continue
        if cur and (loc != cur_loc or len(cur) + len(text) > PASSAGE_TARGET):
            out.extend((cur_loc, piece) for piece in split_long(cur))
            cur = ""
        cur_loc = loc
        cur = f"{cur}\n{text}" if cur else text
    if cur:
        out.extend((cur_loc, piece) for piece in split_long(cur))
    return out


def cap_blocks(blocks: list, limit: int = MAX_CHARS):
    total, kept = 0, []
    for loc, text in blocks:
        if total + len(text) > limit:
            room = limit - total
            if room > 200:
                kept.append((loc, text[:room]))
            return kept, True
        kept.append((loc, text))
        total += len(text)
    return kept, False


# ---------------------------------------------------------------- readers --

def read_pdf(data: bytes) -> tuple:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise Refused("Reading PDFs needs the pypdf library, which isn't installed. Reinstall Letterpress to add it.")
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        raise Refused("That PDF looks damaged, so Letterpress can't read it. Open and re-save it, then try again.")
    if getattr(reader, "is_encrypted", False):
        try:
            if reader.decrypt("") == 0:
                raise Refused("That PDF is password-protected. Save an unlocked copy, then add it.")
        except Refused:
            raise
        except Exception:
            raise Refused("That PDF is password-protected. Save an unlocked copy, then add it.")
    blocks = []
    pages = len(reader.pages)
    kept = 0
    deadline = time.monotonic() + PDF_SECONDS
    for i, page in enumerate(reader.pages, start=1):
        if kept > MAX_CHARS or i > MAX_PDF_PAGES or time.monotonic() > deadline:
            break  # a source keeps 400,000 characters; reading on would only spend time and memory on text it drops
        try:
            text, _stopped = pdf_page_text(page, MAX_CHARS - kept + 1, deadline)
        except Exception:
            text = ""
        text = tidy(text)
        kept += len(text)
        for para in re.split(r"\n\s*\n", text):
            para = re.sub(r"(?<![.:;!?])\n(?=[a-z0-9(])", " ", para)  # rejoin wrapped lines
            if para.strip():
                blocks.append((f"p. {i}", para))
    if not blocks:
        raise Refused("That PDF has no text layer (it is probably a scan). Add a version with selectable text.")
    return blocks, pages, "pages"


MAX_UNZIPPED = 150 * 1024 * 1024


def zip_unpacks_safely(data: bytes, what: str) -> None:
    """Refuse a zip-based file (.docx) whose parts would unpack past ``MAX_UNZIPPED``, or that packs
    far more than real documents do, before any library inflates it."""
    import zipfile
    try:
        infos = zipfile.ZipFile(io.BytesIO(data)).infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        raise Refused(f"That {what} looks damaged, so Letterpress can't read it. Open and re-save it, then try again.")
    total = 0
    for i in infos:
        total += i.file_size
        if i.file_size > 16 * 1024 * 1024 and i.file_size / max(1, i.compress_size) > 200:
            raise Refused(f"That {what} unpacks to far more than its size, so Letterpress won't open it. Re-save it, then try again.")
    if total > MAX_UNZIPPED or len(infos) > 5000:
        raise Refused(f"That {what} unpacks to more than Letterpress reads at once. Split it, or add the pages you need.")


def read_docx(data: bytes) -> tuple:
    try:
        import docx  # python-docx
    except ImportError:
        raise Refused("Reading Word files needs the python-docx library, which isn't installed. Reinstall Letterpress to add it.")
    zip_unpacks_safely(data, "Word file")
    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception:
        raise Refused("That Word file looks damaged, so Letterpress can't read it. Open and re-save it as .docx.")
    blocks, heading, n = [], None, 0
    for p in doc.paragraphs:
        text = tidy(p.text or "")
        if not text:
            continue
        style = (getattr(p.style, "name", "") or "").lower()
        if style.startswith("heading") or style == "title":
            heading = text[:80]
            continue
        n += 1
        blocks.append((f"“{heading}”" if heading else f"para. {n}", text))
    for t in doc.tables:
        for r in t.rows:
            cells = [tidy(c.text) for c in r.cells if tidy(c.text)]
            if cells:
                blocks.append((f"“{heading}” table" if heading else "table", " | ".join(cells)))
    if not blocks:
        raise Refused("That Word file has no text Letterpress can read.")
    return blocks, n, "paragraphs"


def read_text(text: str) -> tuple:
    text = tidy(text)
    blocks, heading, n = [], None, 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        m = re.match(r"^(#{1,4})\s+(.+?)\s*#*\s*$", para.split("\n", 1)[0])
        if m:
            heading = m.group(2).strip()[:80]
            rest = para.split("\n", 1)[1] if "\n" in para else ""
            if not rest.strip():
                continue
            para = rest
        n += 1
        blocks.append((f"“{heading}”" if heading else f"para. {n}", para))
    if not blocks:
        raise Refused("There is no readable text in that.")
    return blocks, n, "paragraphs"


_ts = r"(\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"


def _secs(stamp: str) -> int:
    parts = re.split(r"[:]", stamp.replace(",", ".").split(".")[0])
    parts = [int(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _stamp(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m}:{s:02d}]"


def read_transcript(text: str) -> tuple:
    """Cues from WebVTT or SRT, grouped into about 45 seconds per passage."""
    text = text.replace("\r\n", "\n").replace("\ufeff", "")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        idx = next((i for i, l in enumerate(lines) if re.search(_ts + r"\s*-->\s*" + _ts, l)), None)
        if idx is None:
            continue
        start = re.search(_ts, lines[idx]).group(0)
        body = " ".join(lines[idx + 1:])
        body = re.sub(r"<v\s+([^>]+)>", r"\1: ", body)
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            cues.append((_secs(start), body))
    if not cues:
        raise Refused("Letterpress found no timed lines in that transcript. Check that it is a .vtt or .srt file.")
    blocks, window_start, cur = [], cues[0][0], []
    for secs, body in cues:
        if cur and secs - window_start >= 45:
            blocks.append((_stamp(window_start), " ".join(cur)))
            window_start, cur = secs, []
        cur.append(body)
    if cur:
        blocks.append((_stamp(window_start), " ".join(cur)))
    return blocks, len(cues), "lines"


class _HtmlText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "template", "iframe", "button", "select"}
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "td", "th", "dd", "dt", "figcaption", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title = ""
        self.in_title = False
        self.blocks = []
        self.heading = None
        self.buf = []
        self.tag = None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCK:
            self.flush()
            self.tag = tag
        if tag == "br":
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCK:
            self.flush()

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if self.skip:
            return
        self.buf.append(data)

    def flush(self):
        text = tidy(" ".join(self.buf))
        self.buf = []
        tag, self.tag = self.tag, None
        if not text:
            return
        if tag and tag[0] == "h" and len(tag) == 2:
            self.heading = text[:80]
            return
        if len(text) < 25 and tag not in ("li", "td"):
            return
        self.blocks.append((f"“{self.heading}”" if self.heading else "page", text))


def html_to_blocks(page: str) -> tuple:
    p = _HtmlText()
    try:
        p.feed(page)
        p.flush()
    except Exception:
        pass
    return p.blocks, tidy(html.unescape(p.title))[:160]


# ---------------------------------------------------------------- web --

BLOCK_MARKERS = ("cf-chl", "challenge-platform", "just a moment", "attention required", "captcha",
                 "verify you are human", "enable javascript and cookies", "ddos protection", "px-captcha")
BLOCKED = "That site didn't let Letterpress read it. Add the text by pasting it, or save the page as a PDF and add that."
UNSAFE = "Letterpress only reads public web addresses that start with http:// or https://."
PRIVATE = ("That address isn't a public web page, so Letterpress didn't read it. Check the address: Letterpress never reads "
           "pages on this computer or a private network.")


class Blocked(Refused):
    pass


def looks_blocked(status: int, body: str) -> bool:
    low = (body or "")[:20000].lower()
    if status in (401, 403, 429, 503) and any(m in low for m in BLOCK_MARKERS):
        return True
    if status in (403, 429):
        return True
    return any(m in low for m in BLOCK_MARKERS[:4]) and len(low) < 15000


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise Refused("Type a web address first.")
    if len(url) > 2000:
        raise Refused("That web address is too long.")
    if not re.match(r"^https?://", url, re.I):
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) and not url.lower().startswith(("http:", "https:")):
            raise Refused(UNSAFE)
        url = "https://" + url
    return url


TOO_BIG_PAGE = "That page is over the {mb} MB limit, so Letterpress stopped reading it. Save what you need as a file, or paste the text."
CANT_UNPACK = "That site sent a page Letterpress couldn't unpack. Paste the text instead."
TOO_SLOW = "That site took too long to answer. Try again, or paste the text instead."
FETCH_DEADLINE = 60.0  # seconds for the whole read, on top of the 20-second wait for each answer
RAW_FACTOR = 2  # compressed bytes a page may send per byte of the cap (padding that inflates to nothing stops here)
_clock = time.monotonic


def _client_factory():
    from tools.url_safety import create_ssrf_safe_async_client, is_safe_url
    return create_ssrf_safe_async_client, is_safe_url


class _Inflate:
    """The response's own decoding, bounded. httpx would inflate each network chunk whole (a 64 KB gzip chunk can
    become 64 MB at once, and brotli or zstd far more); this asks zlib for no more than the room left under the
    cap, so memory never passes the cap. Only identity, gzip and deflate are accepted, and Letterpress asks for nothing
    else; any other encoding is refused rather than read as garbage."""

    def __init__(self, encoding: str):
        enc = [e.strip() for e in (encoding or "").lower().split(",") if e.strip() and e.strip() != "identity"]
        if len(enc) > 1 or (enc and enc[0] not in ("gzip", "x-gzip", "deflate")):
            raise Refused(CANT_UNPACK)
        self.kind = enc[0] if enc else ""
        self.z = None
        if self.kind in ("gzip", "x-gzip"):
            self.z = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif self.kind == "deflate":
            self.z = zlib.decompressobj()
        self.first = True

    def feed(self, data: bytes, room: int) -> bytes:
        """Up to ``room + 1`` decoded bytes from ``data`` (one past the room means the cap was passed)."""
        if self.z is None:
            return data[:room + 1]
        try:
            return self.z.decompress(data, room + 1)
        except zlib.error:
            if self.kind == "deflate" and self.first:  # some servers send raw deflate with no zlib header
                self.z, self.first = zlib.decompressobj(-zlib.MAX_WBITS), False
                return self.feed(data, room)
            raise Refused(CANT_UNPACK)
        finally:
            self.first = False

    def finish(self, room: int) -> bytes:
        if self.z is None:
            return b""
        try:
            out = self.z.decompress(self.z.unconsumed_tail, room + 1) if self.z.unconsumed_tail else b""
            return out + self.z.flush()[:room + 1 - len(out)]
        except zlib.error:
            raise Refused(CANT_UNPACK)


async def fetch(url: str, max_bytes: int = 5 * 1024 * 1024, accept: str = "text/html,*/*;q=0.8",
                stop_at_cap: bool = False) -> dict:
    """GET a public URL through Hermes's SSRF-safe client. Returns ``{url, status, type, body, raw, cut}``.

    Redirects are followed one hop at a time and each target is checked again. The body is streamed raw and
    inflated here (``_Inflate``): a ``Content-Length`` over the cap is refused before reading, decoded bytes are
    counted as they arrive and never held past ``max_bytes``, compressed bytes are capped too, and the whole read
    has a deadline, so a huge, gzip-bombed, padded or trickled response stops and never fills memory. Past the cap
    the read stops; ``stop_at_cap`` keeps what came in (``cut`` is set), otherwise it is refused."""
    try:
        make_client, is_safe_url = _client_factory()
    except Exception:
        raise Refused("Reading web pages needs Hermes's safe web client, which isn't available here.")
    current = url
    import asyncio
    mb = max(1, max_bytes // (1024 * 1024))
    deadline = _clock() + FETCH_DEADLINE
    for _hop in range(5):
        safe = await asyncio.to_thread(is_safe_url, current)
        if not safe:
            raise Refused(PRIVATE if re.match(r"^https?://", current, re.I) else UNSAFE)
        async with make_client(timeout=20.0, follow_redirects=False,
                               headers={"User-Agent": "Letterpress (Hermes plugin; reads one page a person asked for)",
                                        "Accept": accept, "Accept-Encoding": "gzip, deflate"}) as client:
            try:
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect and resp.headers.get("location"):
                        from urllib.parse import urljoin
                        current = urljoin(str(resp.url), resp.headers["location"])
                        continue
                    length = resp.headers.get("content-length")
                    if length and length.isdigit() and int(length) > max_bytes and not stop_at_cap:
                        raise Refused(TOO_BIG_PAGE.format(mb=mb))
                    inflate = _Inflate(resp.headers.get("content-encoding", ""))
                    chunks, total, raw_total, cut = [], 0, 0, False
                    async for chunk in resp.aiter_raw():
                        if _clock() > deadline:
                            raise Refused(TOO_SLOW)
                        out = inflate.feed(chunk, max_bytes - total)
                        if total + len(out) > max_bytes:
                            chunks.append(out[:max_bytes - total])
                            total = max_bytes
                            cut = True
                            break
                        chunks.append(out)
                        total += len(out)
                        raw_total += len(chunk)
                        if raw_total > max_bytes * RAW_FACTOR:  # compressed padding that inflates to little or nothing
                            cut = True
                            break
                    if not cut:
                        tail = inflate.finish(max_bytes - total)
                        if total + len(tail) > max_bytes:
                            tail, cut = tail[:max_bytes - total], True
                        chunks.append(tail)
                    if cut and not stop_at_cap:
                        raise Refused(TOO_BIG_PAGE.format(mb=mb))
                    body = b"".join(chunks)
                    ctype = resp.headers.get("content-type", "")
                    status, final = resp.status_code, str(resp.url)
            except Refused:
                raise
            except Exception as e:
                name = type(e).__name__.lower()
                if "timeout" in name:
                    raise Refused("That site took too long to answer. Try again, or paste the text instead.")
                if "decod" in name:
                    raise Refused("That site sent a page Letterpress couldn't unpack. Paste the text instead.")
                raise Refused("Letterpress couldn't reach that site. Check the address and your connection.")
            charset = "utf-8"
            m = re.search(r"charset=([\w-]+)", ctype)
            if m:
                charset = m.group(1)
            try:
                text = body.decode(charset, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return {"url": final, "status": status, "type": ctype, "body": text, "raw": body, "cut": cut}
    raise Refused("That address redirects too many times.")


def read_page(fetched: dict) -> tuple:
    status, body = fetched.get("status", 0), fetched.get("body", "")
    if looks_blocked(status, body):
        raise Blocked(BLOCKED)
    if status >= 400:
        raise Refused(f"That page answered with an error ({status}). Check the address.")
    ctype = (fetched.get("type") or "").lower()
    if "pdf" in ctype:
        blocks, units, label = read_pdf(fetched.get("raw") or b"")
        return blocks, units, label, ""
    blocks, title = html_to_blocks(body)
    if not blocks:
        raise Refused("Letterpress found no readable text on that page. It may need JavaScript. Paste the text instead.")
    return blocks, len(blocks), "sections", title


# ---------------------------------------------------------------- corpus --

def corpus(sources: list, passages_by_source: dict, budget: int = CORPUS_CHARS) -> tuple:
    """The labeled text for one model call, and the passage ids it includes.

    Each source gets an equal share of ``budget``; a share a short source leaves unused goes to the
    others, the way the Forge's build_corpus spread its budget."""
    if not sources:
        return "", []
    # Measured with the label and locator each passage carries in the corpus, so a short source always fits whole
    # (an estimate of the label's length used to drop a source's last passage when its locator ran long).
    chunk_of = lambda p: f"[P{p['id']}] ({p['locator']}) {p['text']}"
    lengths = {s["id"]: sum(len(chunk_of(p)) for p in passages_by_source.get(s["id"], [])) for s in sources}
    share, remaining = {}, budget
    order = sorted(lengths, key=lambda sid: lengths[sid])  # short sources first, so their spare room flows on
    for i, sid in enumerate(order):
        give = min(lengths[sid], remaining // (len(order) - i))
        share[sid] = give
        remaining -= give
    parts, ids = [], []
    for n, s in enumerate(sources, start=1):
        used = 0
        head = f"=== SOURCE {n}: {s.get('title') or 'Untitled'} ({s.get('kind')}) ==="
        lines = [head]
        for p in passages_by_source.get(s["id"], []):
            chunk = chunk_of(p)
            if used + len(chunk) > share[s["id"]]:
                break
            lines.append(chunk)
            ids.append(p["id"])
            used += len(chunk)
        parts.append("\n".join(lines))
    return "\n\n".join(parts), ids


def label_title(filename: str) -> str:
    stem = Path(base_name(filename) or "Untitled").stem
    stem = re.sub(r"[_-]+", " ", stem).strip()
    return (stem[:1].upper() + stem[1:])[:120] if stem else "Untitled"
