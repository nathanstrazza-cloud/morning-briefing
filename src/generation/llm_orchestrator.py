"""Moteur d'orchestration des appels LLM (répartition par parties + secours en chaîne).

Ce module est GÉNÉRIQUE : il ne connaît ni les prompts, ni le contenu du briefing. Il sait
seulement, pour un ensemble de "parties" (Part) et un plan (config/llm_plan.yaml) :
  1. envoyer chaque partie à son fournisseur principal, EN PARALLÈLE entre fournisseurs
     différents (un même fournisseur traite ses parties l'une après l'autre) ;
  2. si une partie échoue, la repasser au fournisseur suivant de sa chaîne (secours), tour
     après tour, jusqu'à réussite ou épuisement de la chaîne ;
  3. n'ouvrir une étape (stage) qu'une fois la précédente terminée, et n'ouvrir l'appel
     (wave) suivant qu'après une pause (fenêtre de tokens/minute de Groq).

Ce qui compte pour la fiabilité (cahier §21) : une partie qui échoue partout renvoie un
PartResult avec body=None et le détail des erreurs -- l'appelant (briefing_generator)
retombe alors sur le contenu brut pour CETTE partie seulement, jamais sur tout le briefing.

Voir aussi : config/llm_plan.yaml (le plan), HANDOFF_LLM.md (contexte), tests/.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

logger = logging.getLogger("morning_briefing.generation")

DEFAULT_PLAN_PATH = Path(__file__).resolve().parents[2] / "config" / "llm_plan.yaml"


@dataclass
class Part:
    """Une partie du briefing à faire rédiger par UN appel LLM."""
    name: str
    system_prompt: str
    build_prompt: Callable[[int], str]      # budget de caractères -> prompt utilisateur
    max_tokens: int
    required_keys: tuple[str, ...] = ()     # clés JSON obligatoires (sinon : échec -> secours)
    prompt_char_budgets: tuple[int, ...] = (12_000,)   # tentatives à budget décroissant (même fournisseur)
    parser: Callable[[str], dict] | None = None        # None = JSON ; sinon parse une réponse TEXTE (ex. article markdown)


@dataclass
class PartResult:
    name: str
    body: dict | None = None
    provider: str | None = None             # fournisseur qui a réussi
    attempts: list[str] = field(default_factory=list)   # "groq: 429 ..." pour chaque échec, dans l'ordre

    @property
    def ok(self) -> bool:
        return self.body is not None

    @property
    def error(self) -> str | None:
        return " | ".join(self.attempts)[:400] if (self.attempts and not self.ok) else None


def parse_json_text(raw: str) -> dict:
    """json.loads tolérant : retire ```json ... ``` et un éventuel texte autour de l'objet
    (ministral/nemo entourent parfois leur JSON de balises ou d'une phrase d'introduction)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.lower().startswith("json"):
            text = text[4:]
    def _load(t: str):
        # strict=False : accepte les retours à la ligne/tabulations BRUTS dans les chaînes (constaté
        # le 30/09 avec ministral : « Invalid control character » sur le texte de l'article).
        try:
            return json.loads(t, strict=False)
        except json.JSONDecodeError:
            # Réparations sûres : nombres précédés de « + » (+1.2), NaN/Infinity -> null.
            fixed = re.sub(r'(?<=[:\[,])(\s*)\+(?=\d)', r'\1', t)
            fixed = re.sub(r'(?<=[:\[,])(\s*)(?:NaN|-?Infinity)\b', r'\1null', fixed)
            return json.loads(fixed, strict=False)
    try:
        return _load(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return _load(text[start:end + 1])
        raise


LEAK_PREFIXES = ("here's a thinking process", "here is a thinking process", "thinking process",
                 "the user wants", "user safety", "okay, let's", "let me think")


def looks_like_leak(text: str) -> bool:
    """Réponse qui commence par du raisonnement / une sortie de modèle de modération : inutilisable."""
    return text.lstrip().lower().startswith(LEAK_PREFIXES)


def _attempt(provider, part: Part) -> tuple[dict | None, str | None]:
    """Un fournisseur, une partie. Retourne (body, None) ou (None, message_d_erreur)."""
    last_error = None
    for i, max_chars in enumerate(part.prompt_char_budgets, start=1):
        raw = ""
        try:
            raw = provider.complete(part.system_prompt, part.build_prompt(max_chars), max_tokens=part.max_tokens)
            body = part.parser(raw) if part.parser else parse_json_text(raw)
            if not isinstance(body, dict):
                raise ValueError("la réponse JSON n'est pas un objet")
            missing = [k for k in part.required_keys if k not in body]
            if missing:
                raise ValueError(f"clés manquantes dans la réponse: {missing}")
            return body, None
        except Exception as exc:  # noqa: BLE001 -- on veut TOUT rattraper : un échec = secours
            last_error = f"{provider.name}: {str(exc)[:160]}"
            detail = getattr(exc, "body_excerpt", None)
            logger.error("Échec LLM part=%s provider=%s tentative=%d/%d budget=%d : %s%s",
                         part.name, provider.name, i, len(part.prompt_char_budgets), max_chars, exc,
                         f" | corps: {detail}" if detail else "")
            if raw and isinstance(exc, (ValueError,)):   # JSON invalide : garde un extrait pour comprendre
                logger.error("  réponse brute (début) : %r", raw[:300])
            # Un 429 = quota de la fenêtre épuisé : réessayer tout de suite avec un prompt plus
            # petit ne peut pas réussir. On passe directement au fournisseur suivant.
            if getattr(exc, "status_code", None) == 429:
                break
            # Un prompt plus petit n'aide QUE si le prompt était trop gros (400/413/422). Pour un JSON
            # invalide, un raisonnement écrit dans la réponse, un timeout ou un 5xx, réessayer sur le
            # même fournisseur ne fait que perdre 1 à 2 minutes (constaté le 30/09 : run de 14 min) :
            # on passe directement au fournisseur suivant.
            if getattr(exc, "status_code", None) not in (400, 413, 422):
                break
    return None, last_error


def run_stage(parts: dict[str, Part], chains: dict[str, list[str]], pool: dict) -> dict[str, PartResult]:
    """Exécute une étape. `chains[nom_partie]` = ordre des fournisseurs ; `pool` = {nom: provider}
    (les fournisseurs sans clé API en sont absents et sont simplement sautés).
    L'ordre d'insertion de `parts` fixe la priorité dans la file d'un même fournisseur."""
    results = {name: PartResult(name) for name in parts}
    order = list(parts)
    max_rounds = max((len(chains[n]) for n in order), default=0)

    for round_idx in range(max_rounds):
        # Parties encore à traiter + fournisseur de ce tour (on saute ceux sans clé)
        queues: dict[str, list[str]] = {}
        for name in order:
            res = results[name]
            if res.ok:
                continue
            chain = chains[name]
            if round_idx >= len(chain):
                continue
            prov_name = chain[round_idx]
            if prov_name not in pool:
                res.attempts.append(f"{prov_name}: pas de clé API")
                continue
            queues.setdefault(prov_name, []).append(name)
        if not queues:
            continue
        logger.info("Tour %d : %s", round_idx + 1,
                    "; ".join(f"{p} -> {', '.join(ns)}" for p, ns in queues.items()))

        def _worker(prov_name: str, names: list[str]) -> None:
            for name in names:   # fournisseur unique : parties servies l'une après l'autre
                body, err = _attempt(pool[prov_name], parts[name])
                if body is not None:
                    results[name].body, results[name].provider = body, prov_name
                else:
                    results[name].attempts.append(err or f"{prov_name}: échec inconnu")

        with ThreadPoolExecutor(max_workers=len(queues)) as ex:
            futures = [ex.submit(_worker, p, ns) for p, ns in queues.items()]
            for f in futures:
                f.result()   # _worker ne lève jamais ; propage quand même un bug de programmation
        if all(results[n].ok for n in order):
            break
    return results


def load_plan(path: str | os.PathLike | None = None) -> dict:
    with open(path or DEFAULT_PLAN_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def wave_gap_seconds(plan: dict) -> int:
    env = os.environ.get("LLM_WAVE_GAP_SECONDS")
    try:
        return max(0, int(env)) if env not in (None, "") else max(0, int(plan.get("wave_gap_seconds", 150)))
    except ValueError:
        return 150


def run_plan(plan: dict, parts: dict[str, Part], pool: dict, sleep=time.sleep) -> dict[str, PartResult]:
    """Exécute tout le plan. `parts` = uniquement les parties du jour (une partie du plan absente
    de `parts`, ex. science_b en mode découverte, est simplement ignorée)."""
    all_results: dict[str, PartResult] = {}
    gap = wave_gap_seconds(plan)
    for w_idx, wave in enumerate(plan["waves"]):
        wave_parts = [n for st in wave["stages"] for n in st["parts"] if n in parts]
        if not wave_parts:
            continue
        if w_idx > 0 and gap:
            logger.info("Pause de %d s avant l'%s (fenêtre tokens/minute des fournisseurs)", gap, wave["name"])
            sleep(gap)
        logger.info("=== %s : %s ===", wave["name"], ", ".join(wave_parts))
        for stage in wave["stages"]:
            stage_parts = {n: parts[n] for n in stage["parts"] if n in parts}
            if not stage_parts:
                continue
            chains = {n: list(stage["parts"][n]) for n in stage_parts}
            all_results.update(run_stage(stage_parts, chains, pool))
    return all_results
