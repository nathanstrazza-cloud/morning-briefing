"""Titres propres, sport arrivé par l'actualité, anglais non traduit, zones Moyen-Orient (11/10/2026)."""
from src.analyse import sport_news, titres, zones
from src.generation import sport_format


def test_titre_en_direct_et_ellipse():
    assert titres.nettoyer_titre("EN DIRECT Guerre au Moyen-Orient : l’Arabie saoudite accuse les Houthis…") == \
        "Guerre au Moyen-Orient : l’Arabie saoudite accuse les Houthis"
    assert titres.nettoyer_titre("EN DIRECT, guerre en Ukraine : Trump affirme que Poutine veut un règlement") == \
        "Guerre en Ukraine : Trump affirme que Poutine veut un règlement"
    assert titres.nettoyer_titre("🔴 Cyclisme : à 20 ans, Paul Seixas devient le plus jeune vainqueur").startswith("Cyclisme")


def test_titre_court_ou_normal_inchange():
    assert titres.nettoyer_titre("Direct") == "Direct"
    assert titres.nettoyer_titre("Le gouvernement adopte le budget") == "Le gouvernement adopte le budget"


def test_resume_de_direct_vide():
    assert titres.nettoyer_resume("Suivez avec nous les informations sur les conflits ce dimanche") == ""
    assert titres.nettoyer_resume("Une frappe a tué six personnes.") == "Une frappe a tué six personnes."


def test_nettoyer_items_ne_modifie_pas_l_entree():
    src = [{"titre": "EN DIRECT Guerre en Ukraine : nouvelle frappe sur Kharkiv", "resume": "Suivez le direct"}]
    out = titres.nettoyer_items(src)
    assert src[0]["titre"].startswith("EN DIRECT") and out[0]["titre"].startswith("Guerre") and out[0]["resume"] == ""


def test_sport_deplace_depuis_l_actualite():
    items = [{"titre": "Lens renoue avec la victoire contre Lyon pour le retour de la Ligue 1", "resume": ""},
             {"titre": "Le Français Paul Seixas remporte le Tour de Lombardie", "resume": ""},
             {"titre": "Un combat contre le cancer : les chercheurs avancent", "resume": "Cyclisme et santé"},
             {"titre": "Le budget 2027 divise la majorité", "resume": "Ligue 1 évoquée en passant"}]
    reste, sport = sport_news.separer_sport(items)
    assert [i["titre"][:4] for i in sport] == ["Lens", "Le F"] and len(reste) == 2
    assert sport[0]["sport"] == "football" and sport[1]["sport"] == "cyclisme" and sport[0]["categorie"] == "sport"


def test_anglais_non_traduit_detecte():
    assert sport_format.semble_anglais("Brilliant Guimaraes goal helps Arsenal fight back to beat Leeds")
    assert not sport_format.semble_anglais("Arsenal bat Leeds grâce à un but de Guimaraes")
    assert not sport_format.semble_anglais("Tottenham arrache le nul à Manchester United")


def test_normaliser_ecarte_l_anglais_mais_garde_si_tout_est_anglais():
    ev = {"football": [{"titre": "a"}, {"titre": "b"}]}
    mixte = {"items": [{"sport": "football", "texte": "Arsenal fight back to beat Leeds in the league"},
                       {"sport": "tennis", "texte": "Vacherot passe au 3e tour à Shanghai"}]}
    assert [i["sport"] for i in sport_format.normaliser(mixte, ev)["items"]] == ["tennis"]
    tout_en = {"items": [{"sport": "football", "texte": "Arsenal fight back to beat Leeds in the league"}]}
    assert len(sport_format.normaliser(tout_en, ev)["items"]) == 1


def test_riyad_houthis_classe_monde():
    it = {"titre": "Guerre au Moyen-Orient : nouvelle attaque contre l'aéroport de Ryad, missile intercepté",
          "resume": "Les Houthis revendiquent une frappe contre l'Arabie saoudite.", "source": "Libération"}
    assert zones.zone_par_contenu(it, "france") == "monde"
    it2 = {"titre": "Frappes sur l'aéroport de Riyad attribuées aux houthistes", "resume": "", "source": "France Info"}
    assert zones.zone_par_contenu(it2, "france") == "monde"


def test_direct_de_match_sans_competition_va_au_sport():
    it = {"titre": "Rpool - Manchester City : Anfield chambre des Cityzens et on s'ennuie… Suivez ce choc électrique avec nous", "resume": ""}
    assert sport_news.est_sport(it)
    assert not sport_news.est_sport({"titre": "Attal - Philippe : le match des centristes est lancé", "resume": ""})


def test_titre_interrogatif_penalise_au_sport():
    from src.analyse.sport_scoring import score_sport_event
    q = {"titre": "Mondiaux de judo : comment le Français a-t-il pu perdre son combat décisif ?", "resume": "", "nb_sources": 1}
    r = {"titre": "Mondiaux de judo : le Français perd son combat décisif", "resume": "", "nb_sources": 1}
    assert score_sport_event(q) == score_sport_event(r) - 2
