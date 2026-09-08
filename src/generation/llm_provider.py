"""Abstraction multi-fournisseurs LLM (cf. README §4 pour le choix et les clés).

Objectif : pouvoir changer de fournisseur (Groq, Gemini, Anthropic, ...) en changeant
uniquement la variable d'environnement LLM_PROVIDER, sans toucher au reste du pipeline.
Chaque provider expose la même méthode `complete(system, user) -> str`.

Aucun provider n'est appelé si aucune clé n'est configurée : `get_provider()` retourne
None dans ce cas, et l'appelant (briefing_generator.py) doit basculer en mode fallback
(cf. cahier §21 : ne jamais planter le pipeline, ne jamais inventer).
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger("morning_briefing.generation.llm")


class LLMProvider:
    name = "base"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class GroqProvider(LLMProvider):
    """Groq : quota gratuit généreux, très rapide. https://console.groq.com"""
    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


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
        resp = requests.post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.3},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


class AnthropicProvider(LLMProvider):
    """Anthropic Claude : pas de quota gratuit permanent, à utiliser seulement si
    l'utilisateur a des crédits API disponibles (cf. cahier §19, objectif 0€)."""
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = requests.post(
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
        resp.raise_for_status()
        data = resp.json()
        return "".join(block["text"] for block in data["content"] if block["type"] == "text")


def get_provider() -> LLMProvider | None:
    """Sélectionne le provider selon LLM_PROVIDER + clé disponible. Retourne None si
    aucune clé n'est configurée (mode fallback pris en charge par l'appelant)."""
    provider_name = os.environ.get("LLM_PROVIDER", "").strip().lower()

    if provider_name == "groq":
        key = os.environ.get("GROQ_API_KEY")
        if key:
            return GroqProvider(key)
    elif provider_name == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            return GeminiProvider(key)
    elif provider_name == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if key:
            return AnthropicProvider(key)
    else:
        logger.warning("LLM_PROVIDER non reconnu ou non défini: %r", provider_name)
        return None

    logger.warning("Clé API manquante pour le provider '%s'", provider_name)
    return None
