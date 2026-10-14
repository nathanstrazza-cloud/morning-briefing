# Analyse du run du 13/10/2026 (06h10 Paris, code de main = 7cee422+f5e5bce)

Run OK (5/5 parties LLM, Groq/Mistral/NVIDIA). 2e déclenchement de 16h49 ignoré par l'idempotence (normal).

## Défauts relevés à la demande de l'utilisateur
1. **Science trop courte (162 mots au lieu de ~1400)**. Cause : le mode « découverte » a été retenu pour une TRIBUNE du Monde
   (« Des prix Nobel scientifiques sans lauréates… », résumé RSS de 3 phrases, aucune étude). `decouverte_qualifiee` avait une exception
   « Nobel » (résumé minimum 60 car., pas de règle des 2 sources) ; le tri préfère les Nobel ; le mode découverte rédige « un article court »
   et le garde-fou a en plus retiré 1 phrase. Le mode « approfondi » (sujet pédagogique Wikipédia, ~10 min) n'est jamais tombé en jeu.
2. **Sport trop vide** : 4 éléments seulement (plafond `max_sport_total: 4` décidé le 24/09, `max_par_sport: 2`), sur 152 items collectés.
   Le LLM ne recevait que les TITRES → éléments sans contexte (une citation de tribune « J'ai joué comme une merde », une anecdote
   de transfert). Les prochaines affiches (calendrier ESPN : Man City – PSG, Lakers – Warriors) n'étaient affichées que si rien n'était retenu.
3. NVIDIA a rendu un JSON de sport invalide (« Expecting ',' delimiter ») → repli Groq OK (normal, non bloquant).
4. Autres (non traités) : Mistral rend 5 événements Monde sur 8 fournis ; CNRS « invalid token » ; ESPN NBA/Top Headlines et L'Équipe Hand/Volley à 0 article ;
   la tribune « Blocus des lycées » et plusieurs items « Selon Libération… » retirés par le garde-fou actu (5 phrases France, 6 Monde).

## Correctifs sur `dev` (voir SUIVI_CORRECTIFS.md, section 13/10 soir)
Science : plus d'exception Nobel sur la matière minimale (< 500 car. refusée sauf ≥ 2 sources ou source primaire), marqueurs sociétaux
(femmes, lauréates, parité, discriminations…) dans le titre = refus, champ `science.nb_mots` + alerte log si approfondi < 900 mots.
Sport : `max_sport_total` 8, `max_par_sport` 3, le LLM reçoit titre + résumé (300 car.) + source, consigne « 1 à 2 phrases informatives,
rien d'ajouté, propos cités reformulés sans grossièretés », `TOKENS_SPORT` 1800, prochaines affiches toujours affichées (frontend + `annoter_sport`).
201 tests OK. À valider par un Dev Test avec LLM ; fusion dev → main seulement avec l'accord de l'utilisateur.
