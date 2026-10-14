# Analyse du run du 2026-10-01 — erreurs restantes (à lire avant de coder)

Contexte : le pipeline est techniquement sain (7/7 parties LLM rédigées, ~5 min, déclenché à l'heure par
cron-job.org). Les erreurs restantes sont des erreurs de CONTENU, pas d'infrastructure. Elles violent surtout
le principe n°1 du cahier des charges : fiabilité > tout. Statut de chaque point : [VÉRIFIÉ] = constaté dans
`docs/data/briefings/2026-10-01.json` ou le code ; [HYPOTHÈSE] = cause probable non testable depuis le sandbox
(pas d'accès réseau à Yahoo/Groq/etc.). Ordre = priorité conseillée.

## 1. Science : statistiques inventées et fausses sources [VÉRIFIÉ] — CRITIQUE
- Article « Autodiagnostic en ligne… » : chiffres sans aucune source (« 30 % à 55 % de concordance », « 500 scénarios »,
  « 2 000 internautes, 38 % / 22 % », « 27 % vs 12 % » lombalgie, « plus de 70 % des adultes » attribué à *Le Monde Sciences*).
- La section Sources cite une seule chronique du Monde (rubrique « intimités », pas une source scientifique) et dit
  « se référer aux références détaillées disponibles dans l'article du Monde » : faux, l'article n'a pas ces données.
- Marqueur interne publié par erreur : « *(Fin de la moitié A – la suite abordera…)* » ; titres de format différent
  entre les moitiés (`## **Introduction**` vs `## 5.`) ; « Bing Chat » obsolète.
- Cause : `science_a`/`science_b` (src/generation/parts.py, `_science_prompt`) ne reçoivent que `contenu_source` = résumé RSS
  d'UN article. Le prompt exige les sections « Données et résultats », « Ce que savent les scientifiques »… → le modèle comble
  avec des chiffres plausibles. Aucune vérification a posteriori.
- Correctifs proposés : (a) interdire dans le prompt tout chiffre/étude absent de `contenu_source`, et écrire « non disponible
  dans la source » pour la section Données ; (b) validateur post-génération : extraire les nombres/% de l'article et rejeter
  (ou retirer la phrase) si absents de la source ; (c) supprimer toute ligne entre parenthèses/italique « (Fin de la moitié… » à la
  fusion dans `merge_results` ; (d) section Sources générée par le CODE (liens réellement fournis), pas par le LLM ;
  (e) idéalement choisir les sujets « approfondis » dans une liste curée de sujets + sources primaires (Nature, CNRS, Inserm…).

## 2. Marchés : variations probablement calculées sur 5 jours [HYPOTHÈSE forte] — CRITIQUE
- Brent −8,0 % « sans explication » et CAC −1,45 % : valeurs douteuses pour une seule séance.
- Cause probable : `src/collecte/markets.py` interroge Yahoo en `range=5d&interval=1d` puis calcule la variation avec
  `meta.previousClose or meta.chartPreviousClose`. Sur l'endpoint « chart », `chartPreviousClose` = clôture AVANT le début de la
  plage (≈ 5 séances plus tôt), et `previousClose` est souvent absent. La variation serait donc hebdomadaire, ce qui fausse
  aussi les explications du LLM (il rattache un mouvement de 5 jours à l'actualité du jour).
- À faire : calculer à partir du tableau `indicators.quote[0].close` (dernier vs avant-dernier non nul), loguer les champs
  `meta` reçus, et vérifier avec `scripts/llm_probe.py`-like (petit script de sonde Yahoo en workflow manuel).
- Explication CAC (« menace de Trump envers Powell ») : lien causal non démontré par les sources → doit être « selon … » ou omis.
- Le site n'affiche que les mouvements ≥ 1 % ; S&P/Nasdaq/DAX/Euro Stoxx/Or ne sont jamais montrés quand ils bougent peu :
  voir si l'utilisateur veut une ligne de synthèse fixe.

## 3. Ajouts non sourcés dans l'actualité (hallucinations d'enrichissement) [VÉRIFIÉ]
- « l'ancien président américain » pour Donald Trump (actu_monde, Powell) : faux (président en exercice ; la version France
  dit bien « le président américain »).
- Christa Pike : « première échec aux États-Unis depuis 2023 » et « les autorités du Tennessee n'ont pas encore commenté » :
  absents du texte source, non vérifiés. (Fond de l'événement : exécution programmée le 30/09/2026 à Nashville, confirmée par
  plusieurs médias ; la tentative ratée est rapportée par Le Monde d'après ses avocats.)
- Hegseth : « tensions syndicales » inventé. Esther Rantzen : « rejet partiel d'une proposition de loi en 2024 » non présent
  dans le flux. Lagarde : « rassurant les marchés » = spéculation présentée comme fait ; le résumé ne dit pas que le titre.
- Cause : les prompts (`_REGLES_COMMUNES`, parts.py) demandent « pourquoi_important » et « consequences » ; des petits modèles
  (ministral-14b, gpt-oss-20b) complètent avec des connaissances de leur entraînement.
- Correctifs : résumé = uniquement faits présents dans le texte fourni ; « pourquoi_important » / « conséquences » préfixés
  « Hypothèse : » ou null si non étayés ; vérificateur léger (nombres, années, « ancien/actuel », « première fois ») ; mettre
  un modèle plus fiable sur actu_monde si possible.

## 4. Doublons entre France et Monde [VÉRIFIÉ]
- Powell/Fed, Hegseth et Pike apparaissent dans les DEUX zones. Pire : même événement, deux statuts (`fait_confirme` côté Monde
  avec 2 sources, `information_rapportee` côté France avec 1 source).
- Cause : `dedup` est appelé séparément par zone (log : « 119 → 110 » puis « 70 → 68 ») ; le flux « Le Monde — Une » classé
  france contient beaucoup d'international.
- Correctif : dédup globale inter-zones après collecte, fusion des sources, affectation France/Monde par contenu (pas par flux).

## 5. Sport : sélection hors sujet et basket absent [VÉRIFIÉ]
- Les 4 items = foot féminin (Chelsea/OL, Paris FC–Arsenal) + démission d'une cheffe de délégation italienne (olympisme).
  Aucun match masculin Ligue 1/C1/Europa, rien sur les Spurs (basket : 9 items collectés, 0 retenu).
- Cause : `score_event` (src/analyse/scoring.py) est un scoring d'ACTUALITÉ générique (« démission » = 9 → l'item Bianchedi passe
  devant) appliqué au sport, puis `max_sport_total=4` coupe globalement (main.py ~l.154) sans quota par catégorie.
- Correctif : scoring sport dédié (mots-clés Ligue 1/C1/Europa/Spurs/Wembanyama…, malus hors périmètre), quota minimal par
  catégorie (≥1 basket si Spurs/NBA disponible), décision à prendre avec l'utilisateur sur le foot féminin.

## 6. Citation du jour toujours null [VÉRIFIÉ, structurel]
- Le prompt (actu_france) dit « uniquement si CERTAIN » ; les petits modèles répondent null à chaque fois. Rien ne garantit
  jamais une citation → le cahier §9 n'est pas rempli.
- Correctif recommandé : banque de citations VÉRIFIÉES (JSON versionné : texte, auteur, œuvre/source, année), tirage
  déterministe par date, sans LLM. Respecte « authenticité d'abord ».

## 7. Anglais du jour [VÉRIFIÉ]
- « centrist » traduit « centré » (correct : « centriste ») ; vocabulaire trop facile (Prime Minister, lawyer, politician),
  exemples génériques. Cause : NVIDIA gpt-oss-20b + prompt sans niveau cible ni liste de mots à exclure. Correctif : cibler
  B2/C1, exclure les mots courants, demander des collocations, et relire la traduction (ou la comparer à un second modèle).

## 8. Météo [VÉRIFIÉ]
- « bruine forte » à Antibes/Cannes avec 0–0,2 mm : `description` vient du code météo INSTANTANÉ à 06h10 (`current.weather_code`),
  pas de la journée ; `description_dominante` = celle d'Antibes seulement (`weather_list[0]`, weather.py `summarize_zone`).
- Codes WMO absents de `WMO_CODES` (56/57, 66/67, 77, 85/86) → « conditions variables ».
- Cahier §8 : manque l'évolution dans la journée. Correctif : `daily.weather_code` + `hourly` (matin/après-midi/soir).

## 9. Divers
- `meta.resume_1_phrase` : phrase tronquée avec « … » en plein milieu (parts.py `merge_results`) ; couper à la dernière phrase
  entière ou afficher 1 seul titre.
- Bruit infra non bloquant : CNRS « invalid token » (4 correctifs successifs inefficaces), ESPN/Hand/Volley « vide »,
  OpenRouter 429 amont systématique sur `gemma-4-31b-it:free` (le secours NVIDIA fonctionne, ~30 s perdues par partie).
- Sécurité : les 2 jetons GitHub sont en clair dans les fichiers du projet Claude ; l'ancien est révoqué, « Nouveau tôle »
  expire le 25/10/2026 → régénérer en fine-grained (Contents + Actions, ce seul dépôt) et supprimer les anciens fichiers.

## Ordre de travail suggéré
1) Science (validateur anti-chiffres inventés + sources par le code) 2) Marchés (calcul sur `close[-1]` vs `close[-2]`)
3) Prompts actualité « faits du texte uniquement » 4) Dédup inter-zones 5) Sport 6) Citations curées 7) Météo/anglais/meta.
Chaque correctif doit être testé hors réseau (providers simulés) puis vérifié sur un vrai run (supprimer
`docs/data/briefings/YYYY-MM-DD.json` pour forcer un re-run le même jour). Voir aussi `HANDOFF_LLM.md` pour l'architecture LLM.
