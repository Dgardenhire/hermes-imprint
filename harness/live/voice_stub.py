"""A harness-only stand-in for Hermes's text_to_speech tool: a silent WAV as long as the script reads at 150 words a
minute, so the live harness can show a chapter playing. It writes a file and never plays anything. Never shipped:
only harness/live/server.py loads it, and only with --voice-stub."""

import re
import struct
from pathlib import Path

RATE = 8000


def silent_wav(seconds: float) -> bytes:
    n = max(1, int(seconds * RATE))
    data = b"\x00\x00" * n
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def dispatch(tool: str, args: dict, timeout: float = 180.0) -> dict:
    if tool != "text_to_speech":
        raise RuntimeError(f"unknown tool {tool}")
    words = len(re.findall(r"\w+", args.get("text") or ""))
    out = Path(args.get("output_path") or "").with_suffix(".wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(silent_wav(words * 60.0 / 150.0))
    return {"success": True, "file_path": str(out)}
