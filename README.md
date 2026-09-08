# Morning Briefing — V1

Site personnel de veille d'actualité automatisée, généré chaque matin (lun-ven, 06h30 Europe/Paris).

Ce dépôt implémente la V1 décrite dans `cahier_des_charges.md` (à la racine, copie du cahier
fourni par l'utilisateur — **document de référence, à relire avant toute modification**).

Ce README est écrit pour qu'une autre IA (ou un développeur humain) puisse reprendre le projet
sans contexte supplémentaire. Il documente : ce qui est fait, ce qui est stub/à finir, les choix
d'architecture et pourquoi, et les prochaines étapes concrètes.

---

## 1. État du projet (à la fin de cette session)

**Fait et fonctionnel (logique testable localement, sans clé API) :**
- Structure du pipeline complète : collecte → analyse → génération → stockage → frontend.
- Collecte RSS (France/Monde/Sport/Sciences) : fonctionnelle, ne nécessite aucune clé.
- Collecte météo (Open-Meteo) : fonctionnelle, aucune clé nécessaire.
- Collecte marchés (Stooq CSV) : fonctionnelle, aucune clé nécessaire.
- Déduplication (similarité de titres) : fonctionnelle.
- Scoring d'importance (heuristique mots-clés + catégorie) : fonctionnelle mais **basique**,
  à affiner (voir §7 Roadmap).
- Vérification (fait confirmé / info rapportée / incertaine, selon nombre de sources
  indépendantes qui convergent) : fonctionnelle mais heuristique simple.
- Stockage JSON par date + `latest.json` + `index.json` (historique) : fonctionnel.
- Génération du briefing final (texte, citation, synthèse scientifique) : **nécessite une clé
  LLM** (voir §4). Le code gère plusieurs fournisseurs et un mode `--no-llm` de secours qui
  produit un briefing minimal à partir des seules données brutes (sans synthèse rédigée), pour
  que le pipeline ne casse jamais complètement si le LLM est indisponible.
- Frontend statique (HTML/CSS/JS, aucun framework, aucune dépendance de build) : fonctionnel,
  lit `docs/data/briefings/latest.json` et `docs/data/briefings/index.json`.
- Workflow GitHub Actions (cron 06:30 Paris, lun-ven) : présent, à activer après premier test
  manuel (`workflow_dispatch`).

**Pas encore fait / stub volontaire (cf. cahier des charges §26, ne pas sur-construire trop tôt) :**
- Sources sport détaillées (Spurs NBA à date, calendrier Ligue 1 précis) : le module
  `sports.py` a une structure prête mais les flux RSS sport sont génériques pour l'instant ;
  à affiner avec de vraies sources (L'Équipe RSS, NBA RSS/API gratuite).
- Vérification "source primaire très fiable" n'est pas une vraie fact-check IA, c'est une
  heuristique de comptage de sources. Une vérification plus poussée (recoupement sémantique
  via LLM) est prévue en roadmap mais volontairement pas construite maintenant.
- Pas de comptes utilisateurs / personnalisation (hors-scope V1, cf. cahier §23).
- Pas de tests automatisés (à ajouter, cf. roadmap).

---

## 2. Architecture

```
morning-briefing/
├── cahier_des_charges.md        # copie du cahier des charges (référence)
├── README.md                    # ce fichier
├── requirements.txt
├── .env.example                 # variables d'environnement attendues (aucun secret réel)
├── .gitignore
├── config/
│   └── config.yaml              # sources RSS, seuils, zones météo, indices marché, etc.
├── src/
│   ├── collecte/                # ÉTAPE 1 : récupère les données brutes
│   │   ├── rss_sources.py       # actualité France/Monde/Sciences via flux RSS
│   │   ├── markets.py           # indices/matières premières via Stooq (gratuit, sans clé)
│   │   ├── weather.py           # météo Antibes/Cannes/Valbonne/Grasse via Open-Meteo
│   │   ├── sports.py            # foot/basket/natation/autres via RSS
│   │   └── collector.py         # orchestre tous les collecteurs -> items bruts
│   ├── analyse/                 # ÉTAPE 2 : nettoie et hiérarchise
│   │   ├── dedup.py             # regroupe les articles qui parlent du même événement
│   │   ├── scoring.py           # score d'importance 0-10 par item
│   │   └── verification.py      # statut : fait confirmé / rapporté / incertain
│   ├── generation/               # ÉTAPE 3 : rédige le briefing
│   │   ├── llm_provider.py      # abstraction multi-fournisseurs LLM (Anthropic/Groq/OpenAI-compat)
│   │   └── briefing_generator.py# construit le prompt, appelle le LLM, valide le JSON produit
│   ├── stockage/                 # ÉTAPE 4 : persistance
│   │   └── storage.py            # écrit docs/data/briefings/YYYY-MM-DD.json, latest.json, index.json
│   └── main.py                   # orchestrateur : exécute le pipeline complet, logs, erreurs
├── logs/                         # logs d'exécution (un fichier par run)
├── docs/                         # site statique + données, servi tel quel par GitHub Pages
│   ├── index.html
│   ├── history.html
│   ├── briefing.html             # affichage d'un briefing archivé (?date=YYYY-MM-DD)
│   ├── style.css
│   ├── app.js
│   └── data/briefings/           # sortie JSON (committée = historique + hébergement gratuit)
└── .github/workflows/
    └── briefing.yml              # cron 06:30 Paris, lun-ven + déclenchement manuel
```

**Pourquoi cette séparation (cf. cahier §17) :** chaque étape est un module Python indépendant
qui prend des données en entrée et retourne des données en sortie (pas d'état global caché).
Cela permet de remplacer un module (ex: changer de fournisseur LLM, ajouter une source) sans
toucher au reste du pipeline. `main.py` est le seul fichier qui connaît l'ordre des étapes.

---

## 3. Comment ça tourne (pipeline)

```
main.py
  1. Détermine le jour (lundi = fenêtre élargie week-end, sinon depuis dernier briefing)
  2. collecte.collector.collect_all(config, fenetre) -> items bruts (actu, marchés, météo, sport, science)
  3. analyse.dedup.deduplicate(items) -> événements uniques + sources associées
  4. analyse.scoring.score_items(events) -> chaque event a un score 0-10
  5. analyse.verification.classify(events) -> statut fait confirmé / rapporté / incertain
  6. filtre : on ne garde que score >= seuil (config.yaml, défaut 5) sauf sections obligatoires
     (météo, citation, science) qui ont leur propre logique
  7. generation.briefing_generator.generate(events_filtrés, contexte) -> objet Briefing (dict)
     - si LLM indisponible ou erreur -> generation.briefing_generator.fallback_briefing() :
       briefing minimal, factuel, sans synthèse rédigée, mais jamais de contenu inventé
  8. stockage.storage.save(briefing) -> JSON du jour + mise à jour latest.json + index.json
  9. Le frontend (statique, servi par GitHub Pages) lit ces JSON au chargement de la page.
```

**Gestion d'erreur (cf. cahier §21)** : chaque étape est encapsulée dans un `try/except` dans
`main.py`. Si une source échoue -> on continue avec les autres (log warning). Si la génération
LLM échoue -> `fallback_briefing()`. Si TOUT échoue au point de ne rien avoir de fiable -> le
script **ne touche pas** à `latest.json` (le dernier briefing valide reste affiché), et écrit
un indicateur d'échec dans `docs/data/briefings/status.json` que le frontend peut afficher
("Dernière mise à jour a échoué, vous consultez le dernier briefing valide").

---

## 4. Clé(s) API nécessaires (secrets GitHub)

Le seul point qui **nécessite un choix de l'utilisateur** est le fournisseur LLM pour la
rédaction. Sans lui, le pipeline tourne quand même (mode fallback, données brutes seulement,
pas de synthèse scientifique approfondie ni de rédaction fluide).

Options gratuites (à choisir un, configurer `LLM_PROVIDER` + secret correspondant) :

| Fournisseur | Variable secret GitHub | Gratuit ? |
|---|---|---|
| Groq (Llama/Gemma, très rapide) | `GROQ_API_KEY` | Oui, quota gratuit généreux |
| Google Gemini | `GEMINI_API_KEY` | Oui, quota gratuit |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | Payant (pas de quota gratuit permanent) |

`LLM_PROVIDER` = `groq` | `gemini` | `anthropic` (variable d'environnement, pas un secret,
définie dans `briefing.yml`).

**Recommandation V1 (objectif 0€, cf. cahier §19) : Groq ou Gemini**, pas Anthropic, sauf si
l'utilisateur a déjà des crédits API qu'il veut utiliser.

Aucune autre clé n'est nécessaire : RSS, Open-Meteo et Stooq sont gratuits et sans clé.

Pour ajouter le secret : Settings -> Secrets and variables -> Actions -> New repository secret.
**Ne jamais committer de clé** (cf. cahier §20) — `.env` est dans `.gitignore`.

---

## 5. Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis remplir la clé LLM choisie
python -m src.main --date 2026-09-07          # génère le briefing du jour indiqué
python -m src.main --no-llm                    # test rapide sans clé, briefing minimal
```

Le frontend peut être ouvert directement (`docs/index.html`) ou servi avec
`python -m http.server` depuis la racine si le navigateur bloque les `fetch()` en `file://`.

Pour voir immédiatement un rendu du site sans lancer de vraie collecte ni configurer de clé
API, un jeu de données factice est fourni :

```bash
python -m scripts.generate_demo_data
python -m http.server -d docs 8000   # puis ouvrir http://localhost:8000
```

---

## 6. Hébergement (cf. cahier §19, objectif 0€)

- **GitHub Pages** pour le frontend statique (gratuit) — à activer dans Settings → Pages →
  "Deploy from a branch" → branche `main`, dossier **`/docs`**. Ce dossier contient à la fois
  le site (HTML/CSS/JS) et les données JSON, donc aucune configuration supplémentaire n'est
  nécessaire : chaque push (fait automatiquement par le workflow) republie le site.
- **GitHub Actions** pour le cron (gratuit dans les limites du quota mensuel gratuit — un run
  quotidien de quelques minutes, 5j/semaine, reste très en dessous des 2000 min/mois gratuites).
- **Le JSON généré est committé dans le repo** (`docs/data/briefings/`) : pas besoin de base de
  données externe, GitHub sert de stockage. C'est simple et gratuit, adapté à un seul
  utilisateur (cf. cahier §1). À reconsidérer si le volume de données devient important.

Étape d'inspection demandée par le cahier (§26) : comme il n'existait **aucun dépôt existant**
au moment de cette session (pas de repo GitHub fourni/connecté), ce projet est livré comme une
V1 autonome prête à être poussée sur un nouveau dépôt GitHub. Si un dépôt existant doit être
utilisé à la place, la prochaine IA doit d'abord : inspecter sa stack actuelle, vérifier
qu'aucun fichier ne rentre en conflit avec cette structure, puis fusionner.

---

## 7. Roadmap (ne pas faire maintenant, cf. cahier §23-24)

Par ordre de priorité si on reprend ce projet :
1. Brancher un vrai secret LLM et vérifier une génération de bout en bout sur GitHub Actions.
2. Activer GitHub Pages et vérifier l'affichage réel (mobile + desktop).
3. Affiner les sources sport (RSS spécifiques L'Équipe par sport, source NBA/Spurs dédiée).
4. Affiner le scoring (actuellement heuristique par mots-clés — pourrait être amélioré par le
   LLM lui-même en lui demandant de noter chaque item avant rédaction).
5. Ajouter des tests (pytest) sur `dedup.py`, `scoring.py`, `verification.py` — ce sont les
   modules les plus critiques pour la fiabilité (priorité n°1 du cahier).
6. Seulement ensuite : personnalisation, comptes, notifications, audio (cf. cahier §24).

---

## 8. Principes à respecter absolument en continuant ce projet

Rappel des priorités du cahier des charges (§26), dans l'ordre :
**1. Fiabilité — 2. Robustesse — 3. Qualité de sélection — 4. Qualité rédactionnelle —
5. Design — 6. Personnalisation.**

Concrètement : ne jamais inventer une information, un chiffre de marché ou une citation ;
toujours préférer ne rien afficher plutôt qu'afficher une donnée non vérifiée ; toujours garder
le dernier briefing valide visible en cas d'échec.
