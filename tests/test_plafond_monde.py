"""Plafond Monde levé (10/10/2026) : clé dédiée, prompt non rogné à 8 événements, avertissement si le LLM en retire."""
import logging

import yaml

from src.generation import parts


def _events(n):
    return [{"titre": f"Événement {i} " + "x" * 80, "resume": "r" * 600, "nb_sources": 2, "score": 9 - i % 3,
             "sources": [{"nom": "Le Monde", "url": "https://x/%d" % i}, {"nom": "NYT", "url": "https://y/%d" % i}],
             "statut": "fait_confirme"} for i in range(n)]


def test_config_plafond_monde_superieur_a_france():
    s = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))["seuils"]
    assert s["max_actualites_monde"] > s["max_actualites_france"] >= 1


def test_prompt_monde_garde_8_evenements():
    p = parts._zone_prompt("actualite_monde", _events(8), False, parts.PROMPT_CHARS, "intro")
    assert p.count("Événement ") == 8


def test_consigne_un_element_par_evenement_dans_les_deux_prompts():
    assert "UN élément par événement" in parts.SYSTEM_ACTU_MONDE
    assert "UN élément par événement" in parts.SYSTEM_ACTU_FRANCE


def test_avertissement_si_le_llm_retire_des_evenements(caplog):
    analysed = {"actualite_monde": _events(5)}
    rendus = [{"titre": "A", "resume": "r", "pourquoi_important": None, "consequences": None,
               "statut": "fait_confirme", "sources": ["Le Monde"]}] * 3
    with caplog.at_level(logging.WARNING, logger="morning_briefing.generation"):
        parts._garde_actu(rendus, analysed, "actualite_monde")
    assert any("3 événement(s) sur 5" in r.message for r in caplog.records)
