"""Tests hors réseau du garde-fou science (02/10/2026)."""
from src.generation.science_guard import (
    guard_science_article, normalize_headings, remove_llm_sources, remove_unsupported_numbers,
    source_numbers, strip_markers, unsupported_numbers,
)

SRC = {"titre": "Les enfants de 3 à 4 ans sont les plus actifs",
       "resume": "Une étude portant sur 18 542 pas par jour en moyenne, soit 40 % de plus.",
       "url": "https://exemple.org/article", "sources": ["Le Monde Sciences"]}


def test_nombres_de_la_source_conserves_et_inventes_retires():
    allowed = source_numbers(SRC["titre"], SRC["resume"])
    txt = "Ils font en moyenne 18 542 pas par jour. Une autre étude a suivi 2 000 enfants. Le cœur bat vite."
    out, removed = remove_unsupported_numbers(txt, allowed)
    assert "18 542" in out and "Le cœur bat vite." in out
    assert "2 000" not in out and len(removed) == 1


def test_pourcentage_et_decimal_inventes_retires_mais_chiffre_isole_tolere():
    allowed = set()
    assert unsupported_numbers("Soit 27 % de plus.", allowed) == ["27"]
    assert unsupported_numbers("Soit 3,5 fois plus.", allowed)
    assert not unsupported_numbers("Trois facteurs, dont 1 majeur.", allowed)


def test_ligne_de_liste_entierement_inventee_disparait():
    out, removed = remove_unsupported_numbers("- Fréquence : 100 à 120 battements.\n- Calme.", set())
    assert out == "- Calme." and removed


def test_marqueurs_internes_et_titres_normalises():
    t = "## **Introduction**\ntexte\n*(Fin de la moitié A – la suite abordera les données)*\n## 5. Données\nx"
    out = normalize_headings(strip_markers(t))
    assert "Fin de la moitié" not in out
    assert "## Introduction" in out and "## Données" in out and "**" not in out


def test_section_sources_du_llm_remplacee_par_celle_du_code():
    t = "## Conclusion\nok\n\n## 10. Sources\nSe référer aux références détaillées du Monde."
    assert "Se référer" not in remove_llm_sources(t)
    final, _ = guard_science_article(t, SRC)
    assert final.count("## Sources") == 1 and "https://exemple.org/article" in final


def test_sources_sans_url_ne_plante_pas():
    final, _ = guard_science_article("## A\ntexte", {"titre": "T", "resume": "", "url": "", "sources": []})
    assert "## Sources" in final


# --- 06/10/2026 : fuites internes, termes non sourcés, deux-points orphelins, sections vides ---------------------
from src.generation.science_guard import (  # noqa: E402
    ensure_sections_not_empty, fix_orphan_colons, remove_meta_leaks, remove_unsupported_terms, source_full_text,
    unsupported_terms,
)

SRC2 = {"titre": "Nobel de médecine : l'optogénétique", "resume": "Karl Deisseroth et des chercheurs contrôlent des neurones par la lumière.",
        "textes_sources": [{"source": "Nature", "titre": "Medicine Nobel", "resume": "Peter Hegemann and Georg Nagel, channelrhodopsin."}],
        "liens_sources": [{"nom": "Nature", "url": "https://n.org/a"}, {"nom": "Le Monde", "url": ""}]}


def test_fuite_du_resume_retiree():
    out, rem = remove_meta_leaks("Le résumé indique que tout va bien. La lumière active les neurones.")
    assert out == "La lumière active les neurones." and len(rem) == 1
    out, rem = remove_meta_leaks("Aucun chiffre n'est fourni dans le résumé disponible.")
    assert out == "" and rem


def test_affirmation_absolue_et_amorce_vide_retirees():
    out, rem = remove_meta_leaks("La lumière est non invasive pour les tissus. Par exemple. Les neurones réagissent.")
    assert out == "Les neurones réagissent." and len(rem) == 2


def test_identifiants_et_sigles_non_sources_retires_mais_sigles_courants_toleres():
    src = source_full_text(SRC2)
    assert unsupported_terms("La protéine ChR2 s'ouvre.", src)
    assert unsupported_terms("Le virus AAV cible les cellules.", src)
    assert not unsupported_terms("L'ADN et l'IRM sont courants.", src)
    assert not unsupported_terms("La channelrhodopsin est citée.", src)          # présent dans une source fusionnée
    assert unsupported_terms("Selon Jean Dupont, c'est vrai.", src)              # nom absent
    assert not unsupported_terms("Selon Karl Deisseroth, c'est vrai.", src)      # nom présent dans la source


def test_noms_de_plusieurs_sources_comptent_dans_les_nombres_autorises():
    t = "Le prix compte 2026 lauréats. Il y en a 999."
    out, rem = guard_science_article("## Données\n" + t, dict(SRC2, resume="Le prix de 2026 est décerné."))
    assert "999" not in out


def test_deux_points_orphelin_corrige_mais_liste_conservee():
    assert fix_orphan_colons("Ces protéines agissent comme des interrupteurs :\n\nLe tour de force ?") .startswith("Ces protéines agissent comme des interrupteurs.")
    assert fix_orphan_colons("Voici les étapes :\n- un\n- deux").splitlines()[0].endswith(":")
    assert fix_orphan_colons("Fin :").endswith("Fin.")


def test_section_donnees_vide_remplacee_autre_section_vide_supprimee():
    out = ensure_sections_not_empty("## Introduction\ntexte\n\n## Données et résultats\n\n## Limites\n\n## Conclusion\nok")
    assert "données chiffrées détaillées" in out and "## Limites" not in out and "## Conclusion" in out


def test_pipeline_complet_sur_texte_type_du_06_10():
    brut = ("## Introduction\nTexte.\n\n## Fonctionnement\nLe principe : \n- La protéine ChR2 s'ouvre.\n- Le virus AAV cible.\n"
            "## Données et résultats\nLe résumé indique que rien n'est chiffré.\n## Conclusion\nFin.")
    out, rem = guard_science_article(brut, SRC2)
    assert "ChR2" not in out and "AAV" not in out and "résumé" not in out
    assert "données chiffrées détaillées" in out
    assert "Le principe." in out or "Le principe" in out
    assert "## Sources\n- Nature — https://n.org/a\n- Le Monde" in out
    assert len(rem) == 3
