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
| Mistral | open-mistral-nemo, ministral-8b-latest | 188 req/min, 625 000 tokens/min ; mois : voir console.mistral.ai/limits. mistral-small/medium/magistral = 429 (quota nul) |
| OpenRouter | openrouter/free | 50 requêtes/jour (modèles gratuits, `is_free_tier`) ; 429 « rate-limited upstream » possible sur un modèle précis |
| NVIDIA | nemotron-3.5-lightning-30b-a3b, openai/gpt-oss-20b | ~40 req/min (doc publique), pas d'en-têtes ; 410 = modèle retiré, 404 = pas activé sur le compte, 503 = surcharge passagère |

## Pièges connus
- Mistral `open-mistral-nemo` renvoie le JSON entouré de ```json … ``` : vérifier que le parseur du pipeline retire les balises.
- Groq gpt-oss : le raisonnement consomme `max_tokens` (réponse vide/tronquée) → passer `reasoning_effort` bas (la sonde le fait, pas encore le pipeline).
- Prompt « bloc » > 12000 car. chaque jour → le sport est coupé en premier (Spurs/foot absents).
- Un 429 ne doit pas être retenté dans la même minute sur le même fournisseur.

## Reste à faire (ordre suggéré)
1. Choisir le meilleur modèle Mistral autorisé (l'utilisateur a un tableau des limites par modèle : à comparer avec la sonde, viser justesse vs quota).
2. Mettre `reasoning_effort` bas côté Groq dans le pipeline ; vérifier le parseur JSON (balises ```).
3. Relancer un run réel (supprimer `docs/data/briefings/YYYY-MM-DD.json`) et lire `llm_bloc/llm_science/llm_anglais` dans l'onglet Erreurs.
4. Architecture en 2 vagues (cf. mémoire du projet) quand 3 fournisseurs tiennent.
5. Sécurité : les 2 jetons GitHub sont en clair dans les fichiers du projet Claude → les révoquer une fois fini.
