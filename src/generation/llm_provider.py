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
# NB (corrigé le 2026-09-27) : confirmé par les logs réels du 26 et du 27/09 -- même avec
# max_tokens=3500, Groq répond en 429 "tokens per minute (TPM)" dès la 1ère tentative de la
# journée (donc PAS un effet cumulatif de plusieurs tentatives). Recherche du tier gratuit
# Groq pour openai/gpt-oss-120b : la limite TPM publiée pour ce modèle est de l'ordre de
# 8 000 tokens/minute seulement (contre 1M tokens/JOUR) -- un modèle 120B coûte cher à servir,
# donc Groq alloue un TPM minuscule sur le tier gratuit même si le total journalier semble
# généreux. Avec ~3000 tokens de prompt (system+user) + 3500 de sortie demandée, une seule
# requête consommait déjà 90%+ de la fenêtre -- il ne restait aucune marge pour un 2e appel
# (science) dans la même minute, ni pour un léger dépassement d'estimation.
#
# Solution retenue (cf. demande explicite de l'utilisateur le 27/09) : scinder l'appel LLM en
# DEUX requêtes indépendantes plutôt que de continuer à réduire un seul gros appel :
#   - "bloc" (actualité+marchés+sport+citation) : JSON court, sortie majoritairement des
#     phrases courtes -> budget de sortie réduit.
#   - "science" : article ~10 min de lecture, le plus gourmand en tokens de SORTIE -> budget
#     dédié, séparé du bloc pour ne pas cumuler dans la même fenêtre TPM.
# Cf. get_providers(role=...) ci-dessous : le bloc et l'article science n'utilisent pas le
# même ordre de providers par défaut (Groq priorisé pour le bloc, Mistral pour la science) --
# objectif : que les deux appels d'un même run se répartissent naturellement sur deux comptes
# différents plutôt que de cumuler sur le TPM d'un seul, tout en gardant chacun capable de
# basculer sur l'autre en repli si besoin (Mistral et Groq restent complémentaires, pas
# seulement l'un en secours pur de l'autre).
MAX_OUTPUT_TOKENS = 1800  # budget par défaut (bloc) ; cf. briefing_generator pour les valeurs
# dédiées par appel (MAX_OUTPUT_TOKENS_BLOC / MAX_OUTPUT_TOKENS_SCIENCE), passées explicitement
# à `complete(..., max_tokens=...)` -- cette constante ne sert plus que de valeur par défaut si
# un appelant ne précise rien.


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

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
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

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
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
                "max_tokens": max_tokens,
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

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        data = self._post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
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

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
        data = self._post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
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
        self.model = model or os.environ.get("MISTRAL_MODEL") or "open-mistral-nemo"  # 29/09: mistral-small/medium/magistral = quota gratuit 0 req/min (429 code 1300) ; open-mistral-nemo et ministral-8b-latest répondent

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
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
                "max_tokens": max_tokens,
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

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
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
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        return data["choices"][0]["message"]["content"]


class OpenRouterProvider(LLMProvider):
    """OpenRouter (openrouter.ai), modèles ":free" -- ajouté le 2026-09-28.

    Aucune carte bancaire requise ; quota gratuit partagé entre tous les modèles :free
    (~20 requêtes/min, ~50 requêtes/jour d'après la doc publique) -- très largement suffisant
    pour 3 appels/jour. API compatible OpenAI. Les modèles gratuits tournent sans préavis :
    on envoie donc une liste `models` (repli côté OpenRouter) plutôt qu'un seul identifiant.
    Surcharge possible sans toucher au code : OPENROUTER_MODEL (un identifiant) --
    la liste de repli reste alors celle par défaut derrière lui.
    Non vérifié en conditions réelles au moment de l'écriture (pas d'accès réseau depuis le
    sandbox) : lire l'onglet Erreurs après le 1er run qui l'utilise."""
    name = "openrouter"

    DEFAULT_MODELS = (
        "openrouter/free",  # 29/09: gpt-oss-120b:free et llama-3.3:free = 404 (plus gratuits)
        "nvidia/nemotron-3-super-120b-a12b:free",
        "google/gemma-4-31b-it:free",
    )

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        preferred = model or os.environ.get("OPENROUTER_MODEL", "").strip()
        models = list(self.DEFAULT_MODELS)
        if preferred:
            if preferred in models:
                models.remove(preferred)
            models.insert(0, preferred)
        self.models = models

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
        data = self._post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/nathanstrazza-cloud/morning-briefing",
                "X-Title": "Morning Briefing",
            },
            json={
                "models": self.models,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            timeout=90,
        )
        return _extract_content(data, self.name)


class NvidiaProvider(LLMProvider):
    """NVIDIA NIM (build.nvidia.com) -- ajouté le 2026-09-28.

    Pas de carte bancaire ; ~40 requêtes/min d'après la doc publique. API compatible OpenAI.
    Modèle par défaut : meta/llama-3.3-70b-instruct (bon en français, JSON strict correct).
    Surcharge possible : NVIDIA_MODEL. Non vérifié en conditions réelles (cf. OpenRouter)."""
    name = "nvidia"

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("NVIDIA_MODEL") or "nvidia/nemotron-3.5-lightning-30b-a3b"  # 29/09: llama-3.3/3.1-70b et gpt-oss-120b = 410 Gone ; alternative testée OK : openai/gpt-oss-20b

    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
        data = self._post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            timeout=90,
        )
        return _extract_content(data, self.name)


def _extract_content(data: dict, provider_name: str) -> str:
    """Extrait le texte d'une réponse OpenAI-compatible ; lève LLMError si vide (ex: modèle
    à raisonnement dont le budget max_tokens a été entièrement consommé par la réflexion)."""
    try:
        content = data["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        content = None
    if not content or not str(content).strip():
        raise LLMError(f"Réponse vide (provider={provider_name})")
    return content


_PROVIDER_BUILDERS = {
    "groq": lambda key: GroqProvider(key),
    "mistral": lambda key: MistralProvider(key),
    "cerebras": lambda key: CerebrasProvider(key),
    "openrouter": lambda key: OpenRouterProvider(key),
    "nvidia": lambda key: NvidiaProvider(key),
    "gemini": lambda key: GeminiProvider(key),
    "anthropic": lambda key: AnthropicProvider(key),
}
_ENV_KEY_BY_PROVIDER = {
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

# NB (corrigé le 2026-09-27) : DEUX ordres de repli par défaut au lieu d'un seul, un par
# "rôle" d'appel (cf. briefing_generator, qui scinde désormais la génération en 2 requêtes
# indépendantes -- bloc actu/marchés/sport et article science, cf. MAX_OUTPUT_TOKENS
# ci-dessus). Objectif explicite de l'utilisateur (27/09) : que Groq et Mistral se
# répartissent naturellement le travail au lieu que le second serve UNIQUEMENT de secours du
# premier -- en pratique, sur un run normal, le bloc part sur Groq et la science part sur
# Mistral EN PARALLÈLE logique (2 comptes différents, 2 fenêtres TPM différentes), donc les
# deux appels d'un run ne se marchent plus dessus sur le même quota/minute. Chacun des deux
# reste capable de basculer sur l'autre si son 1er choix échoue (repli croisé complet, pas un
# simple ordre figé) : role="bloc" essaie Groq -> Mistral -> Gemini -> Anthropic ; role=
# "science" essaie Mistral -> Groq -> Gemini -> Anthropic.
#
# Cerebras RETIRÉ des deux ordres par défaut (décision prise le 2026-09-27, cf. cahier §19 :
# "aucun service payant ne doit devenir une dépendance") : 3 runs réels consécutifs (25, 26,
# 27/09) ont tous échoué avec "402 Payment Required" sur le modèle configuré -- ce n'est donc
# pas un aléa mais un fait confirmé : le compte Cerebras actuel n'a pas de tier gratuit
# fonctionnel pour ce modèle. Le garder en repli automatique n'apportait aucune valeur (il
# n'a jamais réussi une seule fois) tout en polluant `_erreur_llm` d'un message toujours
# identique et sans intérêt diagnostique. La classe CerebrasProvider reste dans le code (rien
# de perdu) et reste sélectionnable explicitement via LLM_PROVIDER=cerebras + CEREBRAS_API_KEY
# si un jour un tier gratuit fonctionnel est activé sur ce compte -- il suffira alors de le
# rajouter dans les deux tuples ci-dessous.
# NB (2026-09-28) : run réel du 28/09 = bloc OK sur Groq, mais science ET anglais en 429
# (Groq TPM saturé par le bloc, Mistral également en rate-limit). Ajout d'OpenRouter et de
# NVIDIA NIM (clés OPENROUTER_API_KEY / NVIDIA_API_KEY, aucune carte bancaire) et ORDRE
# DÉDIÉ PAR RÔLE pour que chacun des 3 appels démarre sur un compte/quota différent :
#   bloc    : Groq       -> OpenRouter -> Mistral -> NVIDIA
#   science : Mistral    -> NVIDIA     -> Groq    -> OpenRouter
#   anglais : OpenRouter -> NVIDIA     -> Groq    -> Mistral
# (Gemini/Anthropic en dernier recours si un jour configurés.) Un provider sans clé est
# simplement ignoré. En complément, briefing_generator espace les appels de 60 s.
_DEFAULT_FALLBACK_ORDER = ("groq", "openrouter", "mistral", "nvidia", "gemini", "anthropic")
_SCIENCE_FALLBACK_ORDER = ("mistral", "nvidia", "groq", "openrouter", "gemini", "anthropic")
_ANGLAIS_FALLBACK_ORDER = ("openrouter", "nvidia", "groq", "mistral", "gemini", "anthropic")
_ORDER_BY_ROLE = {
    "bloc": _DEFAULT_FALLBACK_ORDER,
    "science": _SCIENCE_FALLBACK_ORDER,
    "anglais": _ANGLAIS_FALLBACK_ORDER,
}


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


def get_providers(role: str = "bloc") -> list[LLMProvider]:
    """Retourne la liste ORDONNÉE de tous les providers utilisables (clé API disponible dans
    les secrets GitHub) pour le rôle d'appel donné ("bloc" ou "science", cf. NB ci-dessus).

    Si LLM_PROVIDER est explicitement défini (préférence manuelle de l'utilisateur), ce
    provider passe TOUJOURS en tête, quel que soit le rôle -- y compris s'il ne fait pas
    partie de l'ordre par défaut de ce rôle (ex: LLM_PROVIDER=cerebras reste utilisable
    manuellement même si Cerebras n'est plus dans les ordres par défaut).

    NB (2026-09-19, demande explicite) : jusqu'ici, si le provider unique (typiquement Groq)
    échouait, le pipeline tombait directement en mode fallback sans texte rédigé -- alors
    qu'un simple deuxième secret (ex: MISTRAL_API_KEY) suffirait souvent à obtenir quand même
    une vraie synthèse. cf. briefing_generator.generate() qui parcourt cette liste et n'abandonne
    la synthèse rédigée qu'après avoir épuisé TOUS les providers configurés pour ce rôle. Ne
    coûte rien de plus (toujours 0 quota utilisé si aucun repli n'est nécessaire) et respecte
    l'objectif 0€ (cf. cahier §19) tant que le(s) provider(s) de repli restent sur leur tier
    gratuit."""
    preferred = os.environ.get("LLM_PROVIDER", "").strip().lower()
    base_order = _ORDER_BY_ROLE.get(role, _DEFAULT_FALLBACK_ORDER)
    order = list(base_order)
    if preferred in _PROVIDER_BUILDERS:
        # NB (2026-09-28) : découverte en testant -- avec LLM_PROVIDER=groq (valeur du secret
        # GitHub), l'ancien code plaçait Groq en TÊTE POUR TOUS LES RÔLES, annulant l'ordre
        # dédié "science"/"anglais" : les 3 appels partaient sur Groq et saturaient son TPM
        # (cause probable des 429 du 28/09). La préférence ne pilote donc plus que le rôle
        # "bloc" ; pour les autres rôles, elle est conservée mais à sa place par défaut (ou en
        # dernier recours si absente de l'ordre du rôle, ex: cerebras).
        if role == "bloc":
            if preferred in order:
                order.remove(preferred)
            order.insert(0, preferred)
        elif preferred not in order:
            order.append(preferred)

    providers: list[LLMProvider] = []
    for name in order:
        provider = _build_provider(name)
        if provider:
            providers.append(provider)

    if not providers:
        logger.warning(
            "Aucun provider LLM disponible pour le rôle '%s' (aucune clé API configurée parmi %s)",
            role, ", ".join(_ENV_KEY_BY_PROVIDER.values()),
        )
    elif len(providers) > 1:
        logger.info(
            "Providers LLM disponibles pour le rôle '%s' (ordre d'essai): %s",
            role, " -> ".join(p.name for p in providers),
        )
    return providers
