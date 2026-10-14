# OPERATIONS — à lire SEULEMENT si le cron casse, pour tester sur `dev` ou pour fusionner

Contenu : (A) organisation `main`/`dev` et Dev Test ; (B) déclenchement et dépannage cron-job.org ; (C) lire un Dev Test sans accès à l'artefact ; (D) rotation des données et logs.

# (A) Organisation `main` / `dev` et système de test

Document de relais (humain ou IA). Source : cahier « Organisation main - dev et système de test ».
Principe : **`main` produit, `dev` expérimente. Aucun test de `dev` ne modifie la production.**

## 1. Rôle des branches
| Branche | Contenu | Utilisée par |
|---|---|---|
| `main` | code validé + données publiées (`docs/data/briefings/`) + logs de production | GitHub Pages (dossier `/docs`), cron externe 06h10 (cron-job.org → `workflow_dispatch` sur `main`), filet `schedule` 07:00 UTC, workflow `Morning Briefing` |
| `dev` | nouvelles fonctionnalités, corrections, essais | workflow manuel `Dev Test` uniquement |

Flux : `dev` → test manuel → Pull Request → `main`. **Ne jamais développer directement sur `main`.**
Exception tolérée : le bot écrit chaque matin sur `main` (`docs/data/`), pas de protection de branche imposant une PR pour l'instant (cahier §11).

## 2. Règles impératives
1. **Ne jamais committer sur `dev`** de fichiers sous `docs/data/` ni `logs/` (les données de production vivent uniquement sur `main`, sinon les deux historiques divergent). Une PR `dev → main` ne doit donc contenir que du code/doc/config/tests. Vérifier `git diff --stat main...dev` avant de fusionner.
2. Le workflow `LLM probe` ne committe plus rien (résultat en artefact) : il peut être lancé sans risque.
3. Les tests utilisent **les mêmes clés API** que la production (quotas Groq/Mistral/NVIDIA/OpenRouter). Pas de test complet inutile ; pas entre 05h45 et 06h45 Paris en semaine (le workflow le bloque sauf `force_near_prod`). Tester la mécanique sans quota : `no_llm` coché, ou tests unitaires.
4. Aucun secret dans le dépôt (les jetons GitHub ont été fournis en clair dans les fichiers du projet Claude : **à révoquer/régénérer** une fois le travail fini).

## 3. Ce qui est en place
- `src/stockage/storage.py` : `resolve_data_dir()` — dossier de sortie = `BRIEFING_OUTPUT_DIR` si défini (relatif = depuis la racine du dépôt), sinon `docs/data/briefings` (production, **inchangé**). Garde-fou : `TEST_MODE=true` + dossier de production ⇒ `RuntimeError`.
- `src/utils.py` : `is_test_mode()` (`TEST_MODE`), `resolve_logs_dir()` (`BRIEFING_LOGS_DIR`, défaut `logs/`).
- `src/main.py` : en `TEST_MODE=true`, le garde-fou d'idempotence (`day_briefing_exists`) et le garde-fou « avant 06h » sont ignorés → le briefing du jour peut être régénéré. En production (`TEST_MODE` absent) : comportement identique à avant.
- Un briefing produit en test porte `"test_mode": true` dans son enveloppe JSON.
- `.github/workflows/dev-test.yml` : manuel uniquement, `permissions: contents: read`, groupe de concurrence propre `dev-test`, checkout du code (`ref`, défaut `dev`) + checkout **sparse en lecture seule** de `main:docs/data/briefings` copié dans `test-output/` (contexte/historique), tests unitaires, exécution du bot, artefact `dev-test-<n>` (`test-output/` = JSON + `logs/`, `preview-site/` = frontend + données de test). **Aucun commit, aucun push, aucune publication Pages.**
- Tests : `tests/test_storage_config.py` (sans réseau) en plus de `tests/test_llm_orchestrator.py` : `python -m unittest discover -s tests -v`.

## 4. Utilisation
1. `git checkout dev && git pull`, développer, commit/push sur `dev`.
2. GitHub → Actions → **Dev Test** → Run workflow (branche : `main` dans le menu, input `ref` = `dev`). Options : `no_llm`, `force_near_prod`.
3. Télécharger l'artefact (rétention 14 j), consulter `test-output/latest.json` et `test-output/logs/`. Aperçu du site : `cd preview-site && python3 -m http.server` puis http://localhost:8000.
4. Si OK : Fusion `dev → main` (le jeton a maintenant le droit de créer des PR ; un fast-forward / merge direct reste toléré).
5. Après fusion, ré-aligner `dev` : `git checkout dev && git merge main` (récupère aussi les données du bot ; ne pas les modifier).

Test local équivalent : `TEST_MODE=true BRIEFING_OUTPUT_DIR=test-output BRIEFING_LOGS_DIR=test-output/logs python -m src.main [--no-llm]` (copier d'abord `docs/data/briefings/.` dans `test-output/` pour avoir l'historique). `test-output/` et `preview-site/` sont ignorés par git.

## 5. Particularités GitHub à connaître
- Un workflow `workflow_dispatch` n'apparaît dans l'interface que s'il existe sur la branche par défaut (`main`) : c'est pourquoi `dev-test.yml` a été fusionné sur `main` en premier (mise en place minimale, comportement de production inchangé).
- Le `schedule` ne s'exécute que sur la branche par défaut : `dev` ne déclenche donc rien automatiquement.
- Le workflow de production (`briefing.yml`, groupe `morning-briefing`) n'a pas été modifié.

## 6. Reste à faire / idées (non faites)
- Protection de `main` (PR obligatoire) : plus tard, quand le bot n'écrira plus directement sur `main` (cahier §11).
- Éventuel garde-fou CI sur les PR : échouer si la PR touche `docs/data/briefings/` ou `logs/`.
- Travail de fond à mener désormais sur `dev` : défauts listés dans `CONTEXT.md`, module mémoire/personnalisation, approfondissement à la demande (cahiers du projet). Contexte LLM : `CONTEXT.md` (§ LLM).


---

# (B) Déclenchement et dépannage cron-job.org

## B1. Déclenchement (mis à jour le 2026-09-24 — IMPORTANT, à lire avant de retoucher au cron)

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


## B2. Dépannage du déclenchement cron-job.org (ajouté le 2026-09-28)

**Symptôme** : aucun run `workflow_dispatch` à ~06h10 Paris (constaté lun. 28/09 : plus aucun
run externe depuis ven. 25/09). Le job cron-job.org envoie un `POST` avec un jeton GitHub dans
l'en-tête `Authorization`. Cause la plus probable : **le jeton collé dans le job a été
révoqué/renouvelé** (l'ancien jeton "fin le 20/10" renvoie désormais 401 Bad credentials).

**Correction (côté cron-job.org, non automatisable depuis ce dépôt)** :
1. cron-job.org -> le job -> onglet *History* : lire le code HTTP de la dernière exécution
   (401 = jeton invalide ; 403/404 = jeton sans droit `Actions: Read and write` sur ce dépôt ;
   204 = succès, le run doit apparaître dans l'onglet Actions).
2. Créer un jeton GitHub **dédié** (fine-grained, uniquement ce dépôt, permission
   *Actions: Read and write*), le coller dans l'en-tête `Authorization: Bearer <jeton>`.
3. Vérifier : fuseau du job = Europe/Paris, jours lun-ven, heure ~06:10, corps `{"ref":"main"}`,
   en-têtes `Accept: application/vnd.github+json` et `X-GitHub-Api-Version: 2022-11-28`.
4. Bouton *Test run* : réponse attendue **204**, puis run visible dans Actions. (L'idempotence
   `day_briefing_exists` empêche une double génération le même jour.)
5. Activer dans cron-job.org l'alerte e-mail en cas d'échec du job.
**Ne jamais** committer ni coller un jeton dans un fichier du dépôt ou du projet partagé.


# (C) Lire un Dev Test depuis un environnement sans accès à blob.core.windows.net
Les logs et l'artefact d'un run sont inaccessibles dans certains sandbox (hôte bloqué). Le workflow Dev Test publie donc un
résumé en **annotations** (`scripts/test_summary.py`) : `GET /repos/{o}/{r}/check-runs/{job_id}/annotations` (titres `1-log-marches`,
`2-log-garde-fous`, `3-briefing`, `4-science`). Déclencher : `POST /repos/{o}/{r}/actions/workflows/372349191/dispatches`
avec `{"ref":"dev","inputs":{"ref":"dev","no_llm":"false"}}` (le jeton a le droit Actions). Le workflow lance aussi `pytest`.
Aperçu local de l'artefact : le décompresser, puis `cd preview-site && python3 -m http.server 8001` et ouvrir http://localhost:8001.

# (D) Rotation des données et logs (réorganisation du 14/10/2026)
- **Logs** : `logs/` n'est plus versionné (`.gitignore`). Chaque run de production les publie en **artefact GitHub Actions** `logs-<date>-<run>`
  (rétention 90 jours) : Actions → run → Artifacts. Le dossier reste présent grâce à `logs/.gitkeep`.
- **Briefings** : `docs/data/briefings/` garde les 30 derniers briefings (+ `latest/index/status/status_history`). Les plus anciens sont déplacés
  par `storage.rotate_briefings()` vers `docs/data/briefings/archives/` (non listés dans l'historique du site, mais conservés : cahier §16
  « ne pas supprimer » respecté ; `encyclopedie.sujets_deja_utilises` les lit encore pour la rotation des sujets de science).
- `status_history.json` est plafonné à 50 entrées (`MAX_STATUS_HISTORY`).
