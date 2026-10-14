# Analyse du run de production du dimanche 11/10/2026

> Document de relais (lisible par une autre IA). Doc seule : aucun correctif de code dans ce commit.
> Run : workflow « Morning Briefing », `workflow_dispatch` (cron-job.org) à 06h10 Paris, run GitHub 38110737374,
> code = `24bdbc4` (premier run de production avec : actualité malus/plafond Monde 8, météo cohérente, anglais littéraire).
> Résultat : succès, 6/6 parties LLM, ~3 min 40 (pause de 150 s comprise), briefing publié `24c06d3`.

## 0. Constat structurel : le run tourne aussi le week-end
- Cause : le déclenchement principal est le job externe cron-job.org (appel `workflow_dispatch`), configuré tous les jours.
  Le `schedule` natif du workflow est restreint à lun-ven (`0 7 * * 1-5`), mais il n'est qu'un filet de sécurité.
  Aucun garde-fou « jour ouvré » dans le code (`grep weekday` : seul `utils.py` teste le lundi).
- Les runs de samedi 10/10 et dimanche 11/10 ont réussi ; il y a donc 2 briefings week-end publiés (cahier V1 §18 : lun-ven seulement).
- Effets à connaître :
  1. Quotas : 1 run/jour de plus x 2 ; sans risque pour l'instant (Groq 1000 req/j, OpenRouter 50/j, appels par run = 6 ou 7).
  2. Lundi : `calculer_fenetre` remonte au vendredi 18h (`is_monday`) alors que samedi et dimanche ont déjà un briefing
     -> risque de reprendre des sujets déjà publiés samedi/dimanche. La couverture week-end du lundi n'est plus nécessaire.
  3. Répétitions samedi -> dimanche déjà visibles : séisme au Panama, Nobel de la paix Pillay, accord Trump-Poutine sur le diesel,
     mobilisation lycéenne, présidentielle 2027 (cf. §2).
- Décision à prendre par l'utilisateur : (a) garder le week-end (alors désactiver la fenêtre « lundi » et ajouter une
  dédup inter-jours), ou (b) revenir à lun-ven (retirer samedi/dimanche dans cron-job.org, ou garde-fou `weekday() >= 5` dans `main.py`).
  Ne rien changer avant sa réponse.

## 1. Ce qui fonctionne (vérifié dans le log et le JSON du 11/10)
- Plan LLM : actu_france=groq, actu_monde=mistral, marchés=nvidia, science_a=mistral, science_b=groq, sport=nvidia ; 0 essai échoué ; OpenRouter non sollicité.
- Anglais : plus aucun appel LLM (`llm_anglais.genere_par_llm=false` est NORMAL depuis la refonte littéraire, pas une erreur). Passage du jour : Orgueil et Préjugés (Austen), glose « mot (= traduction) ». Texte conforme à la mémoire de l'auteur de la banque ; à relire contre Gutenberg (non fait, hôte non joignable depuis le sandbox).
- Citation : Pasteur 1854 (banque vérifiée), enfin non nulle.
- Météo : cohérente (0 mm, 0 % partout, matin dégagé puis couvert, tmax 22-24 °C) ; plus d'incohérence « dégagé + forte pluie ».
- Marchés : variations sur une séance (CAC +0,95 %, DAX +1,13 %, or +1,43 %) ; aucune explication inventée (`explication: null`, résumé « aucune cause fiable »).
- Actualité : Monde = 5 affichés (8 fournis, le LLM en a rendu 5 -> avertissement de log « le LLM a rendu 5 événement(s) sur 8 »).
- Calendrier ESPN : 1 seul HTTP 400 par run, puis jour par jour (conforme).

## 2. Défauts constatés (à traiter sur `dev`, accord requis avant fusion)
1. PRIORITÉ HAUTE — science « approfondie » fabriquée à partir d'un seul résumé RSS de 2 lignes (`matiere_source: fine`,
   `textes_sources_audit` = 1 source Le Monde Sciences). Sujet : interview de Jérémie Naudé (« Neuro arnaque »). L'article fait ~1 400 mots,
   attribue à Naudé des analyses (« souligne », « montre que… ») absentes de la source, et traite un livre polémique comme un
   sujet scientifique. Le garde-fou n'a retiré que 2 phrases (nombres) : il ne voit pas les affirmations en mots courants.
   Pistes : refuser le mode approfondi si une seule source et résumé < ~500 caractères (le repli doit alors être une courte
   note honnête, ou un sujet pédagogique réellement sourcé) ; interdire l'attribution de thèses à une personne nommée au-delà du texte ;
   exclure interviews / tribunes / essais du pool science.
2. Sport : le texte « Brilliant Guimaraes goal helps Arsenal fight back to beat Leeds » est resté en anglais (titre BBC non traduit,
   défaut déjà connu depuis le 06/10). Absents alors qu'ils figuraient dans les titres collectés : Lens - Lyon (retour de la Ligue 1),
   Mondiaux de judo (fusionné par entités avec un autre événement). `prochains_matchs` vide car des items sont retenus (voulu).
3. Zones France/Monde : « Guerre au Moyen-Orient : l'Arabie saoudite accuse les Houthis… (Riyad) » est affiché en France ;
   c'est du Monde (la fusion par entités l'a rattaché à un titre classé France). Le titre est un « EN DIRECT » non reformulé.
4. Actualité : élément faible conservé en France (« Lalanne et Dieudonné lancent leur campagne », `information_rapportee`, 1 source,
   pourquoi_important null) alors que Lens-Lyon / autres faits n'apparaissent pas. `pourquoi_important` null sur 5/10 (décision
   du 06/10 : on laisse vide si non étayé, ne pas toucher).
5. Marchés : le mouvement du Brent (+0,42 %) et de l'or (+1,43 %) n'est pas relié à l'accord Trump-Poutine sur le diesel (gros sujet
   du jour) ; ici l'absence d'explication est préférable à un lien faible (règle de fiabilité) — à ne PAS « corriger » sans source.
6. LLM Monde : rend 5 événements sur 8 fournis malgré la règle 8 « un élément par événement » : la règle n'est pas suivie par Mistral.
   Piste : plafond côté code (renvoyer les événements manquants sous forme de repli court) ou test sur Groq pour la partie Monde.
7. Flux vides ou en erreur (inchangé) : CNRS (invalid token, 4 correctifs infructueux), L'Équipe Hand/Volley, ESPN NBA, ESPN Top Headlines
   (week-end creux, probablement normal sauf CNRS qui est un vrai bug de parsing).
8. Doublons week-end (cf. §0) : pas de dédup inter-jours effective.

## 3. À faire, par ordre de priorité
1. Réponse de l'utilisateur sur le week-end (§0) puis action correspondante.
2. Science (§2.1) : seuil « matière suffisante » avant le mode approfondi + garde-fou d'attribution.
3. Zones/titres « EN DIRECT » et rattachement par entités (§2.3).
4. Sport : traduction systématique des titres anglais, Lens-Lyon / Ligue 1 (§2.2).
5. Mistral/Monde : 5 sur 8 (§2.6).
6. Jeton GitHub à régénérer avant le 25/10 ; relire le passage d'anglais contre Gutenberg ; CNRS.

## 4. Règles de travail (rappel)
Développer sur `dev`, ne jamais committer `docs/data` ni `logs` sur `dev`, `Dev Test` manuel via l'API
(workflow id 372349191), fusion `dev` -> `main` seulement avec l'accord de l'utilisateur ; voir `DEV_WORKFLOW.md`, `SUIVI_CORRECTIFS.md`, `HANDOFF_LLM.md`.
