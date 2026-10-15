"""15/10/2026 : une découverte (160-295 mots) est toujours suivie d'un dossier approfondi (science trop courte sinon)."""
from src.generation import briefing_generator as bg
from src.generation import parts as parts_mod
from src.generation.llm_orchestrator import PartResult, load_plan

MOTS = lambda n, m="alpha": " ".join([m] * n)


def _topic(titre, origine=None):
    cs = {"titre": titre, "resume": "résumé " * 40, "url": "u", "sources": ["Nature News"], "liens_sources": [],
          "textes_sources": [{"source": "Nature News", "titre": titre, "resume": "résumé " * 40}], "matiere": "suffisante"}
    if origine:
        cs.update({"origine": origine, "sujet_id": "sommeil"})
    return {"mode": "approfondi" if origine else "decouverte", "contenu_source": cs}


def _ok(name, body):
    return PartResult(name, body=body, provider="mistral")


def _bodies(a=True, b=True, d=True):
    r = {}
    r["science_a"] = _ok("science_a", {"science": {"mode": "approfondi", "titre": "Le sommeil", "contenu_markdown": "## 1. Intro\n\n" + MOTS(400)}}) if a else PartResult("science_a", attempts=["x"])
    r["science_b"] = _ok("science_b", {"contenu_markdown": "## 5. Données\n\n" + MOTS(400)}) if b else PartResult("science_b", attempts=["x"])
    r["science_d"] = _ok("science_d", {"science": {"mode": "decouverte", "titre": "Zones protégées", "contenu_markdown": MOTS(200)}}) if d else PartResult("science_d", attempts=["x"])
    return r


def _merge(results):
    topic = _topic("Zones protégées")
    topic["approfondissement"] = _topic("Le sommeil", origine="encyclopedie")
    res = {"citation": None, "actualite": {"france": [], "monde": []}, "science": {}}
    parts_mod.merge_results(res, results, None, science_source=topic["contenu_source"], analysed=None,
                            science_approf_source=topic["approfondissement"]["contenu_source"])
    return res["science"]


def test_plan_declare_science_d():
    # build_parts exige beaucoup de données d'actualité : on vérifie le plan (science_d déclaré) ; la fusion est testée ci-dessous
    plan = load_plan()
    noms = [n for w in plan["waves"] for st in w["stages"] for n in st["parts"]]
    assert "science_d" in noms and "science_a" in noms and "science_b" in noms


def test_ajouter_approfondissement_ajoute_le_sujet(monkeypatch):
    from src.collecte import encyclopedie
    monkeypatch.setattr(encyclopedie, "choisir_sujet_pedagogique", lambda jour=None: _topic("Le sommeil", "encyclopedie"))
    t = bg.ajouter_approfondissement(_topic("Zones protégées"))
    assert t["approfondissement"]["contenu_source"]["origine"] == "encyclopedie"


def test_ajouter_approfondissement_sans_sujet_ne_casse_pas(monkeypatch):
    from src.collecte import encyclopedie
    monkeypatch.setattr(encyclopedie, "choisir_sujet_pedagogique", lambda jour=None: None)
    t = bg.ajouter_approfondissement(_topic("Zones protégées"))
    assert "approfondissement" not in t


def test_ajouter_approfondissement_ignore_le_mode_approfondi(monkeypatch):
    from src.collecte import encyclopedie
    monkeypatch.setattr(encyclopedie, "choisir_sujet_pedagogique", lambda jour=None: (_ for _ in ()).throw(AssertionError("appelé")))
    t = bg.ajouter_approfondissement(_topic("Le sommeil", "encyclopedie"))
    assert "approfondissement" not in t


def test_fusion_decouverte_plus_dossier():
    sci = _merge(_bodies())
    assert sci["titre"] == "Zones protégées" and sci["mode"] == "decouverte"
    assert "## Pour aller plus loin : Le sommeil" in sci["contenu_markdown"]
    assert sci["nb_mots"] >= 900 and sci["nb_mots_approfondi"] >= 700
    assert sci["sujet_id"] == "sommeil"          # rotation sur le sujet pédagogique


def test_fusion_dossier_seul_si_decouverte_en_echec():
    sci = _merge(_bodies(d=False))
    assert sci["mode"] == "approfondi" and sci["titre"] == "Le sommeil"


def test_fusion_decouverte_seule_si_dossier_en_echec():
    sci = _merge(_bodies(a=False, b=False))
    assert sci["mode"] == "decouverte" and "Pour aller plus loin" not in sci["contenu_markdown"]
