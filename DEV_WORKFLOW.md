# Organisation `main` / `dev` et système de test

Document de relais (humain ou IA). Source : cahier « Organisation main - dev et système de test ».
Principe : **`main` produit, `dev` expérimente. Aucun test de `dev` ne modifie la production.**

## 1. Rôle des branches
| Branche | Contenu | Utilisée par |
|---|---|---|
| `main` | code validé + données publiées (`docs/data/briefings/`) + logs de production | GitHub Pages (dossier `/docs`), cron externe 06h10 (cron-job.org → `workflow_dispatch` sur `main`), filet `schedule` 07:00 UTC, workflow `Morning Briefing` |
| `dev` | nouvelles fonctionnalités, corrections, essais | workflow manuel `Dev Test` uniquement |

Flux : `dev` → test manuel → Pull Request → `main`. **Ne jamais développer directement sur `main`.**
Exception tolérée : le bot écrit chaque matin sur `main` (`docs/data/`, `logs/`), pas de protection de branche imposant une PR pour l'instant (cahier §11).

## 2. Règles impératives
1. **Ne jamais committer sur `dev`** de fichiers sous `docs/data/` ni `logs/` (les données de production vivent uniquement sur `main`, sinon les deux historiques divergent). Une PR `dev → main` ne doit donc contenir que du code/doc/config/tests. Vérifier `git diff --stat main...dev` avant de fusionner.
2. Ne pas lancer le workflow `LLM probe` depuis `dev` (il committerait `logs/llm_probe.*` sur `dev`).
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
4. Si OK : Pull Request `dev → main`, relecture, fusion.
5. Après fusion, ré-aligner `dev` : `git checkout dev && git merge main` (récupère aussi les données du bot ; ne pas les modifier).

Test local équivalent : `TEST_MODE=true BRIEFING_OUTPUT_DIR=test-output BRIEFING_LOGS_DIR=test-output/logs python -m src.main [--no-llm]` (copier d'abord `docs/data/briefings/.` dans `test-output/` pour avoir l'historique). `test-output/` et `preview-site/` sont ignorés par git.

## 5. Particularités GitHub à connaître
- Un workflow `workflow_dispatch` n'apparaît dans l'interface que s'il existe sur la branche par défaut (`main`) : c'est pourquoi `dev-test.yml` a été fusionné sur `main` en premier (mise en place minimale, comportement de production inchangé).
- Le `schedule` ne s'exécute que sur la branche par défaut : `dev` ne déclenche donc rien automatiquement.
- Le workflow de production (`briefing.yml`, groupe `morning-briefing`) n'a pas été modifié.

## 6. Reste à faire / idées (non faites)
- Protection de `main` (PR obligatoire) : plus tard, quand le bot n'écrira plus directement sur `main` (cahier §11).
- Éventuel garde-fou CI sur les PR : échouer si la PR touche `docs/data/briefings/` ou `logs/`.
- Travail de fond à mener désormais sur `dev` : correctifs de contenu listés dans `ANALYSE_RUN_2026-10-01.md` (science, marchés, doublons, sport, citation…), module mémoire/personnalisation, approfondissement à la demande (cahiers du projet). Contexte LLM : `HANDOFF_LLM.md`.
