"""Tests (sans réseau) de l'organisation main/dev : dossier de sortie configurable,
TEST_MODE, garde-fou « un test ne touche jamais la production ».
Lancer : python -m unittest discover -s tests -v
"""
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import utils
from src.stockage import storage


class ResolveDataDirTests(unittest.TestCase):
    def test_default_is_production_dir(self):
        self.assertEqual(storage.resolve_data_dir({}), storage.PROD_DATA_DIR)
        self.assertTrue(str(storage.PROD_DATA_DIR).endswith("docs/data/briefings"))

    def test_relative_env_is_resolved_from_repo_root(self):
        p = storage.resolve_data_dir({"BRIEFING_OUTPUT_DIR": "test-output"})
        self.assertEqual(p, storage.ROOT / "test-output")

    def test_absolute_env_is_kept(self):
        self.assertEqual(storage.resolve_data_dir({"BRIEFING_OUTPUT_DIR": "/tmp/x"}), Path("/tmp/x"))

    def test_test_mode_refuses_production_dir(self):
        with self.assertRaises(RuntimeError):
            storage.resolve_data_dir({"TEST_MODE": "true"})
        with self.assertRaises(RuntimeError):
            storage.resolve_data_dir({"TEST_MODE": "true", "BRIEFING_OUTPUT_DIR": "docs/data/briefings"})

    def test_test_mode_with_other_dir_ok(self):
        p = storage.resolve_data_dir({"TEST_MODE": "true", "BRIEFING_OUTPUT_DIR": "test-output"})
        self.assertEqual(p, storage.ROOT / "test-output")

    def test_test_mode_false_keeps_production_allowed(self):
        self.assertEqual(storage.resolve_data_dir({"TEST_MODE": "false"}), storage.PROD_DATA_DIR)


class IsTestModeTests(unittest.TestCase):
    def test_values(self):
        for v, expected in [("true", True), ("TRUE", True), ("1", True), ("false", False), ("", False)]:
            with mock.patch.dict(os.environ, {"TEST_MODE": v}):
                self.assertEqual(utils.is_test_mode(), expected, v)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(utils.is_test_mode())

    def test_logs_dir(self):
        self.assertEqual(utils.resolve_logs_dir({}), utils.ROOT / "logs")
        self.assertEqual(utils.resolve_logs_dir({"BRIEFING_LOGS_DIR": "test-output/logs"}),
                         utils.ROOT / "test-output" / "logs")


class SaveInTestOutputTests(unittest.TestCase):
    """Sauvegarde réelle dans un dossier temporaire : la production n'est pas touchée et
    la mémoire (latest.json copié depuis main) est bien lue."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.prod_before = sorted(p.name for p in storage.PROD_DATA_DIR.glob("*")) \
            if storage.PROD_DATA_DIR.exists() else []
        patcher = mock.patch.object(storage, "DATA_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_day_briefing_exists_uses_output_dir(self):
        self.assertFalse(storage.day_briefing_exists("2099-01-01"))
        (self.tmp / "2099-01-01.json").write_text("{}")
        self.assertTrue(storage.day_briefing_exists("2099-01-01"))

    def test_save_marks_test_mode_and_leaves_production_untouched(self):
        with mock.patch.dict(os.environ, {"TEST_MODE": "true"}):
            storage.save_briefing({"_genere_par_llm": False}, "2099-01-01", "2099-01-01T06:30:00+02:00")
        env = json.loads((self.tmp / "2099-01-01.json").read_text())
        self.assertTrue(env["test_mode"])
        self.assertTrue((self.tmp / "latest.json").exists())
        after = sorted(p.name for p in storage.PROD_DATA_DIR.glob("*")) if storage.PROD_DATA_DIR.exists() else []
        self.assertEqual(self.prod_before, after)
        self.assertFalse((storage.PROD_DATA_DIR / "2099-01-01.json").exists())

    def test_save_in_production_mode_has_no_test_marker(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            storage.save_briefing({}, "2099-01-02", "2099-01-02T06:30:00+02:00")
        env = json.loads((self.tmp / "2099-01-02.json").read_text())
        self.assertNotIn("test_mode", env)

    def test_last_successful_datetime_read_from_copied_history(self):
        (self.tmp / "latest.json").write_text(json.dumps({"derniere_mise_a_jour": "2026-10-01T04:15:00+02:00"}))
        self.assertEqual(storage.get_last_successful_datetime().year, 2026)


if __name__ == "__main__":
    unittest.main()
