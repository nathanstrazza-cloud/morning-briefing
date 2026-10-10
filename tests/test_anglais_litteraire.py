"""Anglais du jour (10/10/2026) : banque de passages littéraires + traductions en ligne, sans LLM."""
import re
from datetime import date, timedelta

from src.generation import anglais_litteraire as al


def test_banque_valide():
    bank = al.load_bank()
    assert len(bank) >= 9
    for p in bank:
        n = len(p["texte"].split())
        assert 60 <= n <= 170, (p["oeuvre"], n)             # ~10 lignes
        assert p["annee"] and p["annee"] < 1930              # domaine public sans ambiguïté
        assert len(p["mots"]) >= 6, p["oeuvre"]


def test_chaque_glose_est_trouvee_et_ne_chevauche_pas():
    for p in al.load_bank():
        for m in p["mots"]:
            assert re.search(r"(?<!\w)" + re.escape(m["en"]) + r"(?!\w)", p["texte"], re.IGNORECASE), (p["oeuvre"], m["en"])
        seg = al.build_segments(p["texte"], p["mots"])
        assert sum(1 for s in seg if s["g"]) == len(p["mots"]), p["oeuvre"]       # aucune glose perdue
        assert "".join(s["t"] for s in seg) == p["texte"]                          # texte intact


def test_format_en_ligne():
    out = al.passage_du_jour(date(2026, 10, 12), [{"oeuvre": "X", "auteur": "Y", "annee": 1900,
                                                  "texte": "I like apples and I like sundry things.",
                                                  "mots": [{"en": "sundry", "fr": "divers"}]}])
    assert out["texte_glose"] == "I like apples and I like sundry (= divers) things."
    assert out["segments"][-1] == {"t": " things.", "g": None}


def test_tirage_deterministe_et_tournant():
    bank = al.load_bank()
    j = date(2026, 10, 12)
    assert al.passage_du_jour(j)["oeuvre"] == al.passage_du_jour(j)["oeuvre"]
    assert len({al.passage_du_jour(j + timedelta(days=i))["oeuvre"] for i in range(len(bank))}) == len(bank)


def test_banque_vide_donne_none():
    assert al.passage_du_jour(date(2026, 10, 12), []) is None
