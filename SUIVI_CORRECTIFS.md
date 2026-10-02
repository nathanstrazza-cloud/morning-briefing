# Suivi des correctifs de contenu (branche `dev`) — À LIRE EN PREMIER pour reprendre le travail

Source des défauts : `ANALYSE_RUN_2026-10-01.md` (9 points). Le run du 02/10/2026 06:10 les a **reproduits à
l'identique** (techniquement 7/7 parties LLM OK ; le contenu est le problème) : CAC −3,0 % (variation sur 5 jours),
science avec chiffres/sources inventés, sport hors périmètre (foot féminin), basket vide, citation `null`,
Powell/Pike en double France/Monde. Contexte d'organisation : `DEV_WORKFLOW.md` (main = prod, dev = essais).

## Règles de travail (ne pas les enfreindre)
- On développe UNIQUEMENT sur `dev`. Jamais de commit de `docs/data/` ni `logs/` sur `dev`. Ne pas lancer `LLM probe` depuis `dev`.
- Test sans quota : `pip install -r requirements.txt pytest && python3 -m pytest -q tests` (tout est simulé, aucun réseau).
- Test réel : GitHub → Actions → **Dev Test** → Run workflow (branche `dev`) ; le résultat est un artefact téléchargeable,
  rien n'est publié. Il consomme les quotas LLM (Groq 8000 tokens/min, OpenRouter 50 req/j) : pas juste avant 06h10.
- Mise en production : fusion `dev` → `main` (le jeton n'a pas le droit de créer des Pull Requests : fast-forward direct
  ou PR faite par l'utilisateur dans l'interface GitHub), seulement après un Dev Test satisfaisant et l'accord de l'utilisateur.
- Priorité du projet : fiabilité > tout. En cas de doute, ne pas afficher plutôt qu'inventer.

## État des 9 points
| # | Point | État | Où |
|---|-------|------|----|
| 1 | Science : chiffres/sources inventés | **FAIT sur dev, non testé en réel** | `src/generation/science_guard.py`, prompts `_TON_SCIENCE`/`_PLAN_ARTICLE` (parts.py), branché dans `merge_results(..., science_source=...)`, tests `tests/test_science_guard.py` |
| 2 | Marchés : variation sur 5 jours | **FAIT sur dev, non testé en réel** | `compute_session_change()` dans `src/collecte/markets.py` (close[-1] vs close[-2]), tests `tests/test_markets.py` |
| 3 | Actu : ajouts non sourcés (« ancien président », « tensions syndicales »…) | À FAIRE | prompts `_REGLES_COMMUNES`/actu dans parts.py : « faits du texte uniquement », `pourquoi_important`/`consequences` préfixés « Hypothèse : » ou null ; vérificateur léger (nombres, années, « ancien/actuel », « première fois ») |
| 4 | Doublons France/Monde | À FAIRE | `src/main.py` (dédup appelée par zone, ~l.100-154) → dédup globale inter-zones puis affectation par contenu |
| 5 | Sport hors sujet, basket absent | À FAIRE | `src/analyse/scoring.py` + `main.py` (`max_sport_total=4`) → scoring sport dédié, quota par catégorie. Décision de l'utilisateur (01/10) : si rien d'intéressant, le briefing le DIT et indique le prochain match intéressant à venir |
| 6 | Citation toujours `null` | À FAIRE | banque JSON de citations vérifiées (texte, auteur, source, année), tirage déterministe par date, sans LLM |
| 7 | Anglais du jour (niveau, « centrist ») | À FAIRE | prompt `anglais` : cibler B2/C1, exclure mots courants |
| 8 | Météo (code instantané, évolution jour) | À FAIRE | `src/collecte/weather.py` : `daily.weather_code` + `hourly`, codes WMO manquants |
| 9 | Divers (`resume_1_phrase` tronqué, CNRS, ESPN) | À FAIRE | `merge_results` (couper à la phrase entière) ; reste = bruit |

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
1) Lancer **Dev Test** une fois et contrôler : variation marchés (log), science (phrases retirées, Sources). 2) Si OK, fusionner
sur `main` après accord de l'utilisateur. 3) Enchaîner sur les points 3, 4, 5, 6 dans cet ordre.
