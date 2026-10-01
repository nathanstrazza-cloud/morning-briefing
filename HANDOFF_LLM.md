# HANDOFF — fournisseurs LLM (état au 29/09/2026 soir)

Document pour une autre IA / une future session. Lire aussi `README.md` et `src/generation/llm_provider.py`.

## Ce qui a été fait
- `scripts/llm_probe.py` + workflow manuel `.github/workflows/llm-probe.yml` ("LLM probe", Actions > Run workflow) :
  requête à 1 token sur les 4 fournisseurs, test « utilisable » (JSON, 400 tokens), relevé des limites.
  Résultat commité dans `logs/llm_probe.txt` et `logs/llm_probe.json` (aucune clé dedans). Le sandbox de Claude ne
  peut PAS joindre ces API : on lance la sonde via GitHub et on lit `logs/llm_probe.json`.
- Défauts corrigés dans `llm_provider.py` : Mistral `open-mistral-nemo`, NVIDIA `nvidia/nemotron-3.5-lightning-30b-a3b`,
  OpenRouter `openrouter/free` en tête. Variables d'env vides ne masquent plus le défaut (`or` au lieu de `get(..., défaut)`).

## Résultats de la sonde (29/09/2026) — les 4 répondent
| Fournisseur | Modèle OK | Limites relevées |
|---|---|---|
| Groq | openai/gpt-oss-120b | 1000 requêtes/jour, 8000 tokens/MINUTE (le vrai goulot) |
| Mistral | **ministral-14b-2512 (choisi)**, ministral-8b-2512, open-mistral-nemo | 14b : 30 req/min, 937 500 tokens/min ; 8b/nemo : 188 req/min, 625 000 tokens/min ; mois : console.mistral.ai/limits. mistral-small/medium/magistral = 429 (0 req/min réel malgré 20 000 tokens/min affichés au tableau) ; mistral-large-2512 = 403 (palier d'abonnement) |
| OpenRouter | google/gemma-4-31b-it:free (défaut) ; `openrouter/free` = routeur automatique NON FIABLE (a renvoyé un modèle de modération et des raisonnements) | 50 requêtes/jour (modèles gratuits, `is_free_tier`) ; 429 « rate-limited upstream » possible sur un modèle précis |
| NVIDIA | **openai/gpt-oss-20b (défaut depuis le 30/09)** ; nemotron-3.5-lightning répond à 1 token mais écrit son raisonnement au lieu du JSON | ~40 req/min (doc publique), pas d'en-têtes ; 410 = modèle retiré, 404 = pas activé sur le compte, 503 = surcharge passagère |

## Pièges connus
- Mistral (ministral / nemo) renvoie le JSON entouré de ```json … ``` : vérifier que le parseur du pipeline retire les balises.
- Groq gpt-oss : le raisonnement consomme `max_tokens` (réponse vide/tronquée) → passer `reasoning_effort` bas (la sonde le fait, pas encore le pipeline).
- Prompt « bloc » > 12000 car. chaque jour → le sport est coupé en premier (Spurs/foot absents).
- Un 429 ne doit pas être retenté dans la même minute sur le même fournisseur.

## Nouvelle architecture de génération (codée le 30/09/2026, testée avec de faux fournisseurs, PAS encore en réel)
Décidée avec l'utilisateur : critères = qualité de rédaction + volume de chaque partie. 8 parties, 4 fournisseurs, 2 appels.

| Appel | Étape | Partie (principal) | Secours dans l'ordre |
|---|---|---|---|
| 1 (T+0) | actualité | actu_france + citation (groq), actu_monde (mistral) | nvidia, openrouter, puis dernier recours |
| 1 | marchés/anglais (APRÈS l'étape actualité) | marches (nvidia), anglais (openrouter) | l'autre du couple, puis dernier recours |
| 2 (+150 s après la fin de l'appel 1) | science/sport | science_a (mistral), science_b (groq), sport (openrouter) | nvidia = secours de la science (sport seulement s'il est libre) |

Règles voulues par l'utilisateur : si un fournisseur d'actualité échoue, le secours (nvidia pour la France, openrouter pour le monde)
passe AVANT de traiter marchés/anglais ; en appel 2, le fournisseur inutilisé (nvidia) est le secours de la science.
Science = 2 moitiés du même article : A = sections 1-4 (intro, importance, phénomène, mécanismes), B = sections 5-10 (données,
connu, incertain, limites, conclusion, sources). En mode « découverte » : un seul appel (science_a), pas de science_b.
Si A échoue partout, on garde le contenu brut (jamais B seule) ; si B échoue, A est publiée avec une mention explicite.

Fichiers : `config/llm_plan.yaml` (le plan : modifier ici pour réassigner, sans code), `src/generation/llm_orchestrator.py`
(moteur générique : parallélisme entre fournisseurs, secours en chaîne, 429 non retenté, JSON tolérant),
`src/generation/parts.py` (prompts/schémas/fusion des 8 parties), `briefing_generator.generate(pool, ...)`,
`llm_provider.get_provider_pool()`, tests : `python -m unittest discover -s tests -v` (21 tests, sans réseau).
Diagnostic : `_parts` (détail par partie) + `_bloc/_science/_anglais` (compatibilité onglet Erreurs). `resume_1_phrase` est
maintenant construit à partir des titres publiés (plus de LLM). Anciennes fonctions (`_run_chain`, `get_providers(role)`,
`_build_user_prompt_*`) conservées mais inutilisées : à supprimer après validation en réel.

## Leçons du vrai run du 30/09 (2 runs) — déjà corrigées dans le code
- Un test « 1 token » NE SUFFIT PAS : il faut un vrai run. Le run a révélé : NVIDIA nemotron-3.5-lightning et OpenRouter `openrouter/free`
  écrivent leur raisonnement (« Here's a thinking process… ») ou une sortie de modération au lieu du JSON ; Mistral casse le JSON dès qu'un long
  article markdown est dedans (guillemets, retours ligne).
- Corrections : (1) la science est demandée en TEXTE markdown (ligne `TITRE: …` puis sections), plus en JSON ; (2) `parse_json_text` tolère
  retours ligne bruts, `+1.2`, NaN ; (3) une réponse qui commence par du raisonnement est rejetée (`looks_like_leak`) ; (4) on ne réessaie avec
  un prompt plus petit que sur 400/413/422 — sinon on passe directement au fournisseur suivant (avant : run de 14 min) ; (5) clé `marches`
  normalisée pour le site (`mouvements_notables`) ; (6) résumé « à la une » dédoublonné ; (7) NVIDIA timeout 150 s ; (8) modèles NVIDIA/OpenRouter nommés.
- Résultat du run 2 (avant ces corrections) : 7/7 parties rédigées, mais via beaucoup de secours ; durée ~14 min.

## Résultat du run de validation (30/09, 3e run, code corrigé) : 7/7 parties rédigées en ~5 min
actu_france=groq, actu_monde=mistral, science_a=mistral, science_b=groq (article de 1 841 mots, sections 1 à 10 cohérentes),
marches=mistral (après échecs NVIDIA « réponse vide » + OpenRouter 429), anglais=nvidia, sport=nvidia (secours d'OpenRouter en 429).
Points encore faibles : (1) OpenRouter : « temporarily rate-limited upstream » (pool partagé Google AI Studio) sur les modèles gratuits
-> ne pas compter dessus (le secours fonctionne) ; (2) NVIDIA gpt-oss-20b renvoyait parfois une réponse vide (le raisonnement mange
max_tokens) -> max_tokens doublé pour gpt-oss (à confirmer au prochain run) ; (3) citation = null (normal si non certaine) ;
(4) les titres de la moitié A de science sont en gras (`## **1. …**`), ceux de la B non : cosmétique, à harmoniser côté prompt si gênant.

## Reste à faire
1. Vérifier le prochain run planifié (`_parts` dans le JSON du jour + journal `logs/`).
2. Si OpenRouter continue d'échouer en 429, le remplacer par un autre rôle/fournisseur dans config/llm_plan.yaml (aucun code).
3. Supprimer le code mort (`_run_chain`, `get_providers(role)`, `_build_user_prompt_*`) et le secret LLM_PROVIDER devenu inutile.
4. Sécurité : les 2 jetons GitHub sont en clair dans les fichiers du projet Claude → les révoquer une fois fini.


## Analyse du run du 01/10/2026
Voir `ANALYSE_RUN_2026-10-01.md` : erreurs de contenu restantes (science inventée, variations de marché, doublons, sport, citation…), causes et correctifs priorisés.


## Organisation main / dev
Voir `DEV_WORKFLOW.md` : développement sur la branche `dev`, tests via le workflow manuel `Dev Test` (artefact, sans toucher à la production).
