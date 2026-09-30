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
| OpenRouter | openrouter/free | 50 requêtes/jour (modèles gratuits, `is_free_tier`) ; 429 « rate-limited upstream » possible sur un modèle précis |
| NVIDIA | nemotron-3.5-lightning-30b-a3b, openai/gpt-oss-20b | ~40 req/min (doc publique), pas d'en-têtes ; 410 = modèle retiré, 404 = pas activé sur le compte, 503 = surcharge passagère |

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

## Reste à faire
1. **Valider en réel** : un vrai run (supprimer docs/data/briefings/AAAA-MM-JJ.json du jour puis lancer le workflow « Morning Briefing »),
   lire `_parts` dans le JSON / l'onglet Erreurs. Le run dure ~6 min (pause de 150 s entre les 2 appels ; `LLM_WAVE_GAP_SECONDS=0` pour tester vite).
2. Vérifier la qualité : citation (Groq), moitiés de science cohérentes entre elles, JSON de ministral-14b.
3. Si un fournisseur est trop faible sur sa partie, changer l'ordre dans config/llm_plan.yaml (aucun code).
4. Supprimer le code mort (cf. ci-dessus) et le secret LLM_PROVIDER devenu inutile.
5. Sécurité : les 2 jetons GitHub sont en clair dans les fichiers du projet Claude → les révoquer une fois fini.
