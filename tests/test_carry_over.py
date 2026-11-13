"""Data kept under the plugin's earlier name is copied into Letterpress's folder once: copied, never moved; nothing in
the new folder overwritten; only this plugin's own database; whole or not at all. Temporary folders only."""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from importlib import import_module
from pathlib import Path
from unittest import mock

from _load import PKG, store

CO = import_module(f"{PKG}.carryover")
R = import_module(f"{PKG}.runtime")


def _tree(folder: Path) -> dict:
    """Every file under ``folder`` with its bytes' hash, so a test can see that nothing in it changed."""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            p = Path(root) / name
            out[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _make_db(path: Path, title: str = "Harborlight FY26 report", wal: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    if wal:
        c.execute("PRAGMA journal_mode=WAL")
    c.executescript(store.SCHEMA)
    c.execute("INSERT INTO sources(id, title) VALUES('s1', ?)", (title,))
    c.execute("INSERT INTO settings(key, value) VALUES('prefs', '{\"kit\": \"harborlight\"}')")
    c.commit()
    c.close()


def _rows(path: Path, sql: str) -> list:
    """Rows from a database in the new folder (opened the way the plugin opens it)."""
    c = sqlite3.connect(str(path))
    try:
        return [tuple(r) for r in c.execute(sql).fetchall()]
    finally:
        c.close()


class CarryOver(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="letterpress-carry-"))
        self.old = self.root / "plugin-data" / "imprint"
        self.new = self.root / "plugin-data" / "letterpress"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def earlier_install(self, wal: bool = False):
        _make_db(self.old / CO.EARLIER_DB, wal=wal)
        (self.old / "sources").mkdir(parents=True)
        (self.old / "sources" / "abc123.pdf").write_bytes(b"%PDF-1.4 a source")
        (self.old / "kits" / "harborlight").mkdir(parents=True)
        (self.old / "kits" / "harborlight" / "kit.json").write_text('{"name": "Harborlight"}')
        (self.old / "outputs" / "o1" / "designs").mkdir(parents=True)
        (self.old / "outputs" / "o1" / "designs" / "state.json").write_text('{"final": "<img src=\\"imprint:logo\\">"}')
        (self.old / "debug.log").write_text("12:00:00 a line\n")
        _make_db(self.old / "sample" / CO.EARLIER_DB, title="Sample source")

    def test_nothing_to_carry(self):
        self.assertEqual(CO.carry_over(self.new, self.old), "none")  # no earlier folder
        self.old.mkdir(parents=True)
        (self.old / "notes.txt").write_text("x")
        self.assertEqual(CO.carry_over(self.new, self.old), "none")  # a folder with no database
        self.assertFalse((self.new / "notes.txt").exists())

    def test_another_plugins_folder_under_the_same_name_is_left_alone(self):
        self.old.mkdir(parents=True)
        c = sqlite3.connect(str(self.old / CO.EARLIER_DB))
        c.execute("CREATE TABLE stamps(id INTEGER PRIMARY KEY, text TEXT)")
        c.commit()
        c.close()
        (self.old / "theirs.json").write_text("{}")
        self.assertEqual(CO.carry_over(self.new, self.old), "none")
        self.assertFalse(self.new.exists() and any(self.new.iterdir()))

    def test_copies_everything_and_leaves_the_earlier_folder_as_it_was(self):
        self.earlier_install()
        before = _tree(self.old)
        self.assertEqual(CO.carry_over(self.new, self.old), "carried")
        self.assertEqual(_tree(self.old), before, "the earlier folder is unchanged")
        db = self.new / CO.NEW_DB
        self.assertEqual(_rows(db, "SELECT id, title FROM sources"), [("s1", "Harborlight FY26 report")])
        self.assertEqual(_rows(db, "SELECT key FROM settings"), [("prefs",)])
        self.assertEqual(_rows(self.new / "sample" / CO.NEW_DB, "SELECT title FROM sources"), [("Sample source",)])
        for rel in ("sources/abc123.pdf", "kits/harborlight/kit.json", "outputs/o1/designs/state.json", "debug.log"):
            self.assertEqual((self.new / rel).read_bytes(), (self.old / rel).read_bytes(), rel)
        self.assertTrue((self.new / CO.MARKER).exists())
        self.assertFalse((self.new / CO.EARLIER_DB).exists(), "the database takes the new name")
        self.assertEqual([p for p in self.new.rglob("*") if ".carrying-" in p.name], [])

    def test_writes_not_yet_checkpointed_are_carried_too(self):
        _make_db(self.old / CO.EARLIER_DB, wal=True)
        keep = sqlite3.connect(str(self.old / CO.EARLIER_DB))  # the earlier plugin still has it open
        keep.execute("PRAGMA wal_autocheckpoint=0")
        keep.execute("INSERT INTO sources(id, title) VALUES('s2', 'added last')")
        keep.commit()
        try:
            self.assertEqual(CO.carry_over(self.new, self.old), "carried")
        finally:
            keep.close()
        self.assertEqual(len(_rows(self.new / CO.NEW_DB, "SELECT id FROM sources")), 2)

    def test_letterpress_data_already_there_wins(self):
        self.earlier_install()
        _make_db(self.new / CO.NEW_DB, title="made in Letterpress")
        new_before, old_before = _tree(self.new), _tree(self.old)
        self.assertEqual(CO.carry_over(self.new, self.old), "skipped")
        self.assertEqual(_tree(self.new), new_before)
        self.assertEqual(_tree(self.old), old_before)

    def test_a_file_already_in_the_new_folder_is_kept(self):
        self.earlier_install()
        (self.new / "kits" / "harborlight").mkdir(parents=True)
        (self.new / "kits" / "harborlight" / "kit.json").write_text('{"name": "newer"}')
        self.assertEqual(CO.carry_over(self.new, self.old), "carried")
        self.assertEqual((self.new / "kits" / "harborlight" / "kit.json").read_text(), '{"name": "newer"}')

    def test_a_second_call_changes_nothing(self):
        self.earlier_install()
        self.assertEqual(CO.carry_over(self.new, self.old), "carried")
        c = sqlite3.connect(str(self.new / CO.NEW_DB))
        c.execute("UPDATE sources SET title='edited in Letterpress'")
        c.commit()
        c.close()
        (self.old / "sources" / "later.pdf").write_bytes(b"added to the earlier folder afterwards")
        self.assertEqual(CO.carry_over(self.new, self.old), "skipped")
        self.assertEqual(_rows(self.new / CO.NEW_DB, "SELECT title FROM sources"), [("edited in Letterpress",)])
        self.assertFalse((self.new / "sources" / "later.pdf").exists())

    def test_a_failed_copy_leaves_nothing_half_done_and_is_tried_again(self):
        self.earlier_install()
        old_before = _tree(self.old)
        real = CO._copy_db

        def broken(src, target):
            if target.parent == self.new:
                raise sqlite3.OperationalError("disk I/O error")
            return real(src, target)
        with mock.patch.object(CO, "_copy_db", broken):
            self.assertEqual(CO.carry_over(self.new, self.old), "failed")
        self.assertEqual(_tree(self.new), {}, "every file the failed copy made is gone")
        self.assertEqual(_tree(self.old), old_before)
        self.assertEqual(CO.carry_over(self.new, self.old), "carried")

    def test_placing_never_replaces_a_file_another_process_put_there(self):
        self.new.mkdir(parents=True)
        target, tmp = self.new / "x.json", self.new / "x.json.carrying-1"
        target.write_text("first")
        tmp.write_text("second")
        self.assertFalse(CO._place(tmp, target))
        self.assertEqual(target.read_text(), "first")
        self.assertFalse(tmp.exists())

    def test_forget_everything_keeps_the_marker_so_nothing_comes_back(self):
        self.earlier_install()
        data = Path(R.base_dir())
        (data / CO.MARKER).write_text("copied\n")
        (data / "debug.log").write_text("x\n")
        store.forget_everything()
        self.assertEqual(sorted(p.name for p in data.iterdir()), [CO.MARKER])
        self.assertEqual(CO.carry_over(data, self.old), "skipped")
        (data / CO.MARKER).unlink()

    def test_the_plugin_carries_over_on_first_open_of_its_folder(self):
        self.earlier_install()
        fake = types.ModuleType("plugins.plugin_storage")

        def plugin_data_dir(name):
            p = self.root / "plugin-data" / name
            p.mkdir(parents=True, exist_ok=True)
            return p
        fake.plugin_data_dir = plugin_data_dir
        pkg = types.ModuleType("plugins")
        pkg.plugin_storage = fake
        env = {k: v for k, v in os.environ.items() if k not in (R.DATA_DIR_VAR, R.EARLIER_DATA_DIR_VAR)}
        with mock.patch.dict(sys.modules, {"plugins": pkg, "plugins.plugin_storage": fake}), \
                mock.patch.dict(os.environ, env, clear=True), mock.patch.object(CO, "_done", set()):
            self.assertEqual(R.base_dir(), self.new)
            self.assertEqual(_rows(self.new / CO.NEW_DB, "SELECT id FROM sources"), [("s1",)])
            self.assertEqual(R.base_dir(), self.new)  # once per folder in a process
        self.assertTrue((self.old / CO.EARLIER_DB).exists())


if __name__ == "__main__":
    unittest.main()
