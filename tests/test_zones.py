from src.analyse.zones import assigner_zones, zone_par_contenu


def it(titre, resume="", source="Le Monde", cat="france"):
    return {"titre": titre, "resume": resume, "source": source, "categorie": cat, "url": "u"}


def test_international_dans_flux_france_passe_en_monde():
    a = it("Budget militaire russe : Moscou augmente ses dépenses", "Le Kremlin annonce…")
    assert zone_par_contenu(a, "france") == "monde"
    b = it("La Corée du Nord teste un nouveau missile")
    assert zone_par_contenu(b, "france") == "monde"


def test_sujet_francais_dans_flux_monde_passe_en_france():
    a = it("Les députés votent le projet de loi de finances à l'Assemblée nationale", cat="monde")
    assert zone_par_contenu(a, "monde") == "france"


def test_cas_mixte_garde_la_zone_du_flux():
    a = it("Macron reçoit Trump", cat="monde")
    assert zone_par_contenu(a, "monde") == "monde"
    assert zone_par_contenu(a, "france") == "france"


def test_sans_marqueur_garde_la_zone_du_flux_et_nyt_reste_monde():
    assert zone_par_contenu(it("Une tempête touche le littoral"), "france") == "france"
    n = it("France votes on budget", source="The New York Times", cat="monde")
    assert zone_par_contenu(n, "monde") == "monde"


def test_pas_de_faux_positif_sur_sous_chaines():
    # « nice » dans un autre mot, « rome » dans « syndrome » : ne doivent pas compter
    assert zone_par_contenu(it("Un syndrome rare inquiète les médecins"), "france") == "france"
    assert zone_par_contenu(it("Une officine fermée"), "monde") == "monde"


def test_assigner_ne_mute_pas_et_met_a_jour_la_categorie():
    f = [it("La Russie frappe Kiev"), it("Grève à la SNCF avant les vacances")]
    m = [it("Le Pen et le RN : les députés réagissent", cat="monde")]
    f0 = [dict(x) for x in f]
    fr, mo, stats = assigner_zones(f, m)
    assert f == f0
    assert [x["titre"] for x in fr] == ["Grève à la SNCF avant les vacances", "Le Pen et le RN : les députés réagissent"]
    assert mo[0]["titre"] == "La Russie frappe Kiev" and mo[0]["categorie"] == "monde"
    assert stats == {"vers_monde": 1, "vers_france": 1}
