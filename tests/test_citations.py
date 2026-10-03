from datetime import date, timedelta

from src.generation.citations import load_bank, pick_citation


def test_banque_valide_et_sans_doublon():
    bank = load_bank()
    assert len(bank) >= 20
    assert all(c["texte"] and c["auteur"] and c["source"] and c["annee"] for c in bank)
    assert len({c["texte"] for c in bank}) == len(bank)


def test_tirage_deterministe_et_sans_repetition_sur_la_banque():
    bank = load_bank()
    d = date(2026, 10, 5)
    assert pick_citation(d) == pick_citation(d)
    jours = {pick_citation(d + timedelta(days=i))["texte"] for i in range(len(bank))}
    assert len(jours) == len(bank)


def test_banque_vide_donne_none():
    assert pick_citation(date(2026, 10, 5), bank=[]) is None
