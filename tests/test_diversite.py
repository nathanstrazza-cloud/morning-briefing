"""Fusion par entités + sélection diversifiée (05/10/2026)."""
from src.analyse.diversite import entites, fusionner_par_entites, selectionner_diversifie
from src.analyse.zones import zone_par_contenu


def ev(titre, score=9, sources=("Libération",)):
    return {"titre": titre, "resume": "", "score": score, "categorie": "monde", "url_principale": "u",
            "sources": [{"nom": s, "url": "u"} for s in sources], "nb_sources": len(sources), "date_publication": None}


def test_entites_noms_propres_et_marqueurs():
    e = entites("Aux Etats-Unis, Christa Pike est toujours dans un état critique")
    assert {"christa", "pike"} <= e and "etats-unis" in e
    assert "bresil" in entites("Brésil : le vote est clôturé")          # 1er mot, via le lexique de zones


def test_fusion_christa_pike_deux_titres_deux_sources():
    a = ev("Aux Etats-Unis, Christa Pike est toujours dans un état critique après son exécution ratée", sources=("Libération", "20 Minutes"))
    b = ev("Christa Pike, condamnée à mort qui a survécu à deux injections létales, est dans un état critique, selon son avocat",
           sources=("France Info",))
    c = ev("Le Brésil vote : Lula face à Flavio Bolsonaro")
    out = fusionner_par_entites([a, b, c])
    assert len(out) == 2
    pike = out[0]
    assert pike["nb_sources"] == 3 and {s["nom"] for s in pike["sources"]} == {"Libération", "20 Minutes", "France Info"}
    assert len(a["sources"]) == 2                                          # entrée non modifiée


def test_entite_banale_ne_fusionne_pas():
    # « Donald Trump » dans 4 titres = trop fréquent pour prouver une identité d'événement
    titres = ["Donald Trump nomme un référent IA", "Donald Trump et les midterms", "Donald Trump dans le mur",
              "Donald Trump menace l'Iran"]
    assert len(fusionner_par_entites([ev(t) for t in titres])) == 4


def test_selection_limite_deux_par_sujet():
    bresil = [ev(f"Brésil : article {i} sur le vote de Lula", score=9) for i in range(4)]
    autres = [ev("Yémen : les houthistes encerclent Taëz", score=8), ev("Lettonie : percée des populistes", score=7),
              ev("Ukraine : un pont de Kiev attaqué", score=7)]
    sel = selectionner_diversifie(bresil + autres, 5)
    assert len(sel) == 5
    assert sum("Brésil" in e["titre"] for e in sel) == 2


def test_selection_complete_si_peu_de_sujets():
    sel = selectionner_diversifie([ev(f"Brésil : article {i}") for i in range(4)], 4)
    assert len(sel) == 4                                                   # complément : jamais de section sacrifiée


def test_zone_etats_unis_sans_accent_et_tennessee():
    it = {"titre": "Aux Etats-Unis, Christa Pike est toujours dans un état critique", "resume": "gouverneur du Tennessee",
          "source": "Libération", "categorie": "france", "url": "u"}
    assert zone_par_contenu(it, "france") == "monde"
