"""Génère un briefing de DÉMONSTRATION dans data/briefings/, pour visualiser le frontend
sans avoir à lancer une vraie collecte (réseau) ni configurer de clé LLM.

Usage : python -m scripts.generate_demo_data

Ce script n'est PAS utilisé par le workflow GitHub Actions (briefing.yml appelle
`python -m src.main`) — il sert uniquement de démonstration/test visuel local.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.stockage import storage  # noqa: E402

DEMO_BRIEFING = {
    "actualite": {
        "france": [
            {
                "titre": "Le gouvernement présente son plan pour les retraites",
                "resume": "Le premier ministre a détaillé ce matin les grandes lignes de la réforme, "
                "attendue depuis plusieurs mois.",
                "pourquoi_important": "Le texte concerne l'ensemble des actifs et doit être débattu "
                "au Parlement dans les prochaines semaines.",
                "consequences": "Des négociations avec les syndicats sont annoncées ; leur issue "
                "reste incertaine à ce stade.",
                "statut": "fait_confirme",
                "sources": ["Le Monde", "France Info"],
            }
        ],
        "monde": [
            {
                "titre": "Sommet européen sur l'énergie à Bruxelles",
                "resume": "Les chefs d'État ont évoqué la sécurité d'approvisionnement pour l'hiver.",
                "pourquoi_important": "Les décisions prises influencent directement les prix de "
                "l'énergie en France.",
                "consequences": None,
                "statut": "information_rapportee",
                "sources": ["Le Monde International"],
            }
        ],
    },
    "marches": {
        "resume_court": "Séance calme en Europe ; le Nasdaq recule après des résultats "
        "technologiques jugés décevants.",
        "mouvements_notables": [
            {"nom": "Nasdaq", "variation_pct": -1.8, "explication": "Résultats trimestriels en dessous des attentes pour plusieurs grandes valeurs technologiques."},
            {"nom": "CAC 40", "variation_pct": 0.3, "explication": None},
        ],
    },
    "sport": {
        "football": ["Ligue 1 : victoire courte de l'OM face à Lille (1-0)."],
        "basketball": ["NBA (présaison) : les Spurs s'imposent, Wembanyama auteur de 24 points."],
        "natation": None,
        "autres": None,
    },
    "science": {
        "mode": "approfondi",
        "titre": "Comprendre le sommeil : à quoi sert-il vraiment ?",
        "contenu_markdown": (
            "## Introduction\n\nLe sommeil occupe environ un tiers de notre vie, mais reste "
            "l'un des phénomènes biologiques les moins bien compris du grand public.\n\n"
            "## Pourquoi c'est important\n\nUn sommeil de mauvaise qualité est associé à des "
            "risques accrus de troubles cardiovasculaires et métaboliques.\n\n"
            "## Ce que la science sait\n\nLe sommeil alterne des phases lentes profondes et des "
            "phases paradoxales, chacune associée à des fonctions distinctes de consolidation "
            "de la mémoire et de régulation émotionnelle.\n\n"
            "## Ce qui reste incertain\n\nLe rôle exact du sommeil paradoxal dans l'apprentissage "
            "fait encore débat parmi les chercheurs."
        ),
    },
    "citation": {
        "texte": "Ce n'est pas parce que les choses sont difficiles que nous n'osons pas, "
        "c'est parce que nous n'osons pas qu'elles sont difficiles.",
        "auteur": "Sénèque",
    },
    "meteo": {
        "villes_detail": [
            {"ville": "Antibes", "temperature_actuelle": 22.5},
            {"ville": "Cannes", "temperature_actuelle": 22.9},
            {"ville": "Valbonne", "temperature_actuelle": 21.1},
            {"ville": "Grasse", "temperature_actuelle": 20.8},
        ],
        "temperature_max_zone": 26,
        "temperature_min_zone": 18,
        "probabilite_pluie_max_pct": 5,
        "vent_max_kmh": 12,
        "description_dominante": "ciel dégagé",
    },
    "meta": {"resume_1_phrase": "Briefing de démonstration — données fictives."},
    "_genere_par_llm": False,
    "_provider": None,
}


def main() -> None:
    storage.save_briefing(DEMO_BRIEFING, "2026-09-06", "2026-09-06T06:31:00+02:00")
    print("Données de démonstration écrites dans docs/data/briefings/. Ouvrez docs/index.html.")


if __name__ == "__main__":
    main()
