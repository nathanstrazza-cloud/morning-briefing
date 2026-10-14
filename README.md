# Morning Briefing

Site personnel de veille d'actualité automatisée : chaque jour ouvré vers 06h10 (Europe/Paris), un pipeline collecte, vérifie, hiérarchise et rédige
un briefing (actualité France/Monde, marchés, sport, science, anglais du jour, météo, citation) publié sur GitHub Pages. Un seul utilisateur, coût visé 0 €,
**fiabilité avant tout** (ne jamais inventer : mieux vaut ne rien afficher).

> **Reprise du projet (humain ou IA) : lire `CONTEXT.md`** (état, règles, défauts connus, architecture détaillée).
> `OPERATIONS.md` : cron, branches `main`/`dev`, Dev Test. `archives/` : historique. `cahier_des_charges.md` : intentions d'origine, indicatives.

## 1. Architecture

```
src/main.py            orchestrateur (seul à connaître l'ordre des étapes)
src/collecte/          ÉTAPE 1 — RSS, marchés (Yahoo Finance), météo (Open-Meteo), sport, calendrier (ESPN), extraits Wikipédia
src/analyse/           ÉTAPE 2 — zones France/Monde, déduplication, scoring, vérification, diversité
src/generation/        ÉTAPE 3 — rédaction LLM par parties (plan : config/llm_plan.yaml) + garde-fous codés
src/stockage/          ÉTAPE 4 — JSON par date, latest/index/status, rotation des briefings
config/                config.yaml (sources, seuils, plafonds), llm_plan.yaml, banques (citations, textes anglais, sujets science)
docs/                  site statique (HTML/CSS/JS sans framework) + docs/data/briefings/ (données publiques) — servi par GitHub Pages
tests/                 205 tests sans réseau :  python3 -m pytest -q tests
.github/workflows/     briefing.yml (production), dev-test.yml (manuel), llm-probe.yml (manuel)
```

Chaque étape est un module indépendant (entrées/sorties explicites) : on peut changer de fournisseur LLM ou ajouter une source sans toucher au reste.

**Flux** : fenêtre de collecte (lundi = week-end inclus) → collecte → zones → dédup → scoring → vérification → diversité → rédaction LLM (parties indépendantes, secours en chaîne,
repli sans LLM) → garde-fous (nombres, noms propres, sources) → stockage → site. **Erreurs** : une source qui échoue est ignorée ; si tout échoue, `latest.json` n'est pas touché
(le dernier briefing valide reste affiché) et l'onglet *Erreurs* du site montre l'historique des runs (`status_history.json`).

## 2. Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # clés LLM (optionnel : sans clé, briefing minimal)
python -m src.main --no-llm          # run sans LLM ; --date AAAA-MM-JJ pour une autre date
python -m scripts.generate_demo_data && python -m http.server -d docs 8000   # site avec données factices
```

## 3. Hébergement et clés

- **GitHub Pages** : Settings → Pages → branche `main`, dossier `/docs` (site + données). **GitHub Actions** : un run quotidien de quelques minutes, très sous le quota gratuit.
- Stockage = les JSON committés dans `docs/data/briefings/` (30 derniers) + `archives/` ; les logs de run sont des artefacts Actions (90 jours), non versionnés.
- Secrets (Settings → Secrets and variables → Actions) : `GROQ_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY` (tous gratuits, sans carte). Détails, limites et ordre de repli : `CONTEXT.md` §5.
  **Jamais de clé ni de jeton dans le dépôt.** RSS, Open-Meteo, Yahoo Finance, ESPN, Wikipédia : gratuits, sans clé.

## 4. Roadmap

Voir `CONTEXT.md` §3 (défauts à corriger) et §7 (mémoire/personnalisation, approfondissement à la demande : non commencés, à ne lancer que sur demande).

## 5. Principes

Ordre de priorité : **1. Fiabilité — 2. Robustesse — 3. Qualité de sélection — 4. Qualité rédactionnelle — 5. Design — 6. Personnalisation.**
Ne jamais inventer une information, un chiffre de marché ou une citation ; toujours préférer ne rien afficher plutôt qu'afficher une donnée non vérifiée ; garder le dernier briefing valide en cas d'échec.
