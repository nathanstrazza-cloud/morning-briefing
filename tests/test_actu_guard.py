"""Tests hors réseau : garde-fou actualité + dédup inter-zones (03/10/2026)."""
from src.analyse.dedup import merge_zones
from src.generation.actu_guard import guard_events

SRC = [{"titre": "Powell : Trump menace le président de la Fed", "resume": "Le président américain a critiqué Jerome Powell jeudi.",
        "statut_verification": "fait_confirme"}]


def _ev(**kw):
    base = {"titre": "Powell : Trump menace le président de la Fed", "resume": "r", "pourquoi_important": None,
            "consequences": None, "statut": "information_rapportee", "sources": ["Le Monde"]}
    base.update(kw)
    return base


def test_ancien_absent_de_la_source_est_retire():
    out, rem = guard_events([_ev(resume="L'ancien président américain a critiqué Powell. Il l'a fait jeudi.")], SRC)
    assert "ancien" not in out[0]["resume"] and "jeudi" in out[0]["resume"] and rem


def test_terme_present_dans_la_source_est_conserve():
    src = [dict(SRC[0], resume="L'ancien président de la Fed a parlé.")]
    out, rem = guard_events([_ev(resume="L'ancien président de la Fed a parlé.")], src)
    assert not rem and out[0]["resume"]


def test_nombre_invente_retire_et_resume_source_en_repli():
    out, _ = guard_events([_ev(resume="Une hausse de 25 % est attendue en 2024.")], SRC)
    assert out[0]["resume"] == SRC[0]["resume"]


def test_consequences_prefixees_hypothese_et_statut_impose_par_le_code():
    out, _ = guard_events([_ev(consequences="Les marchés pourraient réagir.")], SRC)
    assert out[0]["consequences"].startswith("Hypothèse : ")
    assert out[0]["statut"] == "fait_confirme"


def _e(titre, noms, date=None):
    return {"titre": titre, "resume": "", "url_principale": "u", "categorie": "x",
            "sources": [{"nom": n, "url": "u"} for n in noms], "nb_sources": len(noms), "date_publication": date}


def test_merge_zones_deplace_vers_monde_et_cumule_les_sources():
    fr = [_e("Exécution ratée de Christa Pike Tennessee", ["20 Minutes"]), _e("Réforme des retraites Assemblée vote", ["Le Monde"])]
    mo = [_e("Christa Pike : l'exécution ratée dans le Tennessee", ["Le Monde"])]
    f, m = merge_zones(fr, mo)
    assert [e["titre"] for e in f] == ["Réforme des retraites Assemblée vote"]
    assert m[0]["nb_sources"] == 2 and {s["nom"] for s in m[0]["sources"]} == {"Le Monde", "20 Minutes"}
    assert len(fr) == 2 and mo[0]["nb_sources"] == 1      # entrées non modifiées


def test_merge_zones_sans_doublon_ne_change_rien():
    fr, mo = [_e("Budget 2027 présenté", ["Le Monde"])], [_e("Séisme au Japon", ["NYT"])]
    f, m = merge_zones(fr, mo)
    assert len(f) == 1 and len(m) == 1
