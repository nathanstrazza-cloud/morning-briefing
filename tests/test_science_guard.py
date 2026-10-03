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
