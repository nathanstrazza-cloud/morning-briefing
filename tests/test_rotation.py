"""Tests (sans réseau) de la rotation des briefings (14/10/2026)."""
import json
import tempfile
import unittest
from pathlib import Path

from src.collecte import encyclopedie
from src.stockage import storage


def _remplir(d: Path, n: int, depart: int = 1):
    dates = [f"2026-09-{i:02d}" for i in range(depart, depart + n)]
    for x in dates:
        (d / f"{x}.json").write_text(json.dumps({"briefing": {"science": {"sujet_id": "s" + x}}}), encoding="utf-8")
    (d / "index.json").write_text(json.dumps({"dates": sorted(dates, reverse=True)}), encoding="utf-8")
    (d / "latest.json").write_text("{}", encoding="utf-8")
    return dates


class RotationTests(unittest.TestCase):
    def test_garde_les_n_plus_recents_et_archive_le_reste(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            dates = _remplir(d, 12)
            moved = storage.rotate_briefings(keep=5, data_dir=d)
            self.assertEqual(len(moved), 7)
            restants = sorted(p.name for p in d.glob("20??-??-??.json"))
            self.assertEqual(restants, [f"{x}.json" for x in dates[-5:]])
            self.assertEqual(len(list((d / "archives").glob("*.json"))), 7)   # rien n'est supprimé
            self.assertTrue((d / "latest.json").exists())
            idx = json.loads((d / "index.json").read_text(encoding="utf-8"))["dates"]
            self.assertEqual(idx, sorted(dates[-5:], reverse=True))

    def test_rien_a_faire_sous_le_seuil(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            _remplir(d, 3)
            self.assertEqual(storage.rotate_briefings(keep=30, data_dir=d), [])
            self.assertFalse((d / "archives").exists())

    def test_sujets_science_des_archives_restent_visibles(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            _remplir(d, 10)
            storage.rotate_briefings(keep=2, data_dir=d)
            ids = encyclopedie.sujets_deja_utilises([d], n=45)
            self.assertEqual(len(ids), 10)


if __name__ == "__main__":
    unittest.main()
