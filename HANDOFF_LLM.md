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

## Reste à faire (ordre suggéré)
1. (FAIT 30/09) Modèle Mistral choisi : ministral-14b-2512. Ne pas se fier au tableau de la console seul : l'en-tête x-ratelimit-limit-req-minute de la sonde fait foi.
2. Mettre `reasoning_effort` bas côté Groq dans le pipeline ; vérifier le parseur JSON (balises ```).
3. Relancer un run réel (supprimer `docs/data/briefings/YYYY-MM-DD.json`) et lire `llm_bloc/llm_science/llm_anglais` dans l'onglet Erreurs.
4. Architecture en 2 vagues (cf. mémoire du projet) quand 3 fournisseurs tiennent.
5. Sécurité : les 2 jetons GitHub sont en clair dans les fichiers du projet Claude → les révoquer une fois fini.
