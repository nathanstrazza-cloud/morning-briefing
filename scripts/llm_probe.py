#!/usr/bin/env python3
"""Sonde des 4 fournisseurs LLM (Groq, Mistral, OpenRouter, NVIDIA NIM).

BUT : pour chaque fournisseur, (1) vérifier qu'une requête à 1 token de sortie fonctionne
avec la clé configurée, (2) relever les LIMITES annoncées (en-têtes x-ratelimit-*, endpoints
d'info de compte, catalogue de modèles), (3) en cas d'échec, afficher le code HTTP et le corps
de l'erreur (c'est le corps qui donne la vraie cause).

Utilisation :
  - En local / CI : les clés sont lues dans l'environnement
      GROQ_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY, NVIDIA_API_KEY
  - Sur GitHub : Actions > "LLM probe" > Run workflow (les secrets sont déjà configurés).
  - Sortie : texte lisible sur stdout + docs/... JAMAIS : le fichier de sortie contient
    uniquement des en-têtes de limites et des codes, jamais une clé.
  - Option --json FICHIER : écrit aussi le résultat structuré (utile pour une autre IA).

Aucun secret n'est jamais affiché : les en-têtes Authorization ne sont pas relus, et tout
texte de réponse est passé par `_scrub()` qui masque toute chaîne ressemblant à une clé.
Dépendance unique : `requests` (déjà dans requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import requests

TIMEOUT = 45
PING = [{"role": "user", "content": "Hi"}]

# Modèles testés par défaut (surchargeables par les variables d'environnement du pipeline,
# cf. src/generation/llm_provider.py : GROQ_MODEL, MISTRAL_MODEL, OPENROUTER_MODEL, NVIDIA_MODEL).
GROQ_MODEL = os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b"  # `or` : une variable vide ne doit pas écraser le défaut
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL") or "mistral-small-latest"
OPENROUTER_MODELS = [
    m for m in [os.environ.get("OPENROUTER_MODEL", "").strip()] if m
] + [
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-120b:free",  # retiré du gratuit au 29/09/2026 (404) : gardé pour détecter un retour
]
# NVIDIA : meta/llama-3.3-70b-instruct renvoie 410 Gone (retiré le 26/08/2026). On teste
# d'abord NVIDIA_MODEL s'il est défini, puis des candidats ; seuls ceux présents dans
# /v1/models du compte sont réellement essayés.
NVIDIA_CANDIDATES = [
    m for m in [os.environ.get("NVIDIA_MODEL", "").strip()] if m
] + [
    "nvidia/nemotron-3-super-120b-a12b",
    "mistralai/mistral-large-2-instruct",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "mistralai/mistral-large",
    "nv-mistralai/mistral-nemo-12b-instruct",
    # Retirés (410 Gone constatés le 29/09/2026) : meta/llama-3.3-70b-instruct, meta/llama-3.1-70b-instruct,
    # openai/gpt-oss-120b.
]

_KEY_RE = re.compile(r"(gsk_|nvapi-|sk-or-|ghp_|github_pat_)[A-Za-z0-9_\-]{8,}")


def _scrub(text: str, secrets: list[str]) -> str:
    text = _KEY_RE.sub("[MASQUÉ]", text or "")
    for s in secrets:
        if s and len(s) > 8:
            text = text.replace(s, "[MASQUÉ]")
    return text


def _limit_headers(resp: requests.Response) -> dict:
    """Tous les en-têtes qui parlent de limites/quotas/reset/retry."""
    out = {}
    for k, v in resp.headers.items():
        lk = k.lower()
        if any(t in lk for t in ("ratelimit", "rate-limit", "retry-after", "quota", "remaining", "limit")):
            out[lk] = v
    return out


def _chat(url: str, key: str, model_payload: dict, extra_headers: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    body = {"messages": PING, "max_tokens": 1, "temperature": 0}
    body.update(model_payload)
    t0 = time.time()
    try:
        r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    except requests.RequestException as exc:  # réseau / timeout
        return {"ok": False, "http": None, "error": f"{type(exc).__name__}: {exc}", "latency_s": round(time.time() - t0, 2)}
    res = {
        "ok": r.ok,
        "http": r.status_code,
        "latency_s": round(time.time() - t0, 2),
        "limit_headers": _limit_headers(r),
    }
    if r.ok:
        try:
            data = r.json()
            res["model_used"] = data.get("model")
            res["usage"] = data.get("usage")
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            # Avec max_tokens=1 un modèle à raisonnement peut renvoyer content vide : c'est NORMAL,
            # la clé et le quota fonctionnent (HTTP 200 = succès de la sonde).
            res["content_preview"] = (msg.get("content") or "")[:40]
        except ValueError:
            res["error"] = "réponse 200 non JSON"
    else:
        res["error"] = (r.text or "")[:600]
    return res


def _get(url: str, key: str | None = None, timeout: int = TIMEOUT) -> requests.Response | None:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException:
        return None


def probe_groq(key: str) -> dict:
    res = {"provider": "groq", "model": GROQ_MODEL}
    res["ping"] = _chat("https://api.groq.com/openai/v1/chat/completions", key, {"model": GROQ_MODEL})
    # Groq renvoie dans les en-têtes : x-ratelimit-limit-requests (par JOUR), x-ratelimit-limit-tokens
    # (par MINUTE), x-ratelimit-remaining-*, x-ratelimit-reset-* (cf. console.groq.com/docs/rate-limits).
    res["limites_lisibles"] = (
        "Groq : requêtes par JOUR (RPD) et tokens par MINUTE (TPM) dans les en-têtes "
        "x-ratelimit-limit-requests / x-ratelimit-limit-tokens ; quotas propres à chaque modèle."
    )
    return res


def probe_mistral(key: str) -> dict:
    res = {"provider": "mistral", "model": MISTRAL_MODEL}
    r = _get("https://api.mistral.ai/v1/models", key)
    if r is not None:
        res["models_http"] = r.status_code
        if r.ok:
            try:
                ids = sorted(m.get("id", "") for m in r.json().get("data", []))
                res["models_count"] = len(ids)
                res["models_sample"] = [i for i in ids if "small" in i or "medium" in i or "large" in i][:12]
            except ValueError:
                pass
        else:
            res["models_error"] = (r.text or "")[:300]
    res["ping"] = _chat("https://api.mistral.ai/v1/chat/completions", key, {"model": MISTRAL_MODEL})
    res["limites_lisibles"] = (
        "Mistral ne publie plus de chiffres fixes : 3 limites par ORGANISATION (requêtes/seconde, "
        "tokens/minute, tokens/mois) visibles SEULEMENT sur console.mistral.ai > Limits (Admin). "
        "En-têtes x-ratelimit-* parfois renvoyés (cf. ping.limit_headers)."
    )
    return res


def probe_openrouter(key: str) -> dict:
    res = {"provider": "openrouter", "models_tested": OPENROUTER_MODELS}
    # Endpoint d'info de clé : donne limit, usage, is_free_tier et rate_limit quand il existe.
    r = _get("https://openrouter.ai/api/v1/auth/key", key)
    if r is not None:
        res["key_info_http"] = r.status_code
        try:
            res["key_info"] = r.json().get("data", r.json()) if r.ok else (r.text or "")[:300]
        except ValueError:
            res["key_info"] = (r.text or "")[:300]
    # Catalogue public : quels modèles sont RÉELLEMENT gratuits aujourd'hui (prix prompt+completion = 0).
    cat = _get("https://openrouter.ai/api/v1/models")
    if cat is not None and cat.ok:
        try:
            free = [m["id"] for m in cat.json().get("data", [])
                    if str((m.get("pricing") or {}).get("prompt")) in ("0", "0.0") and str((m.get("pricing") or {}).get("completion")) in ("0", "0.0")]
            res["modeles_gratuits_catalogue"] = sorted(free)
        except (ValueError, KeyError):
            pass
    # Un modèle à la fois (pas de liste `models` ici : on veut savoir lequel marche vraiment).
    res["per_model"] = {}
    for m in OPENROUTER_MODELS:
        res["per_model"][m] = _chat(
            "https://openrouter.ai/api/v1/chat/completions", key, {"model": m},
            {"HTTP-Referer": "https://github.com/nathanstrazza-cloud/morning-briefing", "X-Title": "Morning Briefing probe"},
        )
        if res["per_model"][m]["ok"]:
            break  # un seul modèle qui répond suffit pour la sonde (économise le quota journalier)
        time.sleep(3)
    res["ping"] = next((v for v in res["per_model"].values() if v["ok"]), list(res["per_model"].values())[-1])
    res["limites_lisibles"] = (
        "OpenRouter : modèles ':free' partagent un quota commun (~20 requêtes/minute ; ~50 requêtes/jour "
        "sans crédit, ~1000/jour si ≥10 $ de crédit déposés d'après la doc publique) ; le champ key_info "
        "confirme is_free_tier et le rate_limit réel du compte. Les modèles gratuits sont aussi limités "
        "en amont (429 'rate-limited upstream' = fournisseur du modèle saturé, pas votre quota)."
    )
    return res


def probe_nvidia(key: str) -> dict:
    res = {"provider": "nvidia", "models_tested": []}
    r = _get("https://integrate.api.nvidia.com/v1/models", key)
    available: set[str] = set()
    if r is not None:
        res["models_http"] = r.status_code
        if r.ok:
            try:
                available = {m.get("id", "") for m in r.json().get("data", [])}
                res["models_count"] = len(available)
            except ValueError:
                pass
        else:
            res["models_error"] = (r.text or "")[:300]
    # On n'essaie que les candidats présents au catalogue (si le catalogue est vide/inaccessible,
    # on essaie quand même les 3 premiers).
    to_try = [m for m in NVIDIA_CANDIDATES if m in available] or NVIDIA_CANDIDATES[:3]
    res["per_model"] = {}
    for m in to_try:
        res["per_model"][m] = _chat("https://integrate.api.nvidia.com/v1/chat/completions", key, {"model": m},
                                    {"Accept": "application/json"})
        res["models_tested"].append(m)
        if res["per_model"][m]["ok"] and "model" not in res:
            res["model"] = m  # 1er qui répond ; on continue quand même pour lister TOUS ceux qui marchent
        time.sleep(1.5)
    res["modeles_qui_repondent"] = [m for m, v in res["per_model"].items() if v["ok"]]
    res["ping"] = next((v for v in res["per_model"].values() if v["ok"]), list(res["per_model"].values())[-1])
    if available:
        res["autres_modeles_llm_candidats"] = sorted(
            i for i in available if re.search(r"(llama|mistral|gpt-oss|nemotron|qwen)", i, re.I)
        )
    res["limites_lisibles"] = (
        "NVIDIA NIM (build.nvidia.com) : ~40 requêtes/minute d'après la doc publique, quota en 'crédits' "
        "d'essai plutôt qu'en tokens ; PAS d'en-têtes x-ratelimit fiables -> à vérifier sur le tableau de "
        "bord build.nvidia.com. Un 410 Gone = modèle retiré : choisir un autre id dans "
        "autres_modeles_llm_candidats et le passer via NVIDIA_MODEL."
    )
    return res


PROBES = [
    ("groq", "GROQ_API_KEY", probe_groq),
    ("mistral", "MISTRAL_API_KEY", probe_mistral),
    ("openrouter", "OPENROUTER_API_KEY", probe_openrouter),
    ("nvidia", "NVIDIA_API_KEY", probe_nvidia),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", help="chemin d'un fichier JSON de sortie")
    ap.add_argument("--only", help="liste de fournisseurs séparés par des virgules")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    results = []
    secrets = [os.environ.get(env, "") for _, env, _ in PROBES]
    for name, env, fn in PROBES:
        if only and name not in only:
            continue
        key = os.environ.get(env, "").strip()
        if not key:
            results.append({"provider": name, "verdict": "PAS DE CLÉ", "detail": f"secret {env} absent/vide"})
            continue
        try:
            res = fn(key)
        except Exception as exc:  # une sonde ne doit jamais faire planter les autres
            res = {"provider": name, "verdict": "ERREUR SONDE", "detail": f"{type(exc).__name__}: {exc}"}
        else:
            ping = res.get("ping", {})
            res["verdict"] = "OK" if ping.get("ok") else f"ÉCHEC (HTTP {ping.get('http')})"
        results.append(res)

    # Affichage lisible
    print("=" * 70)
    print("SONDE LLM — requête à 1 token de sortie par fournisseur")
    print("=" * 70)
    for res in results:
        print(f"\n### {res['provider'].upper()} -> {res['verdict']}")
        ping = res.get("ping")
        if ping:
            print(f"  HTTP {ping.get('http')} en {ping.get('latency_s')} s, modèle utilisé : {ping.get('model_used') or res.get('model')}")
            if ping.get("error"):
                print("  ERREUR :", _scrub(str(ping["error"]), secrets))
            for k, v in (ping.get("limit_headers") or {}).items():
                print(f"  {k}: {v}")
        if res.get("detail"):
            print("  ", res["detail"])
        for extra in ("key_info", "models_count", "modeles_qui_repondent", "modeles_gratuits_catalogue", "autres_modeles_llm_candidats", "models_sample"):
            if res.get(extra) not in (None, "", []):
                print(f"  {extra}: {_scrub(json.dumps(res[extra], ensure_ascii=False), secrets)}")
        if res.get("per_model"):
            for m, v in res["per_model"].items():
                print(f"  - essai {m}: HTTP {v.get('http')} {'OK' if v.get('ok') else _scrub(str(v.get('error'))[:200], secrets)}")
        if res.get("limites_lisibles"):
            print("  LIMITES :", res["limites_lisibles"])

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(_scrub(json.dumps(results, ensure_ascii=False, indent=2), secrets))
    ok = sum(1 for r in results if r["verdict"] == "OK")
    print(f"\nRésumé : {ok}/{len(results)} fournisseurs OK")
    return 0  # la sonde informe, elle n'échoue pas (le workflow reste vert même si un provider est KO)


if __name__ == "__main__":
    sys.exit(main())
