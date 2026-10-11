"""Format de la section sport (05/10/2026) : `{"items": [{"sport": str, "texte": str}]}`.

Remplace l'ancien format figé {football, basketball, natation, autres}. Fonctions pures, sans réseau.
`depuis_evenements` = repli sans LLM ; `normaliser` accepte la sortie du LLM (nouveau format, ou ancien
format par catégories) et la borne : jamais plus d'items que d'événements retenus par le code.
"""
from __future__ import annotations


_MOTS_EN = {"the", "of", "to", "and", "in", "for", "with", "after", "his", "her", "helps", "beat", "wins", "win", "as",
            "on", "at", "by", "from", "into", "fight", "back", "against", "over", "but", "is", "are", "was", "has"}
_MOTS_FR = {"le", "la", "les", "de", "du", "des", "et", "à", "au", "aux", "un", "une", "pour", "avec", "dans", "sur", "par",
            "en", "face", "contre", "après", "qui", "que", "est", "a", "se", "s'impose", "son", "sa", "ses"}


def semble_anglais(texte: str) -> bool:
    """Phrase restée en anglais (titre BBC non traduit, 11/10) : >= 2 mots outils anglais et aucun mot outil français."""
    mots = [m.strip(".,:;!?\"'«»()").lower() for m in str(texte).split()]
    return sum(m in _MOTS_EN for m in mots) >= 2 and not any(m in _MOTS_FR for m in mots)


def depuis_evenements(sport_events: dict[str, list[dict]]) -> dict:
    items = [{"sport": sp, "texte": e["titre"]} for sp, evs in sport_events.items() for e in evs]
    return {"items": items}


def normaliser(corps, sport_events: dict[str, list[dict]]) -> dict:
    """Retourne toujours {"items": [...]}. Entrée inexploitable -> repli sur les titres retenus."""
    maxi = sum(len(v) for v in sport_events.values())
    items: list[dict] = []
    if isinstance(corps, dict):
        brut = corps.get("items")
        if isinstance(brut, list):
            for it in brut:
                if isinstance(it, dict) and str(it.get("texte") or "").strip():
                    items.append({"sport": str(it.get("sport") or "autres").strip().lower(),
                                  "texte": str(it["texte"]).strip()})
        else:                                   # ancien format {football: [str], ...}
            for sp, lignes in corps.items():
                if isinstance(lignes, list):
                    items += [{"sport": str(sp).lower(), "texte": str(t).strip()} for t in lignes if str(t).strip()]
    francais = [it for it in items if not semble_anglais(it["texte"])]
    if francais:                       # jamais d'élément non traduit si au moins un est en français
        items = francais
    if not items:
        return depuis_evenements(sport_events)
    return {"items": items[:maxi] if maxi else items}
