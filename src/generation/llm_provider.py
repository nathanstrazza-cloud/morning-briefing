"""Abstraction multi-fournisseurs LLM (cf. README §4 pour le choix et les clés).

Objectif : pouvoir changer de fournisseur (Groq, Mistral, Cerebras, Gemini, Anthropic, ...)
en changeant uniquement la variable d'environnement LLM_PROVIDER, sans toucher au reste du
pipeline. Chaque provider expose la même méthode `complete(system, user) -> str`.

Aucun provider n'est appelé si aucune clé n'est configurée : `get_provider()` retourne
None dans ce cas, et l'appelant (briefing_generator.py) doit basculer en mode fallback
(cf. cahier §21 : ne jamais planter le pipeline, ne jamais inventer).
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger("morning_briefing.generation.llm")

# NB (ajouté le 2026-09-26) : jusqu'ici aucun provider ne fixait `max_tokens` sur la requête
# de complétion -- cf. logs du 26/09 : la 1ère tentative Groq (budget prompt=12000 caractères,
# ~3000 tokens en entrée) a bien reçu une réponse HTTP 200, mais tronquée en plein milieu
# ("Unterminated string starting at: line 79 column 18") : le modèle a manifestement dépassé
# un budget de sortie implicite avant d'avoir fini le JSON (probable, vu le tier gratuit
# "on_demand" : Groq semble réserver une sortie par défaut assez généreuse mais pas illimitée,
# et rien ne borne explicitement combien le modèle peut écrire). Cette tentative ratée a à elle
# seule consommé 6587 des 8000 tokens/minute autorisés (cf. message d'erreur de la 2e
# tentative : "Limit 8000, Used 6587, Requested 3722"), condamnant d'avance la 2e tentative
# (prompt réduit à 4000 caractères) qui a immédiatement reçu un 429.
# Fixer explicitement `max_tokens` a un double bénéfice : (1) empêcher une réponse tronquée
# impossible à parser en JSON (le modèle est contraint de rester dans un budget qui, combiné
# à MAX_PROMPT_CHARS/RETRY_PROMPT_CHARS, doit lui permettre de terminer son JSON), et (2)
# réduire le nombre de tokens "Requested" compté par le rate-limiter TPM de Groq (qui semble
# inclure le budget de sortie demandé, pas seulement l'entrée), laissant plus de marge sous
# la limite de 8000/minute observée pour ce modèle/tier.
# Valeur choisie : 3500 -- avec MAX_PROMPT_CHARS=12000 (~3000 tokens d'entrée + ~600 tokens de
# SYSTEM_PROMPT), le total (entrée + sortie demandée) reste sous 8000, avec de la marge pour
# les tokens déjà consommés par un run précédent dans la même fenêtre d'une minute. À ajuster
# si un futur run montre encore une troncature ("Unterminated string"/"Expecting value") malgré
# ce plafond -- cela indiquerait qu'un sujet science "approfondi" a besoin de plus de place et
# qu'il faudrait alors réduire MAX_PROMPT_CHARS en contrepartie plutôt que remonter ce chiffre.
MAX_OUTPUT_TOKENS = 3500


class LLMError(RuntimeError):
    """Erreur de génération LLM enrichie du corps de la réponse HTTP quand disponible.

    NB (corrigé le 2026-09-19) : jusqu'ici chaque provider laissait `resp.raise_for_status()`
    lever une `requests.HTTPError` "nue", dont le message ne contient que le code + la phrase
    de statut HTTP (ex: "413 Client Error: Payload Too Large for url: ..."), jamais le corps
    de la réponse. Or c'est justement ce corps qui indique la VRAIE cause chez Groq/Gemini/
    Anthropic (ex: "Request too large for model X on tokens per minute (TPM): Limit 6000,
    Requested 11342"). Sans lui, impossible de savoir si le problème est le nombre d'octets,
    le nombre de tokens, ou une limite de débit par minute — cf. logs des 2026-09-10, 09-11,
    09-13 et 09-17 : quatre tentatives de correction "à l'aveugle" du même symptôme 413.
    Cette classe capture le corps (tronqué) pour que le prochain diagnostic n'ait plus à
    deviner."""

    def __init__(self, message: str, body_excerpt: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.body_excerpt = body_excerpt
        # NB (corrigé le 2026-09-26) : ajouté pour que l'appelant (briefing_generator.generate)
        # puisse distinguer un 429 "rate limit" (cf. logs du 26/09 : Groq/Mistral tokens per
        # minute) -- où retenter IMMÉDIATEMENT le MÊME provider avec un prompt plus petit ne
        # sert à rien, le quota de la fenêtre en cours est déjà consommé -- d'une autre erreur
        # (ex: JSON tronqué, 413) où réduire le budget de caractères a justement pour but
        # d'aider. Avant ce champ, seul le message texte contenait le code, ce qui forçait un
        # parsing fragile ("429" in str(exc)) pour la même décision.
        self.status_code = status_code


class LLMProvider:
    name = "base"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def _post(self, url: str, **kwargs) -> dict:
        """Wrapper commun : POST + lève LLMError avec le corps de la réponse en cas d'échec,
        au lieu de laisser passer une HTTPError nue (cf. LLMError ci-dessus)."""
        resp = requests.post(url, **kwargs)
        if not resp.ok:
            excerpt = (resp.text or "")[:500]
            raise LLMError(
                f"{resp.status_code} {resp.reason} (provider={self.name}): {excerpt}",
                body_excerpt=excerpt,
                status_code=resp.status_code,
            )
        return resp.json()


class GroqProvider(LLMProvider):
    """Groq : quota gratuit généreux, très rapide. https://console.groq.com

    NB (corrigé le 2026-09-09) : `llama-3.3-70b-versatile` a été décommissionné par Groq
    le 16 août 2026 (annonce du 17 juin 2026, cf. console.groq.com/docs/deprecations).
    Les requêtes avec ce modèle échouent maintenant avec une erreur 404. Remplacé par
    `openai/gpt-oss-120b`, le modèle de migration recommandé par Groq. Si ce modèle est à
    son tour décommissionné dans le futur, vérifier console.groq.com/docs/deprecations et
    mettre à jour la valeur par défaut ci-dessous.

    NB (2026-09-13) : la valeur par défaut peut désormais être surchargée sans toucher au
    code via la variable d'environnement optionnelle GROQ_MODEL (GitHub Secret ou variable
    de repo), pour pouvoir réagir à une future dépréciation sans attendre une session de
    debug complète."""
    name = "groq"

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

    def complete(self, system: str, user: str) -> str:
        data = self._post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout=60,
        )
        return data["choices"][0]["message"]["content"]


class GeminiProvider(LLMProvider):
    """Google Gemini : quota gratuit. https://aistudio.google.com"""
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        data = self._post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": MAX_OUTPUT_TOKENS},
            },
            timeout=60,
        )
        return data["candidates"][0]["content"]["parts"][0]["text"]


class AnthropicProvider(LLMProvider):
    """Anthropic Claude : pas de quota gratuit permanent, à utiliser seulement si
    l'utilisateur a des crédits API disponibles (cf. cahier §19, objectif 0€)."""
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str) -> str:
        data = self._post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=90,
        )
        return "".join(block["text"] for block in data["content"] if block["type"] == "text")


class MistralProvider(LLMProvider):
    """Mistral AI (La Plateforme), plan gratuit "Experiment". https://console.mistral.ai

    NB (2026-09-19, ajouté en repli de Gemini) : le plan gratuit ne demande qu'une
    vérification par numéro de téléphone (pas de carte bancaire), avec une limite d'âge de
    13 ans + autorisation parentale si mineur -- pas de blocage "compte Google adulte"
    comme rencontré avec Gemini. Quota très généreux (1 milliard de tokens/mois, cf.
    console.mistral.ai/limits). API compatible OpenAI (même forme que Groq)."""
    name = "mistral"

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

    def complete(self, system: str, user: str) -> str:
        data = self._post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout=60,
        )
        return data["choices"][0]["message"]["content"]


class CerebrasProvider(LLMProvider):
    """Cerebras Cloud, plan gratuit "Developer". https://cloud.cerebras.ai

    NB (2026-09-19, ajouté en repli de Gemini) : inscription par email, pas de carte
    bancaire ni de vérification d'âge particulière signalée. Jusqu'à 1M tokens/jour sur
    les modèles gratuits (llama-3.3-70b, llama3.1-8b), inférence très rapide (matériel
    dédié Cerebras). API compatible OpenAI (même forme que Groq/Mistral).

    NB (corrigé le 2026-09-20) : "llama-3.3-70b" (valeur par défaut jusqu'ici, documentée
    partout dans la doc publique Cerebras) échouait en conditions réelles avec une erreur
    404 "Model does not exist or you do not have access to it" -- probablement une
    restriction propre au compte gratuit de l'utilisateur (certains modèles Cerebras ne
    sont pas activés par défaut sur tous les comptes développeur). Remplacé par
    "gpt-oss-120b", également disponible gratuitement chez Cerebras et plus généralement
    accessible sur le tier gratuit. Non vérifié en conditions réelles au moment de ce
    correctif (accès à api.cerebras.ai impossible depuis le sandbox qui a écrit ce code) --
    à confirmer sur le prochain run réel ; si ça échoue encore, vérifier les modèles
    réellement activés sur https://cloud.cerebras.ai (page "Models") et les passer via la
    variable d'environnement CEREBRAS_MODEL plutôt que de retoucher le code."""
    name = "cerebras"

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b")

    def complete(self, system: str, user: str) -> str:
        data = self._post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout=60,
        )
        return data["choices"][0]["message"]["content"]


# cf. cahier §19 : ordre de priorité par défaut des providers de repli. Groq en tête (quota
# gratuit le plus généreux et le plus rapide constaté en pratique), puis Mistral et Cerebras
# (2026-09-19 : ajoutés comme repli de Gemini, qui bloque les comptes mineurs -- ni Mistral
# ni Cerebras n'imposent ce type de vérification d'âge liée au compte), puis Gemini (toujours
# utilisable si le compte le permet), Anthropic en dernier (pas de quota gratuit permanent).
_PROVIDER_BUILDERS = {
    "groq": lambda key: GroqProvider(key),
    "mistral": lambda key: MistralProvider(key),
    "cerebras": lambda key: CerebrasProvider(key),
    "gemini": lambda key: GeminiProvider(key),
    "anthropic": lambda key: AnthropicProvider(key),
}
_ENV_KEY_BY_PROVIDER = {
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
_DEFAULT_FALLBACK_ORDER = ("groq", "mistral", "cerebras", "gemini", "anthropic")


def _build_provider(name: str) -> LLMProvider | None:
    key = os.environ.get(_ENV_KEY_BY_PROVIDER.get(name, ""))
    if not key:
        return None
    return _PROVIDER_BUILDERS[name](key)


def get_provider() -> LLMProvider | None:
    """Sélectionne le provider PRÉFÉRÉ selon LLM_PROVIDER + clé disponible. Retourne None si
    LLM_PROVIDER n'est pas défini/reconnu ou si sa clé manque -- utilisé pour les logs et par
    get_providers() ci-dessous. Ne pas utiliser seul pour décider d'abandonner la synthèse
    LLM : cf. get_providers(), qui inclut aussi les providers de repli."""
    provider_name = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if provider_name not in _PROVIDER_BUILDERS:
        if provider_name:
            logger.warning("LLM_PROVIDER non reconnu: %r", provider_name)
        return None
    provider = _build_provider(provider_name)
    if provider is None:
        logger.warning("Clé API manquante pour le provider préféré '%s'", provider_name)
    return provider


def get_providers() -> list[LLMProvider]:
    """Retourne la liste ORDONNÉE de tous les providers utilisables (clé API disponible dans
    les secrets GitHub) : le provider choisi via LLM_PROVIDER en premier s'il est disponible,
    puis les autres comme repli automatique.

    NB (2026-09-19, demande explicite) : jusqu'ici, si le provider unique (typiquement Groq)
    échouait, le pipeline tombait directement en mode fallback sans texte rédigé -- alors
    qu'un simple deuxième secret (ex: GEMINI_API_KEY) suffirait souvent à obtenir quand même
    une vraie synthèse. cf. briefing_generator.generate() qui parcourt cette liste et n'abandonne
    la synthèse rédigée qu'après avoir épuisé TOUS les providers configurés. Ne coûte rien de
    plus (toujours 0 quota utilisé si aucun repli n'est nécessaire) et respecte l'objectif 0€
    (cf. cahier §19) tant que le(s) provider(s) de repli restent sur leur tier gratuit."""
    preferred = os.environ.get("LLM_PROVIDER", "").strip().lower()
    order = list(_DEFAULT_FALLBACK_ORDER)
    if preferred in _PROVIDER_BUILDERS and preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)

    providers: list[LLMProvider] = []
    for name in order:
        provider = _build_provider(name)
        if provider:
            providers.append(provider)

    if not providers:
        logger.warning(
            "Aucun provider LLM disponible (aucune clé API configurée parmi %s)",
            ", ".join(_ENV_KEY_BY_PROVIDER.values()),
        )
    elif len(providers) > 1:
        logger.info(
            "Providers LLM disponibles (ordre d'essai): %s",
            " -> ".join(p.name for p in providers),
        )
    return providers
