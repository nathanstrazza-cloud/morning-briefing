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


from src.generation.actu_guard import guard_marches, RESUME_MARCHES_SANS_CAUSE


def _analysed():
    return {"marches_data": {"indices": [{"name": "Nasdaq", "variation_pct": 1.19}, {"name": "CAC 40", "variation_pct": -1.4}],
                             "matieres_premieres": []},
            "actualite_economie": [{"titre": "Wall Street gagne du terrain après des résultats d'entreprises solides",
                                    "resume": "Les résultats trimestriels des géants de la tech soutiennent le Nasdaq."}]}


def test_marches_explication_hors_sujet_supprimee_variation_imposee_par_le_code():
    m = {"resume_court": "Hausse grâce aux dépenses de défense russe.",
         "mouvements_notables": [{"nom": "Nasdaq", "variation_pct": 9.9, "explication": "augmentation des dépenses de défense russe"},
                                 {"nom": "Inconnu", "variation_pct": 3.0, "explication": None}]}
    out = guard_marches(m, _analysed())
    assert out["mouvements_notables"] == [{"nom": "Nasdaq", "variation_pct": 1.19, "explication": None}]
    assert out["resume_court"] == RESUME_MARCHES_SANS_CAUSE


def test_marches_explication_etayee_conservee():
    m = {"resume_court": "Résultats solides de la tech.",
         "mouvements_notables": [{"nom": "nasdaq", "variation_pct": 1.19,
                                  "explication": "résultats trimestriels solides des géants de la tech"}]}
    out = guard_marches(m, _analysed())
    assert out["mouvements_notables"][0]["explication"] and out["resume_court"] == "Résultats solides de la tech."


def test_pourquoi_important_non_etaye_est_supprime_pas_prefixe():
    # 05/10/2026 : plus de « Hypothèse : » creux sur tous les items ; non étayé -> null
    src = [dict(SRC[0])]
    out, rem = guard_events([_ev(pourquoi_important="Cela pourrait influencer la coopération judiciaire française.")], src)
    assert out[0]["pourquoi_important"] is None and any("pourquoi_important" in r for r in rem)


def test_pourquoi_important_etaye_conserve_sans_prefixe():
    src = [dict(SRC[0])]
    out, _ = guard_events([_ev(pourquoi_important="Trump critique le président de la Fed, Jerome Powell.")], src)
    assert out[0]["pourquoi_important"] == "Trump critique le président de la Fed, Jerome Powell."


def test_pourquoi_important_formule_creuse_supprimee():
    src = [dict(SRC[0])]
    out, _ = guard_events([_ev(pourquoi_important="Cette affaire met en lumière la Fed, Trump et le président Powell.")], src)
    assert out[0]["pourquoi_important"] is None


def test_nom_propre_invente_retire_la_phrase():
    # Cas réel du 05/10 : « Olaf Scholz » écrit alors que la source parle de Merz
    src = [{"titre": "Ukraine : visite de Merz à Kiev", "resume": "Le chancelier allemand Friedrich Merz est arrivé à Kiev.",
            "statut_verification": "fait_confirme"}]
    ev = _ev(titre="Ukraine : visite de Merz à Kiev",
             resume="Le chancelier allemand Olaf Scholz est arrivé à Kiev. La visite a eu lieu lundi.")
    out, rem = guard_events([ev], src)
    assert "Scholz" not in out[0]["resume"] and "lundi" in out[0]["resume"]
    assert any("Scholz" in r for r in rem)


def test_nom_propre_present_dans_la_source_conserve_meme_sans_accent():
    src = [{"titre": "Brésil : Lula devant", "resume": "Flavio Bolsonaro frôle la victoire à São Paulo.",
            "statut_verification": "fait_confirme"}]
    ev = _ev(titre="Brésil : Lula devant", resume="Le vote a vu Flavio Bolsonaro frôler la victoire à Sao Paulo.")
    out, rem = guard_events([ev], src)
    assert not rem and out[0]["resume"].startswith("Le vote")


def test_nom_propre_au_debut_de_phrase_non_controle():
    out, rem = guard_events([_ev(resume="Mardi, la Fed a parlé. Powell a répondu.")], SRC)
    assert not rem


def test_marches_article_sans_lien_avec_la_bourse_ne_peut_pas_expliquer():
    # Cas réel du 05/10 : DAX/Euro Stoxx « expliqués » par le budget 2027 (article France sans mention de marché)
    an = {"marches_data": {"indices": [{"name": "DAX", "variation_pct": 1.17}, {"name": "Euro Stoxx 50", "variation_pct": 1.02}],
                           "matieres_premieres": []},
          "actualite_economie": [{"titre": "Le budget 2027 prévoit des garanties pour les réacteurs nucléaires",
                                  "resume": "Le projet de loi de finances prévoit des garanties de l'État pour les réacteurs nucléaires."}]}
    m = {"resume_court": "Hausse portée par le budget.",
         "mouvements_notables": [{"nom": "DAX", "explication": "Le budget 2027 prévoit des garanties pour les réacteurs nucléaires"},
                                 {"nom": "Euro Stoxx 50", "explication": "Le budget 2027 prévoit des garanties pour les réacteurs nucléaires"}]}
    out = guard_marches(m, an)
    assert all(x["explication"] is None for x in out["mouvements_notables"])
    assert out["resume_court"] == RESUME_MARCHES_SANS_CAUSE


def test_marches_explication_conservee_si_un_article_parle_de_ce_marche():
    an = {"marches_data": {"indices": [{"name": "DAX", "variation_pct": 1.17}], "matieres_premieres": []},
          "actualite_economie": [{"titre": "Le DAX bondit après l'accord commercial entre Berlin et Washington",
                                  "resume": "Les investisseurs saluent l'accord commercial conclu entre Berlin et Washington."}]}
    m = {"resume_court": "", "mouvements_notables": [{"nom": "DAX", "explication": "accord commercial entre Berlin et Washington salué par les investisseurs"}]}
    out = guard_marches(m, an)
    assert out["mouvements_notables"][0]["explication"]
