"""A stand-in for Imprint's model runtime that talks to ``claude -p`` (harness only; inside Hermes the runtime is Hermes's model).

``structured(system, instructions, body, schema, purpose, images=...)`` returns the parsed JSON the model wrote. Images are written
next to the work folder and named in the prompt; the model opens them with the Read tool."""
import asyncio, json, re
from pathlib import Path


def parse(text: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i = t.find("{")
    obj, _ = json.JSONDecoder().raw_decode(t[i:])
    return obj


class ClaudeCLI:
    def __init__(self, model, workdir):
        self.model, self.workdir = model, Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.calls = []

    async def structured(self, *, system, instructions, body, schema, purpose, max_tokens=0, timeout=0, images=None):
        prompt = f"{instructions}\n\n{body}"
        cmd = ["claude", "-p", "--model", self.model, "--output-format", "text", "--system-prompt", system, "--strict-mcp-config",
               "--disable-slash-commands", "--setting-sources", "local"]
        if images:
            names = []
            for i, im in enumerate(images, 1):
                if isinstance(im, dict) and isinstance(im.get("data"), (bytes, bytearray)):
                    name = f"shot-{purpose.replace('.', '-')}-{i}.png"
                    (self.workdir / name).write_bytes(im["data"])
                    names.append(str(self.workdir / name))
            if names:
                prompt += "\n\nSCREENSHOT FILES (open each with the Read tool and look at it before you answer):\n" + "\n".join(names)
            cmd += ["--tools", "Read", "--allowedTools", "Read", "--add-dir", str(self.workdir)]
        else:
            cmd += ["--tools", ""]
        for attempt in range(2):  # the real runtime also tries once more when a reply is not valid JSON
            pr = prompt if attempt == 0 else prompt + "\n\nYour last reply was not valid JSON. Reply again as one complete, valid JSON object."
            p = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.PIPE, cwd=str(self.workdir))
            out, err = await asyncio.wait_for(p.communicate(pr.encode()), timeout=900)
            txt = out.decode()
            self.calls.append({"purpose": purpose, "chars_in": len(pr), "chars_out": len(txt)})
            try:
                return parse(txt)
            except Exception:
                (self.workdir / f"bad-{purpose}-{attempt}.txt").write_text(txt + "\n---\n" + err.decode())
        raise ValueError("The model did not return valid JSON twice.")
