# Suivi des correctifs de contenu — À LIRE EN PREMIER pour reprendre le travail

> **03/10/2026 : tous les correctifs ci-dessous marqués « FAIT » ont été fusionnés dans `main` (commit 7c471ae, accord de l'utilisateur) ; `dev` a été réaligné dessus. Le premier run de production avec ce code est celui du lundi 05/10 à 06h10 : le vérifier (contenu du briefing + logs `Garde-fou`, `Marché`, `Sport:`) et corriger sur `dev` si besoin. En cas de régression grave : `git revert -m 1 7c471ae` sur `main`.**

Source des défauts : `ANALYSE_RUN_2026-10-01.md` (9 points). Le run du 02/10/2026 06:10 les a **reproduits à
l'identique** (techniquement 7/7 parties LLM OK ; le contenu est le problème) : CAC −3,0 % (variation sur 5 jours),
science avec chiffres/sources inventés, sport hors périmètre (foot féminin), basket vide, citation `null`,
Powell/Pike en double France/Monde. Contexte d'organisation : `DEV_WORKFLOW.md` (main = prod, dev = essais).

> **03/10/2026 (soir) — 4 correctifs codés sur `dev` (PAS fusionnés dans `main`)** : anglais du jour, météo, affectation France/Monde par contenu, mention « rien d'intéressant » + prochain match au sport. 95 tests OK, rien vérifié en réel à ce stade (voir tableau et « À vérifier au prochain Dev Test »).

## Règles de travail (ne pas les enfreindre)
- On développe UNIQUEMENT sur `dev`. Jamais de commit de `docs/data/` ni `logs/` sur `dev`. Ne pas lancer `LLM probe` depuis `dev`.
- Test sans quota : `pip install -r requirements.txt pytest && python3 -m pytest -q tests` (tout est simulé, aucun réseau).
- Test réel : GitHub → Actions → **Dev Test** → Run workflow (branche `dev`) ; le résultat est un artefact téléchargeable,
  rien n'est publié. Il consomme les quotas LLM (Groq 8000 tokens/min, OpenRouter 50 req/j) : pas juste avant 06h10.
- Mise en production : fusion `dev` → `main` (le jeton n'a pas le droit de créer des Pull Requests : fast-forward direct
  ou PR faite par l'utilisateur dans l'interface GitHub), seulement après un Dev Test satisfaisant et l'accord de l'utilisateur.
- Priorité du projet : fiabilité > tout. En cas de doute, ne pas afficher plutôt qu'inventer.

## État des 9 points (mis à jour le 03/10/2026 en fin de session)
| # | Point | État | Où |
|---|-------|------|----|
| 1 | Science : chiffres/sources inventés | FAIT sur dev, **validé en réel** (Dev Test 03/10 : 2 phrases retirées, Sources par le code, titres propres) | `src/generation/science_guard.py`, tests `test_science_guard.py` |
| 2 | Marchés : variation sur 5 jours | FAIT sur dev, **validé en réel** (CAC +0,79 % ; l'ancienne base `chartPreviousClose` aurait donné ≈ −2 %) | `compute_session_change()` dans `src/collecte/markets.py` |
| 2b | Marchés : explication inventée (« dépenses de défense russe » → Nasdaq) | FAIT sur dev, **validé en réel** (4e run : explications null + phrase « Aucune cause fiable… ») | `guard_marches()` dans `src/generation/actu_guard.py` : explication gardée seulement si ≥ 50 % de ses mots sont dans les articles économie ; variations imposées par les données ; sinon « Aucune cause fiable… » |
| 3 | Actu : ajouts non sourcés | FAIT sur dev (partiel) | `guard_events()` (actu_guard.py) : phrases à nombre/marqueur (« ancien », « première fois »…) absent de la source retirées ; `consequences` et `pourquoi_important` non étayés préfixés « Hypothèse : » ; statut imposé par le code. Limite : heuristique lexicale, ne détecte pas tout |
| 4 | Doublons France/Monde | FAIT sur dev, **validé en réel** (6 événements fusionnés) | `merge_zones()` dans `src/analyse/dedup.py`, appelée dans `main.py` |
| 5 | Sport hors sujet, basket absent | FAIT sur dev, **vu en réel** (Dev Test 03/10 : 4 retenus = 2 foot Bleus/Italie, 1 basket, 1 autre ; foot féminin écarté). WNBA écartée ensuite (commit suivant), à revérifier | `src/analyse/sport_scoring.py` (périmètre §6, quota par catégorie, Spurs, foot féminin écarté via `sport.inclure_feminin` absent = false). NB : bug découvert : `dedup` ne recopiait pas `equipe_prioritaire`, le bonus Spurs ne s'appliquait jamais |
| 6 | Citation toujours `null` | FAIT sur dev, **vu en réel** (Pascal, Pensées 1670) | `config/citations.json` (22 citations avec œuvre+année) + `src/generation/citations.py` ; le LLM n'écrit plus de citation |
| 7 | Anglais du jour (niveau, « centrist ») | FAIT sur dev (tests OK, **non vérifié en réel**) | `src/generation/anglais_guard.py` (filtre mots faciles/absents du texte/doublons, glossaire de traductions imposées, score de sélection B2/C1) ; prompt `SYSTEM_ANGLAIS` (parts.py) ; `select_nyt_article` choisit par vocabulaire soutenu ; tests `test_anglais_guard.py` |
| 8 | Météo (code instantané, évolution jour) | FAIT sur dev (tests OK, **non vérifié en réel**) | `src/collecte/weather.py` réécrit : prévisions horaires, périodes matin/après-midi/soir, description de la zone sur les 4 villes, alertes (rafales ≥ 60, pluie ≥ 20 mm, chaleur ≥ 35, gel), codes WMO ajoutés, code pluie sans pluie mesurée → « couvert » ; `resume` construit par le code ; frontend `renderSectionMeteo` ; tests `test_weather.py` |
| 9 | Divers (`resume_1_phrase` tronqué, CNRS, ESPN) | À FAIRE | `merge_results` (couper à la phrase entière) |
| 10 | Affectation France/Monde par contenu | FAIT sur dev (tests OK, **non vérifié en réel**) | `src/analyse/zones.py` (`assigner_zones`, appelée dans `main.py` AVANT la dédup) : marqueurs France vs étranger (titre ×2, résumé ×1), réaffectation si écart ≥ 2, sinon zone du flux ; NYT reste en Monde ; `raw` non modifié. Prompt Monde : plus de lien France obligatoire dans `pourquoi_important` ; tests `test_zones.py` |
| 11 | Sport : « rien d'intéressant » + prochain match | FAIT sur dev (tests OK, **source ESPN non vérifiée en réel**) | `src/collecte/calendrier.py` (API publique ESPN scoreboard, config `calendrier:` dans config.yaml), appelée dans `main.py` après la génération ; ajoute `sport.rien_a_signaler` et `sport.prochains_matchs` ; frontend `renderSectionSport` ; tests `test_calendrier.py` |

## Autres constats du Dev Test du 03/10 (non traités)
- La zone France contient encore de l'international (ex. budget militaire russe, Corée du Nord) : les flux « Le Monde — Une » / Libération sont classés `france` par flux, pas par contenu. Les « pourquoi important » forcent un lien avec la France (maintenant marqués « Hypothèse »). Piste : affectation par contenu, ou prompt « pourquoi important » sans obligation de lien France.
- OpenRouter renvoie « Réponse vide » / 429 sur `gemma-4-31b-it:free` à chaque run (le secours NVIDIA fonctionne, ~30 s perdues).
- Le nom du fournisseur d'une partie apparaît masqué (`actu_france=***`) dans les logs GitHub : sans conséquence.
- Faux positifs du garde-fou science : voulu (fiabilité d'abord) ; la fourchette de phrases retirées est loggée en WARNING.

## Comment lire un Dev Test depuis un environnement sans accès à blob.core.windows.net
Les logs et l'artefact d'un run sont inaccessibles dans certains sandbox (hôte bloqué). Le workflow Dev Test publie donc un
résumé en **annotations** (`scripts/test_summary.py`) : `GET /repos/{o}/{r}/check-runs/{job_id}/annotations` (titres `1-log-marches`,
`2-log-garde-fous`, `3-briefing`, `4-science`). Déclencher : `POST /repos/{o}/{r}/actions/workflows/372349191/dispatches`
avec `{"ref":"dev","inputs":{"ref":"dev","no_llm":"false"}}` (le jeton a le droit Actions). Le workflow lance maintenant `pytest`
(les tests plain-function de `tests/` ne tournaient pas sous `unittest discover`).

## Détails utiles sur les deux correctifs faits
- **Marchés** : la cause (hypothèse du 01/10) est confirmée par la lecture du code : `chartPreviousClose` de l'endpoint Yahoo
  « chart » avec `range=5d` = clôture d'avant la plage. Le log de chaque marché écrit maintenant
  `cours / ref / var / meta.chartPreviousClose / previousClose` : au prochain Dev Test, **vérifier dans le log** que la variation
  ressemble à une séance (CAC ≈ ±1 %) et que `ref` est la clôture de la veille. Un champ `date_reference` est ajouté aux cotations.
  Non vérifié contre Yahoo en réel (pas d'accès réseau depuis le sandbox de développement).
- **Science** : le garde-fou retire toute phrase contenant un nombre « significatif » (≥ 2 chiffres, décimal ou %) absent du
  titre+résumé de la source. Appliqué à l'article du 02/10 : 9 phrases retirées sur ~2000 mots (le contenu inventé : 30–55 %,
  « 10 maladies », etc.). Effets de bord connus : faux positifs rares (ex. « 24h/24 » retiré) et article plus court ; c'est voulu
  (fiabilité d'abord). Le nombre de phrases retirées est publié dans `science.phrases_retirees_garde_fou` et loggé (WARNING).
  La section « Sources » est désormais construite par le code (lien réel de l'article) ; les titres sont normalisés (`## Titre`).
  Limite de fond NON résolue : une source = un résumé RSS de quelques lignes ; l'article « approfondi » reste donc largement
  pédagogique/général. Piste (point 1e de l'analyse) : liste de sujets curés + sources primaires (Nature, CNRS, Inserm).

## Prochaine étape recommandée
1) Lire le Dev Test lancé sur le commit « citation du jour » (sport, citation, marchés, actu) ; corriger ce qui reste.
2) Si le contenu est satisfaisant : fusion `dev` → `main` **avec l'accord de l'utilisateur** (la production tourne à 06h10 en semaine).
   Avant la fusion, vérifier que `main` n'a pas de nouveaux commits « Briefing du… » en conflit (ils ne touchent que `docs/data` et `logs`).
3) Restent : point 9 (divers), puis fusion `dev` → `main` des points 7, 8, 10, 11 après vérification (accord de l'utilisateur).

## À vérifier au prochain Dev Test (points non validés en réel)
1. **Calendrier ESPN** : chercher dans les annotations les lignes `Calendrier football <slug>: N match(s)` ; si 0 partout, les `slug` de `config/config.yaml` (section `calendrier:`) ou le format du paramètre `dates=` sont à corriger. En cas d'échec le site dit seulement « Rien d'intéressant à signaler » (jamais de match inventé).
2. **Météo** : annotation `3c-meteo-anglais` → `periodes` (3 entrées), `resume` cohérent, plus de « bruine forte » sans pluie.
3. **Zones** : lignes `Zone par contenu: france -> monde | titre` ; vérifier qu'aucune réaffectation n'est absurde, ajuster `MARQUEURS_*` dans zones.py (faux positifs possibles sur les villes, ex. « Nice », « Rome »).
4. **Anglais** (nécessite un Dev Test AVEC LLM) : ligne `Anglais : N mots reçus -> M retenus`, vérifier que « centrist » → « centriste » et que les mots faciles ont disparu. Si M = 0 trop souvent, assouplir `MOTS_FACILES`.
- Un Dev Test `no_llm=true` suffit pour 1, 2 et 3 (aucun quota LLM consommé) ; seul le point 4 demande un run complet.

## Écart connu (résolu le 03/10 soir, voir point 11)
- Décision de l'utilisateur du 01/10 : quand le sport n'a rien d'intéressant, le briefing le dit et indique le prochain match intéressant → codé (point 11).
- Marchés : quand aucune cause fiable n'est trouvée, le site affiche « Aucune cause fiable n'a pu être établie… » (volontaire, cahier §5 : ne pas inventer). Pour avoir plus d'explications il faudrait enrichir le contexte économie (plus de flux/articles), pas assouplir le garde-fou.
- Quotas LLM : le Dev Test consomme les mêmes clés que la prod. 4 runs complets ont été faits le 03/10 (samedi) ; ne pas en relancer inutilement.
