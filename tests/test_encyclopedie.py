"""Sujets pédagogiques du mode science « approfondi » (11/10/2026) — sans réseau."""
import json
from datetime import date

from src.collecte import encyclopedie as enc
from src.generation import briefing_generator as bg
from src.generation.parts import build_parts
from src.generation.science_guard import build_sources_section

SUJETS = [{"id": f"s{i}", "titre": f"Sujet {i}", "wiki": f"Sujet {i}"} for i in range(5)]
TEXTE = ("Le sommeil est un état physiologique récurrent. " * 80)


def faux_fetch(titre):
    return {"titre": titre, "url": "https://fr.wikipedia.org/wiki/" + titre.replace(" ", "_"), "texte": TEXTE}


def test_config_reelle_valide():
    s = enc.charger_sujets()
    assert len(s) >= 30 and len({x["id"] for x in s}) == len(s)


def test_nettoyage_coupe_sections_de_fin_et_longueur():
    t = "Intro.\n\n" + "Phrase utile. " * 100 + "\n\n\nVoir aussi\nAutre"
    out = enc.nettoyer_extrait(t, max_chars=300)
    assert "Voir aussi" not in out and len(out) <= 300 and out.startswith("Intro.")


def test_rotation_deterministe_et_evite_les_sujets_recents():
    o1 = enc.ordre_du_jour(SUJETS, date(2026, 10, 12), set())
    assert o1 == enc.ordre_du_jour(SUJETS, date(2026, 10, 12), set())
    premier = o1[0]["id"]
    o2 = enc.ordre_du_jour(SUJETS, date(2026, 10, 12), {premier})
    assert o2[0]["id"] != premier and o2[-1]["id"] == premier


def test_choix_saute_les_articles_introuvables():
    appels = []

    def fetch(t):
        appels.append(t)
        return None if len(appels) == 1 else faux_fetch(t)
    topic = enc.choisir_sujet_pedagogique(date(2026, 10, 12), SUJETS, set(), fetch)
    cs = topic["contenu_source"]
    assert len(appels) == 2 and topic["mode"] == "approfondi"
    assert cs["origine"] == "encyclopedie" and cs["matiere"] == "suffisante" and cs["sujet_id"].startswith("s")
    assert cs["textes_sources"][0]["resume"] == TEXTE and cs["liens_sources"][0]["url"].startswith("https://fr.wikipedia.org")


def test_aucun_texte_recuperable_retourne_none():
    assert enc.choisir_sujet_pedagogique(date(2026, 10, 12), SUJETS, set(), lambda t: None) is None


def test_historique_lit_les_sujet_id(tmp_path):
    for d, sid in (("2026-10-10", "sommeil"), ("2026-10-11", "co2"), ("2026-10-09", None)):
        (tmp_path / f"{d}.json").write_text(json.dumps({"briefing": {"science": {"sujet_id": sid}}}), encoding="utf-8")
    (tmp_path / "latest.json").write_text("{}", encoding="utf-8")
    assert enc.sujets_deja_utilises([tmp_path]) == {"sommeil", "co2"}


NEWS_FINE = {"mode": "approfondi", "contenu_source": {"titre": "Interview", "resume": "Court.", "matiere": "fine", "sources": ["Le Monde Sciences"]}}


def test_completer_prefere_le_sujet_pedagogique(monkeypatch):
    monkeypatch.setattr(enc, "choisir_sujet_pedagogique", lambda jour=None: {"mode": "approfondi", "contenu_source": {"origine": "encyclopedie"}})
    assert bg.completer_sujet_pedagogique(NEWS_FINE)["contenu_source"]["origine"] == "encyclopedie"


def test_completer_matiere_fine_sans_wikipedia_devient_indisponible(monkeypatch):
    monkeypatch.setattr(enc, "choisir_sujet_pedagogique", lambda jour=None: None)
    t = bg.completer_sujet_pedagogique(NEWS_FINE)
    assert t["mode"] == "indisponible"
    assert "science_a" not in build_parts({"actualite_france": [], "actualite_monde": [], "marches_data": {}, "sport_events": {}}, t, None, False)


def test_completer_garde_une_actualite_a_matiere_suffisante(monkeypatch):
    monkeypatch.setattr(enc, "choisir_sujet_pedagogique", lambda jour=None: None)
    n = {"mode": "approfondi", "contenu_source": {"titre": "x", "matiere": "suffisante"}}
    assert bg.completer_sujet_pedagogique(n) is n


def test_completer_ne_touche_pas_au_mode_decouverte(monkeypatch):
    monkeypatch.setattr(enc, "choisir_sujet_pedagogique", lambda jour=None: (_ for _ in ()).throw(AssertionError("appelé")))
    d = {"mode": "decouverte", "contenu_source": {}}
    assert bg.completer_sujet_pedagogique(d) is d


def test_exception_reseau_ne_casse_pas_le_run(monkeypatch):
    def boom(jour=None):
        raise RuntimeError("réseau")
    monkeypatch.setattr(enc, "choisir_sujet_pedagogique", boom)
    assert bg.completer_sujet_pedagogique(NEWS_FINE)["mode"] == "indisponible"


def test_sources_encyclopedie_signalees_non_primaires():
    s = build_sources_section({"origine": "encyclopedie", "liens_sources": [{"nom": "Wikipédia (fr) — Sommeil", "url": "https://x"}]})
    assert "Wikipédia" in s and "non primaire" in s
