"""Fill a running live-mode server with a real notebook, through the real routes, for screenshots and a walkthrough.

    /usr/bin/python3 harness/live/server.py 8790 --data /tmp/imprint-nb &
    /usr/bin/python3 harness/live/seed_notebook.py 8790

Adds the three warming-center samples (samples/), waits for their summaries, asks two questions that need more than one
source, pins one answer as a note, adds a typed note, unticks nothing, and makes a deck in Counsel, a graphic in Chart
Room, a one-pager in Folio and an audio brief in Stage (the live harness has no voice, so the audio brief shows the
no-voice path honestly). The scripted model (persona_model.py) writes each from the passages, citing them.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + "/api/" + path, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def wait(base, job, limit=120):
    t = time.time()
    while time.time() - t < limit:
        j = call(base, "GET", f"jobs/{job['id']}")
        if j["status"] != "running":
            return j
        time.sleep(0.3)
    raise SystemExit(f"job {job['id']} did not finish")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    base = f"http://127.0.0.1:{port}"
    ids = []
    for name in ("warming-center-report.md", "council-work-session.vtt", "guest-and-volunteer-survey.txt"):
        data = base64.b64encode((REPO / "samples" / name).read_bytes()).decode()
        j = wait(base, call(base, "POST", "sources/file", {"filename": name, "data": data})["job"])
        ids.append(j["result"]["source"]["id"])
    for _ in range(100):
        st = call(base, "GET", "state")
        if all(s["summary"] for s in st["sources"]):
            break
        time.sleep(0.3)
    chats = []
    for q in ("What did the season cost, and who paid?", "Why do council members want a second site?"):
        j = wait(base, call(base, "POST", "ask", {"question": q, "source_ids": ids})["job"])
        chats.append(j["result"]["chat"])
    call(base, "POST", "notes", {"chat_id": chats[1]["id"]})
    call(base, "POST", "notes", {"text": "Lead with the walk across the river: that is what moved the council."})
    notes = [n["id"] for n in call(base, "GET", "notes")["notes"]]
    made = {}
    for kind, kit, brief in (("audio", "stage", "A three-minute brief for the drive in"),
                             ("onepager", "folio", "A one-page brief for the council"),
                             ("visual", "chart-room", "One graphic for the newsletter: who paid for the season"),
                             ("deck", "counsel", "A short deck for the April 8 budget work session")):
        j = wait(base, call(base, "POST", "outputs", {"kind": kind, "source_ids": ids, "kit_ids": [kit], "brief": brief, "note_ids": notes,
                                                     "pictures": False})["job"])
        made[kind] = j["result"]["output_id"] if j["status"] == "done" else j["error"]
    call(base, "POST", "prefs", {"kit": "counsel"})
    print(json.dumps({"sources": ids, "chats": [c["id"] for c in chats], "made": made}, indent=2))


if __name__ == "__main__":
    main()
