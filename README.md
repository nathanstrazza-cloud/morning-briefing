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
- Collecte marchés (Yahoo Finance) : fonctionnelle, aucune clé nécessaire (migré de Stooq
  début septembre 2026, Stooq étant devenu peu fiable).
- Déduplication (similarité de titres) : fonctionnelle.
- Scoring d'importance (heuristique mots-clés + catégorie) : fonctionnelle mais **basique**,
  à affiner (voir §7 Roadmap).
- Vérification (fait confirmé / info rapportée / incertaine, selon nombre de sources
  indépendantes qui convergent) : fonctionnelle mais heuristique simple.
- Stockage JSON par date + `latest.json` + `index.json` + `status.json` + `status_history.json`
  (historique des runs, cf. onglet Erreurs) : fonctionnel.
- Génération du briefing final (texte, citation, synthèse scientifique) : **nécessite une clé
  LLM** (voir §4). Le code essaie plusieurs fournisseurs dans l'ordre (repli automatique si le
  préféré échoue, cf. §4) et retombe sur un mode fallback qui produit un briefing minimal à
  partir des seules données brutes (sans synthèse rédigée) si aucun n'est disponible ou si tous
  échouent, pour que le pipeline ne casse jamais complètement.
- Frontend statique (HTML/CSS/JS, aucun framework, aucune dépendance de build) : fonctionnel,
  3 pages (Aujourd'hui / Archives / Erreurs) qui lisent `docs/data/briefings/*.json`.
- Workflow GitHub Actions (cron 06:30 Paris, lun-ven) : présent, à activer après premier test
  manuel (`workflow_dispatch`).

**Mise à jour du 2026-09-19 (diagnostic à distance d'un run réel du 18/09)** : la synthèse LLM
échouait systématiquement en production (Groq 413 "Payload Too Large", garde-fou de taille de
prompt du 13/09 insuffisant en pratique). Corrigé : prompt bien plus petit (JSON compact,
12 000 caractères) + `max_actualites_par_zone` (défaut 5, cf. §1 cahier), retry automatique sur
un budget encore plus petit, puis bascule vers un 2e fournisseur LLM si le premier échoue
toujours (cf. §4), et enfin `_erreur_llm`/`status_history.json` pour ne plus jamais avoir à
deviner la cause d'un échec. **Non vérifié en conditions réelles** (pas d'accès à une vraie clé
Groq/Gemini ni au workflow GitHub Actions depuis cette session) : seulement testé en local avec
des providers simulés. À confirmer après le prochain run réel — cf. `docs/erreurs.html`.

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
│   │   ├── markets.py           # indices/matières premières via Yahoo Finance (gratuit, sans clé -- migré de Stooq le 2026-09-1x)
│   │   ├── weather.py           # météo Antibes/Cannes/Valbonne/Grasse via Open-Meteo
│   │   ├── sports.py            # foot/basket/natation/autres via RSS
│   │   └── collector.py         # orchestre tous les collecteurs -> items bruts
│   ├── analyse/                 # ÉTAPE 2 : nettoie et hiérarchise
│   │   ├── dedup.py             # regroupe les articles qui parlent du même événement
│   │   ├── scoring.py           # score d'importance 0-10 par item
│   │   └── verification.py      # statut : fait confirmé / rapporté / incertain
│   ├── generation/               # ÉTAPE 3 : rédige le briefing
│   │   ├── llm_provider.py      # abstraction multi-fournisseurs LLM (Groq/Gemini/Anthropic) + repli automatique (cf. §4)
│   │   └── briefing_generator.py# construit le prompt, appelle le(s) LLM, valide le JSON produit
│   ├── stockage/                 # ÉTAPE 4 : persistance
│   │   └── storage.py            # écrit docs/data/briefings/YYYY-MM-DD.json, latest.json, index.json, status.json, status_history.json
│   └── main.py                   # orchestrateur : exécute le pipeline complet, logs, erreurs
├── logs/                         # logs d'exécution (un fichier par run)
├── docs/                         # site statique + données, servi tel quel par GitHub Pages
│   ├── index.html
│   ├── history.html
│   ├── briefing.html             # affichage d'un briefing archivé (?date=YYYY-MM-DD)
│   ├── erreurs.html              # journal des runs (succès/échec, synthèse LLM dispo ou non) -- cf. status_history.json
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
  6. filtre : on ne garde que score >= seuil (config.yaml, défaut 5), puis on plafonne à
     max_actualites_par_zone (config.yaml, défaut 5) par zone France/Monde -- cf. cahier §1
     "mieux vaut 5 infos réellement importantes que 20 secondaires" (demande explicite,
     2026-09-19) ; sections météo/citation/science ont leur propre logique, pas ce plafond
  7. generation.briefing_generator.generate(providers_LLM, events_filtrés, contexte) -> objet Briefing (dict)
     - essaie chaque provider LLM configuré dans l'ordre (préféré puis repli(s), cf. §4) avant
       de renoncer à la synthèse rédigée
     - si aucun LLM disponible ou tous ont échoué -> generation.briefing_generator.fallback_briefing() :
       briefing minimal, factuel, sans synthèse rédigée, mais jamais de contenu inventé
  8. stockage.storage.save(briefing) -> JSON du jour + latest.json + index.json + status.json + status_history.json
  9. Le frontend (statique, servi par GitHub Pages) lit ces JSON au chargement de la page.
```

**Gestion d'erreur (cf. cahier §21)** : chaque étape est encapsulée dans un `try/except` dans
`main.py`. Si une source échoue -> on continue avec les autres (log warning). Si la génération
LLM échoue -> `fallback_briefing()`. Si TOUT échoue au point de ne rien avoir de fiable -> le
script **ne touche pas** à `latest.json` (le dernier briefing valide reste affiché), et écrit
un indicateur d'échec dans `docs/data/briefings/status.json` que le frontend peut afficher
("Dernière mise à jour a échoué, vous consultez le dernier briefing valide"). L'onglet
**Erreurs** (`docs/erreurs.html`) affiche l'historique complet de ces statuts
(`status_history.json`), pas seulement le dernier run.

---

## 3bis. Déclenchement (mis à jour le 2026-09-24 — IMPORTANT, à lire avant de retoucher au cron)

**Constat mesuré via l'API GitHub (runs des 22/23/24 sept.)** : le déclencheur `schedule:`
natif de GitHub Actions arrive systématiquement avec **4 à 6h de retard** (ex. cible 06:12
Paris -> déclenchement réel vers 11h-12h), quelle que soit la minute choisie dans le cron.
C'est documenté par GitHub lui-même : l'événement `schedule` est "best-effort", retardé
(voire abandonné) pendant les périodes de forte charge, sans qu'aucune minute précise ne
soit fiable. Changer la minute du cron (essayé le 2026-09-24, `30 4/5` -> `12 4/5`) **ne
résout pas le problème** : ce n'est pas un souci de contention, c'est une limite structurelle
du déclencheur `schedule` lui-même.

**Solution retenue** : déclencher le workflow depuis l'extérieur de GitHub Actions, via
l'API REST, à l'heure exacte voulue. Un appel API (`workflow_dispatch`) initié par un
service externe démarre quasi immédiatement — il n'est pas mis en file d'attente par le
même mécanisme que `schedule`.

**Mise en œuvre (à faire par l'utilisateur, pas automatisable depuis ce dépôt)** :

1. Créer un compte gratuit sur un service de cron HTTP externe (ex. cron-job.org,
   ou tout équivalent gratuit capable d'envoyer une requête POST avec headers/corps
   personnalisés à heure fixe et fuseau Europe/Paris).
2. Créer un Personal Access Token GitHub **dédié** (scope minimal : `actions:write` /
   "Actions" en lecture-écriture sur ce dépôt uniquement) — ne pas réutiliser sans
   limite le token de développement existant dans les fichiers du projet.
3. Configurer un job HTTP quotidien (lun-ven, ~06:10 Europe/Paris) :
   - Méthode : `POST`
   - URL : `https://api.github.com/repos/nathanstrazza-cloud/morning-briefing/actions/workflows/briefing.yml/dispatches`
   - Headers : `Authorization: Bearer <TOKEN>`, `Accept: application/vnd.github+json`,
     `X-GitHub-Api-Version: 2022-11-28`
   - Corps JSON : `{"ref": "main"}`
4. Tester une fois manuellement (bouton "Test" du service cron, ou `curl` en local) et
   vérifier dans l'onglet Actions du dépôt qu'un run `workflow_dispatch` démarre en
   quelques secondes.
5. Le `schedule:` natif restant dans `briefing.yml` (07:00 UTC) n'est qu'un **filet de
   sécurité tardif** si le déclenchement externe tombe en panne un jour — le garde-fou
   d'idempotence dans `src/main.py` (`storage.day_briefing_exists`) empêche toute
   double génération, donc il est sans risque de laisser les deux actifs.

Tant que l'étape utilisateur (1-4) n'est pas faite, le site continuera à se mettre à jour
en milieu de matinée plutôt qu'à 06h30 — c'est le seul point bloquant restant pour le
critère de réussite §25.4 du cahier des charges.

---

## 4. Clé(s) API nécessaires (secrets GitHub)

Le seul point qui **nécessite un choix de l'utilisateur** est le fournisseur LLM pour la
rédaction. Sans lui, le pipeline tourne quand même (mode fallback, données brutes seulement,
pas de synthèse scientifique approfondie ni de rédaction fluide).

Options gratuites (`LLM_PROVIDER` définit le provider PRÉFÉRÉ ; configurer le secret
correspondant) :

| Fournisseur | Variable secret GitHub | Gratuit ? | Inscription | Restriction d'âge connue |
|---|---|---|---|---|
| Groq (Llama/Gemma, très rapide) | `GROQ_API_KEY` | Oui, quota gratuit généreux | Email | Aucune signalée |
| Mistral AI (La Plateforme, plan "Experiment") | `MISTRAL_API_KEY` | Oui, très généreux (1 milliard tokens/mois) | Email + vérification par SMS | 13 ans + autorisation parentale si mineur |
| Cerebras (Llama, inférence très rapide) | `CEREBRAS_API_KEY` | Oui (jusqu'à 1M tokens/jour) | Email | Aucune signalée |
| Google Gemini | `GEMINI_API_KEY` | Oui, quota gratuit | Compte Google | **Bloque les comptes mineurs** (restriction de compte Google, pas seulement l'API) |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | Payant (pas de quota gratuit permanent) | Email | Aucune signalée |

`LLM_PROVIDER` = `groq` | `mistral` | `cerebras` | `gemini` | `anthropic` (variable
d'environnement, pas un secret, définie dans `briefing.yml`).

**Recommandation V1 (objectif 0€, cf. cahier §19) : Groq, Mistral ou Cerebras**, pas
Anthropic, sauf si l'utilisateur a déjà des crédits API qu'il veut utiliser. Gemini reste
disponible mais nécessite un compte Google éligible (pas de restriction d'âge) : cf. colonne
"Restriction d'âge connue" ci-dessus.

### Repli automatique entre providers (2026-09-19, étendu le même jour)

Configurer **plusieurs** secrets à la fois (ex: `GROQ_API_KEY` ET `MISTRAL_API_KEY`) active un
repli automatique : `llm_provider.get_providers()` retourne la liste de tous les providers
dont la clé est configurée, provider préféré (`LLM_PROVIDER`) en premier. Dans
`briefing_generator.generate()`, si le provider préféré échoue deux fois (ex: Groq atteint sa
limite de tokens/minute -> 413), le pipeline essaie automatiquement le provider suivant de la
liste avant de renoncer à la synthèse rédigée. Coût : 0€ tant que chaque provider utilisé reste
sur son tier gratuit (cf. cahier §19) — aucun appel supplémentaire n'est fait si le provider
préféré réussit du premier coup. Ordre de repli par défaut (si plusieurs secrets sont
configurés et que `LLM_PROVIDER` n'en privilégie pas un autre) : Groq -> Mistral -> Cerebras
-> Gemini -> Anthropic (cf. `_DEFAULT_FALLBACK_ORDER` dans `llm_provider.py`).

Aucune autre clé n'est nécessaire : RSS, Open-Meteo et Yahoo Finance sont gratuits et sans clé.

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
3. ~~Affiner les sources sport (RSS spécifiques L'Équipe par sport, source NBA/Spurs
   dédiée).~~ Fait le 2026-09-25 (flux L'Équipe Tennis/Rugby/Cyclisme/Hand/Volley + ESPN
   NBA News, cf. `config/config.yaml`) — **pas encore vérifié en conditions réelles**
   (sandbox sans accès à ces domaines) : à confirmer via `docs/erreurs.html` /
   `status.json` → `sources_rss_en_erreur` au prochain run réel. Si un chemin L'Équipe
   échoue, ajuster uniquement le `path` dans `config.yaml` (ex. essayer `/Handball` au
   lieu de `/Hand`).
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
