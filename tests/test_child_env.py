"""Programs the plugin starts (the headless browser that draws designs, the browser that reads a website, and macOS
``sips``) get only an allowlisted environment: a provider key set in this process never reaches them, PATH does.

Each check starts a real child process: a small shell script stands in for the browser or ``sips`` and writes the
environment it was given to a file."""
import os
import stat
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest import mock

from _load import PKG, service

CE = import_module(f"{PKG}.childenv")
HD = import_module(f"{PKG}.htmldeck")
SS = import_module(f"{PKG}.sitestyle")

SECRET = "OPENAI_" + "API_KEY"  # put together at run time; the value is plainly not a key
SECRET_VALUE = "planted-for-the-test-" + "x" * 6
HERMES_ONLY = "HERMES_" + "SESSION_HINT"


def _planted():
    """This process's environment plus a provider key and a Hermes-only variable."""
    env = dict(os.environ)
    env[SECRET] = SECRET_VALUE
    env[HERMES_ONLY] = "anything"
    env.setdefault("PATH", os.defpath)
    return env


def _stand_in(folder: Path, dump: Path, touch_last_arg: bool = False) -> str:
    """A program that records its environment in ``dump`` (and, for ``sips``, creates the file named by its last argument)."""
    script = folder / "stand-in"
    body = "#!/bin/sh\n/usr/bin/env > '%s'\n" % dump
    if touch_last_arg:
        body += 'for last in "$@"; do :; done\nprintf png > "$last"\n'
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def _read(dump: Path) -> dict:
    out = {}
    for line in dump.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


class Allowlist(unittest.TestCase):
    def test_only_the_listed_names_are_copied(self):
        env = {"PATH": "/usr/bin", "HOME": "/home/x", "TMPDIR": "/tmp/x", "LANG": "en_US.UTF-8", "LC_ALL": "C",
               "LC_CTYPE": "UTF-8", SECRET: SECRET_VALUE, HERMES_ONLY: "1", "DISPLAY": ":0", "SYSTEMROOT": r"C:\Windows",
               "DBUS_SESSION_BUS_ADDRESS": "unix:path=/x", "PROGRAMFILES": r"C:\Program Files"}
        self.assertEqual(CE.child_env(env, "mac"), {"PATH": "/usr/bin", "HOME": "/home/x", "TMPDIR": "/tmp/x",
                                                    "LANG": "en_US.UTF-8", "LC_ALL": "C", "LC_CTYPE": "UTF-8"})
        linux = CE.child_env(env, "linux")
        self.assertEqual(linux.get("DISPLAY"), ":0")
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", linux)
        self.assertNotIn("SYSTEMROOT", linux)
        win = CE.child_env(env, "win")
        self.assertEqual(win.get("SYSTEMROOT"), r"C:\Windows")
        self.assertNotIn("PROGRAMFILES", win)
        self.assertNotIn("DISPLAY", win)
        for plat in ("mac", "linux", "win"):
            got = CE.child_env(env, plat)
            self.assertNotIn(SECRET, got)
            self.assertNotIn(HERMES_ONLY, got)

    def test_windows_names_match_in_any_case(self):
        got = CE.child_env({"Path": r"C:\bin", "SystemRoot": r"C:\Windows", "userprofile": r"C:\Users\x", SECRET: "v"}, "win")
        self.assertEqual(got, {"Path": r"C:\bin", "SystemRoot": r"C:\Windows", "userprofile": r"C:\Users\x"})

    def test_a_missing_path_gets_the_default(self):
        self.assertEqual(CE.child_env({"HOME": "/h"}, "mac")["PATH"], os.defpath)

    def test_the_result_is_a_new_dict(self):
        env = {"PATH": "/usr/bin"}
        got = CE.child_env(env, "mac")
        got["X"] = "1"
        self.assertNotIn("X", env)


@unittest.skipIf(sys.platform.startswith("win"), "the stand-in programs are shell scripts")
class RealChildren(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="childenv-"))
        self.dump = self.dir / "env.txt"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def check(self, got: dict):
        self.assertNotIn(SECRET, got)
        self.assertNotIn(SECRET_VALUE, "\n".join(got.values()))
        self.assertNotIn(HERMES_ONLY, got)
        self.assertEqual(got.get("PATH"), os.environ.get("PATH", os.defpath))
        allowed = set(CE.allowed_names())
        self.assertTrue(all(k in allowed or k.startswith("LC_") or k in ("PWD", "SHLVL", "_", "OLDPWD") for k in got), got)

    def test_the_browser_that_draws_designs(self):
        exe = _stand_in(self.dir, self.dump)
        with mock.patch.dict(os.environ, _planted(), clear=True), mock.patch.object(HD, "browser_path", lambda: exe):
            HD._chrome(["--version"], timeout=30)
        self.check(_read(self.dump))

    def test_the_browser_that_reads_a_website(self):
        exe = _stand_in(self.dir, self.dump)
        r1, w1 = os.pipe()
        r2, w2 = os.pipe()
        try:
            with mock.patch.dict(os.environ, _planted(), clear=True):
                child = SS._spawn([exe], r1, w2)
            self.assertEqual(child.wait(30), 0)
        finally:
            for fd in (r1, w1, r2, w2):
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.check(_read(self.dump))

    def test_sips_for_a_one_pager_preview(self):
        exe = _stand_in(self.dir, self.dump, touch_last_arg=True)
        import shutil as real_shutil
        which = real_shutil.which
        with mock.patch.dict(os.environ, _planted(), clear=True), \
                mock.patch.object(real_shutil, "which", lambda name, *a, **k: exe if name == "sips" else which(name, *a, **k)), \
                mock.patch.object(service.KITS, "palette", lambda kit: {}), \
                mock.patch.object(service.KITS, "faces", lambda kit: {}), \
                mock.patch.object(service.KITS, "logo_variants", lambda kit, pal: {}), \
                mock.patch.object(service.L, "source_index", lambda doc, by_ref: ({}, [])), \
                mock.patch.object(service.F, "colophon", lambda faces, n: ""), \
                mock.patch.object(service.RP, "render", lambda *a, **k: b"%PDF-1.4\n"):
            png = service._page_png({"title": "t"}, {}, {})
        self.assertEqual(png, b"png")
        self.check(_read(self.dump))


if __name__ == "__main__":
    unittest.main()
