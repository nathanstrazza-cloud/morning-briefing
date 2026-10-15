# CONTEXT.md — SEUL fichier à lire pour reprendre le projet

> Une IA qui reprend ce projet lit **uniquement ce fichier**. `README.md` (description/lancement), `OPERATIONS.md` (cron, dev/main) et `archives/`
> (historique) ne se lisent que sur besoin explicite. `cahier_des_charges.md` = intentions du départ, **indicatives, modifiables** (le code y renvoie par « cahier §N »).
> Mis à jour le 15/10/2026. Dépôt : github.com/nathanstrazza-cloud/morning-briefing (public). Langue du projet : français.

## 1. État courant
Site personnel de veille quotidienne (lun-ven, run ~06h10 Paris) : collecte RSS/marchés/météo/sport → dédup/scoring/vérification → rédaction LLM par parties
avec garde-fous codés → JSON → site statique GitHub Pages (`docs/`). **Pipeline complet, en production, stable** (6-7/7 parties LLM rédigées par run, ~5 min).
Sections : Actualité France/Monde, Marchés, Sport (tous sports + prochaines affiches), Science (découverte qualifiée **suivie d'un dossier approfondi** ~1300 mots ; sinon dossier seul, à partir d'un
extrait Wikipédia), Anglais du jour (passage littéraire domaine public, traductions en ligne, sans LLM), Météo (Antibes/Cannes/Valbonne/Grasse), Citation (banque vérifiée).
Déclenchement : cron externe cron-job.org (`workflow_dispatch` sur `main`), le `schedule` natif n'est qu'un filet tardif (retards 4-6 h). Détails : `OPERATIONS.md`.
Dernier changement : 15/10 science — le mode « découverte » ne faisait que 160-295 mots (4 runs sur 12, les 3 derniers jours) : une découverte est désormais TOUJOURS suivie d'un dossier
approfondi sur un sujet encyclopédique (`briefing_generator.ajouter_approfondissement`, parties LLM `science_d` = découverte, `science_a/b` = dossier, fusion `parts._merge_science_decouverte_approfondi`,
un seul article : titre de la découverte + « ## Pour aller plus loin : <sujet> »). Champs publiés : `nb_mots`, `nb_mots_decouverte`, `nb_mots_approfondi`. Fait sur `dev` (212 tests).
Run du 15/10 (1re rotation/réorganisation) : OK, sport très positif (8 éléments + affiches, jugé par l'utilisateur), science = 213 mots (cause ci-dessus).
**À contrôler au prochain run après fusion** : `science.nb_mots` ≥ 1000 même en mode découverte (`nb_mots_approfondi` ≥ 900) ; rotation (`docs/data/briefings/archives/`, `index.json` ≤ 30 dates) ; artefact `logs-<run>` ; aucun `logs/*.log` committé.
Limite connue : le sujet d'approfondissement est tiré de la liste curée (`config/science_sujets.json`) et n'est PAS relié à la découverte du jour (piste : choisir le sujet le plus proche par mots-clés).

## 2. Règles de travail (ne pas enfreindre)
1. Développer UNIQUEMENT sur `dev` ; `main` = production (le bot y committe `docs/data/` chaque matin). Ne jamais committer `docs/data/` depuis `dev`. Après une fusion, réaligner `dev` sur `main`.
2. Tests sans réseau ni quota : `pip install -r requirements.txt pytest && python3 -m pytest -q tests` (212 tests, tout est simulé). Le sandbox de dev n'a PAS accès à Groq/Mistral/NVIDIA/flux RSS/blob Azure (seulement github.com / api.github.com).
3. Test réel : Actions → **Dev Test** (manuel, rien n'est publié ni committé) ; consomme les quotas LLM : pas entre 05h45 et 06h45 en semaine. Lecture sans accès à l'artefact : annotations (cf. `OPERATIONS.md` §C).
4. Mise en production = fusion `dev` → `main` après un Dev Test satisfaisant ET l'accord de l'utilisateur ; retour arrière par `git revert -m 1 <fusion>`. Forcer un re-run le même jour = supprimer `docs/data/briefings/AAAA-MM-JJ.json` (idempotence `day_briefing_exists`).
5. **Fiabilité > tout** : ne jamais inventer un fait, un chiffre, un nom ou une citation ; en cas de doute ne pas afficher. Aucune clé/jeton dans le dépôt (GitHub Secrets). Coût visé 0 €.
Décisions de l'utilisateur à respecter : `pourquoi_important`/`conséquences` restent vides s'ils ne sont pas étayés par la source ; le site ne dépend d'aucune préférence figée (pas de Spurs/équipe de France forcés) ; sport faible = on le dit + prochaine affiche.

## 3. Défauts connus NON résolus (à corriger — par priorité indicative)
| # | Défaut | Piste |
|---|---|---|
| 1 | Actualité : choix éditorial perfectible (items faibles retenus, faits importants écartés) ; l'utilisateur doit donner ses instructions avant tout travail | attendre ses consignes ; la fusion de doublons garde le titre le plus long (peut garder un titre d'explicateur) |
| 2 | Science : dossier approfondi (et mode approfondi seul) fondé sur un extrait Wikipédia (source non primaire) ; garde-fou à faux positifs ; n'attrape pas les affirmations fausses en mots courants | sources primaires (Nature/CNRS/Inserm) ; liste de sujets curés (`config/science_sujets.json`, 36) |
| 3 | Mistral rend ~5 événements Monde sur 8 fournis | contourné : le code complète depuis les sources (`actu_guard.completer_manquants`) ; cause non traitée |
| 4 | Doublon inter-zones (ex. Palestine : 1 seule entité commune) et affectation France/Monde encore imparfaite | `analyse/diversite.py`, `analyse/zones.py` |
| 5 | Marchés : explication tolérée avec 1 seul article (ex. Brent/gazole : lien faible) | durcir `guard_marches` |
| 6 | Sport : pas de contrôle automatique des scores cités par le LLM ; titres anglais non traduits écartés ; une affiche (ex. Lens-Lyon) peut sortir si le plafond (8) est saturé | `analyse/sport_scoring.py`, `parts.py::_sport_prompt` |
| 7 | Flux en échec/vides : CNRS « invalid token » (3 correctifs sans effet), ESPN NBA/Top Headlines, L'Équipe Hand/Volley (parfois normal), France 24 SSL | décider : corriger ou retirer de `config/config.yaml` |
| 8 | OpenRouter : 429 amont / réponse vide à chaque run (le secours fonctionne, ~30 s perdues) ; « groq » masqué `***` dans les logs Actions (sans conséquence) | OpenRouter déjà en dernier secours |
| 9 | Lundi : fenêtre « depuis vendredi 18h » redondante, pas de dédup inter-jours (reprises possibles du week-end) ; aucun garde-fou `weekday() >= 5` dans `main.py` (si le job cron-job.org tourne le week-end, le run a lieu) | proposable : garde-fou jour ouvré |
| 10 | Anglais : 9 passages de `config/anglais_textes.json` écrits de mémoire → à relire contre Project Gutenberg ; mode « actualité » non fait | piste Wikinews (CC BY) ; textes NYT protégés |

## 4. Architecture (une ligne par module ; chaque fichier de `src/` commence par une docstring qui détaille)
Pipeline (`src/main.py`) : fenêtre (lundi élargi) → `collecte` → zones → dédup → scoring → vérification → diversité → `generation` (LLM par parties + garde-fous) → `stockage` → site.
- `src/main.py` orchestre ; `src/utils.py` config/logs/fenêtre. `config/config.yaml` = sources RSS, seuils, plafonds (actu France 5 / Monde 8, sport 8 dont 3 par sport (clés `max_actualites_france/monde`, `max_sport_total`, `max_par_sport`)), météo, marchés, calendrier.
- `collecte/` : `rss_sources` (flux RSS) · `markets` (Yahoo Finance, variation sur une séance) · `weather` (Open-Meteo, matin/après-midi/soir, alertes) · `sports` (flux sport généralistes) · `calendrier` (ESPN : prochaines affiches) · `encyclopedie` (extraits Wikipédia pour la science approfondie, rotation sans répétition sur 45 jours) · `collector` (orchestrateur).
- `analyse/` : `dedup` (même événement → 1 + sources ; fusion inter-zones) · `scoring` (importance 0-10, mots entiers, malus tribune/liste/entretien) · `verification` (fait confirmé / rapporté / incertain) · `zones` (France/Monde par contenu) · `diversite` (max 2 par sujet, fusion par entités rares) · `titres` (nettoyage) · `sport_scoring` / `sport_news` (sport hors flux dédiés) · `science_events` (fusion FR/EN d'un même événement science).
- `generation/` : `briefing_generator` (assemblage, mode science découverte/approfondi, repli sans LLM) · `parts.py` (prompts + parties LLM) · `llm_orchestrator` (plan, secours en chaîne) · `llm_provider` (Groq/Mistral/NVIDIA/OpenRouter/Cerebras/Gemini/Anthropic) · `actu_guard` / `science_guard` / `anglais_guard` (garde-fous appliqués par le CODE après le LLM : nombres, noms propres, sources) · `citations` (banque `config/citations.json`) · `anglais_litteraire` · `sport_format`.
- `stockage/storage.py` : JSON du jour, `latest/index/status/status_history`, rotation (30 publiés, reste dans `archives/`).
- `docs/` = site statique servi par Pages (`index/history/briefing/erreurs.html`, `app.js`, `style.css`) + `docs/data/briefings/` (données publiques ; **jamais de donnée privée**).
- `tests/` (212) · `scripts/` (`llm_probe.py` sonde des quotas, `test_summary.py` annotations Dev Test, `generate_demo_data.py`) · `.github/workflows/` : `briefing.yml` (prod), `dev-test.yml` (manuel), `llm-probe.yml` (manuel, artefact).

## 5. LLM (le plan réel est dans `config/llm_plan.yaml`, modifiable sans code)
Secrets GitHub : `GROQ_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY` (+ `LLM_PROVIDER`, `CEREBRAS_API_KEY` inutilisé). Pas de Gemini/Anthropic (payant ou non éligible).
Parties : appel 1 = actu_france Groq, actu_monde Mistral, puis marchés NVIDIA ; appel 2 (150 s plus tard) = science_a Mistral, science_b Groq, sport NVIDIA puis science_d (découverte courte) NVIDIA ; OpenRouter en dernier secours partout (la partie `anglais` du plan est inactive : l'anglais littéraire n'utilise plus de LLM). Un fournisseur qui échoue → suivant de la liste ; échec total d'une partie → repli codé (jamais de contenu inventé).
Limites mesurées (gratuites) : Groq 8000 tokens/min et ~1000 req/j (`openai/gpt-oss-120b`) ; Mistral `ministral-14b-2512` 30 req/min (small/medium/magistral bloqués en 429, large = 403) ; NVIDIA ~40 req/min (`openai/gpt-oss-20b`) ; OpenRouter ~50 req/j. Un 429 n'est jamais retenté sur le même fournisseur. Les noms de modèles gratuits changent sans préavis : relancer `LLM probe` si une erreur 404/410 apparaît. Surcharge : variables `GROQ_MODEL`, `MISTRAL_MODEL`, `NVIDIA_MODEL`, `OPENROUTER_MODEL`.

## 6. Organisation du dépôt (réorganisation du 14/10/2026, objectif : réduire le contexte lu par session ~140 Ko → ~15 Ko)
`archives/` = historique (ne pas lire) · `logs/` non versionné (artefact Actions `logs-<run>`, 90 j) · briefings : 30 derniers publiés, le reste dans `docs/data/briefings/archives/` · `status_history.json` plafonné à 50. Le dossier d'archives est à la racine (et non `docs/`) car `docs/` est entièrement publié par Pages.

## 7. Chantiers futurs (non commencés — cahiers du projet Claude, indicatifs)
- **Mémoire/personnalisation** : formule de classement S = a·I + b·N + c·A − d·R, mémoire de préférences/historique/retours. Attention : le dépôt et Pages sont PUBLICS → la mémoire personnelle ne peut pas y vivre (stockage privé séparé : autre dépôt privé, Gist secret, cache Actions) ; les retours « Intéressant / Déjà vu » exigent un petit backend. Proposition : commencer par la seule dédup inter-jours (point 9), sans retours utilisateur.
- **Approfondissement à la demande** (niveau 2 : dossier généré au clic) : exige un service serverless sécurisé + cache ; ne pas toucher avant demande explicite.
- Jeton GitHub de développement : expire le 2026-11-30 ; il a circulé en clair dans les fichiers du projet Claude → à régénérer (fine-grained, ce dépôt, Contents + Actions + Pull requests). Le jeton de cron-job.org est un autre jeton dédié.
