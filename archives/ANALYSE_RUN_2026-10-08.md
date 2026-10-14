# Analyse du run de production du 08/10/2026 (06h10 Paris)

Document de relais pour une autre IA. Aucun correctif de code dans ce commit : analyse seule.
Code testé : `main` @ b0a5a09 (fusion des parties A–E du 06–07/10, premier run réel de ces correctifs).
Run : 06:10:43 → 06:15:08 (≈ 4 min 25), 7/7 parties LLM (actu_france=groq, actu_monde=mistral, marches=nvidia,
anglais=nvidia, science_a=mistral, science_b=groq, sport=nvidia), aucune erreur LLM.
Le commit « 16:23 » du même jour est un second déclenchement cron-job.org ignoré par le garde-fou d'idempotence
(comportement attendu).

## Retour de l'utilisateur (résumé)
- Actualité : décevante, peu d'informations réellement importantes (« rien de découvert »).
- Anglais : à modifier plus tard (niveau, choix des mots).
- Météo : « ciel dégagé » affiché avec une probabilité de pluie très élevée → incohérence.
- Sport : apprécié. Marchés : apprécié (résultat jugé positif).

## Validé en réel (à ne plus re-vérifier)
- Calendrier ESPN : un seul HTTP 400 puis bascule jour par jour (partie D).
- Plan LLM : 7/7 parties, NVIDIA prend marchés + anglais + sport, OpenRouter pas sollicité.
- Horodatage : `derniere_mise_a_jour` = fin de run (06:15), `debut_run` = 06:10, commit libellé en heure de Paris.
- Marchés sur une séance (CAC −1,22 %, ref = clôture 06/10) ; pas d'explication inventée pour les indices.
- Sport généraliste : 4 retenus (foot ×2, tennis, basket), plus de dépendance Spurs / équipe de France.
- Garde-fous : 7 phrases retirées en actu France, 4 en actu Monde, 3 en science (dont « 285 millions de personnes »).
- Citation : banque vérifiée (Boileau, L'Art poétique, 1674).

## Défauts constatés (par ordre de priorité)

### 1. Science : le mode « approfondi » est un article écrit à partir d'un simple résumé RSS (PRIORITÉ HAUTE)
- Le log montre que TOUTES les candidates « découverte » sont refusées : `decouverte_qualifiee()`
  (src/generation/briefing_generator.py ~l.575-600) utilise `_RE_RECHERCHE`, un vocabulaire **uniquement français**
  (étude, chercheurs, cellules…). Les ~50 articles de Nature News (anglais) échouent donc tous sur
  « aucun vocabulaire de recherche ». Le Nobel de chimie 2026 (Kagan / Soai) est refusé pour « résumé trop court ».
- Repli : le pipeline écrit alors un article de 1 300 mots sur l'optogénétique à partir de **un seul résumé Le Monde**
  (déjà refusé en mode découverte pour « une seule source non primaire »). Le texte contient des détails dont rien ne
  prouve qu'ils figurent dans la source : « dix patients en France, États-Unis, Royaume-Uni », « aucun effet indésirable
  grave », « améliorations maintenues plusieurs mois », « caméra miniature implantée ou externe », section
  « Éthique ». Les textes sources n'étant pas stockés dans le JSON, je n'ai pas pu comparer ; **à vérifier** en
  relisant le résumé RSS du jour. Le garde-fou ne vérifie que les nombres et les noms propres, pas ces affirmations.
- Pistes : (a) rendre `_RE_RECHERCHE` bilingue (study, researchers, trial, cells, protein, Nobel…) ; (b) accepter les
  prix Nobel et les sources primaires avec un résumé court ; (c) en mode approfondi, ne jamais broder sur un fait
  d'actualité à source unique : partir d'une liste de sujets pédagogiques avec sources réelles (liste non encore
  implémentée, cf. cahier V1 §7 mode 2) ; (d) stocker `textes_sources` dans le JSON pour pouvoir auditer.

### 2. Actualité : peu d'importance, choix éditoriaux faibles
- Entonnoir : France 94 bruts → 35 retenus après seuil → 5 affichés ; Monde 102 → 37 → **3 affichés seulement**.
- France : « Qui sont les candidats déclarés à la présidentielle 2027 ? » (page de liste, pas un événement),
  « De quoi la vague de films sur la Seconde Guerre mondiale est-elle le nom ? » (entretien culturel), Bardella
  (article d'analyse). Seuls le procès de Trèbes et la Cour des comptes sont des faits.
- Monde : « Trump veut faire d'un de ses golfs une résidence présidentielle » (anecdote) est retenu alors que les
  logs montrent des sujets plus importants écartés : soupçons de peste en Russie (NYT + Le Monde, fusionnés),
  Christa Pike (survivante d'une exécution), 7-Octobre trois ans après, 500 migrants expulsés par les États-Unis vers
  l'Afrique, journalistes égyptiens inculpés.
- Cause probable : 19+ items France reclassés en Monde par `zones.py`, puis plafond 3 en Monde ; le scoring
  (analyse/scoring.py) donne trop peu d'écart entre faits et articles de forme (explication, liste, entretien).
  À vérifier : pourquoi seulement 3 en Monde (plafond de config ? diversité 2 par entité ?).
- Le sujet « Guerre au Moyen-Orient » (attaques d'aéroports saoudiens) et l'Ukraine sont bien présents.

### 3. Météo : probabilité de pluie incohérente avec le ciel et les millimètres
- Matin : `probabilite_pluie_pct` = 88–93 % alors que `precipitation_mm` = 0,0–0,1 et description « ciel dégagé ».
  Cause : `build_periods()` (src/collecte/weather.py ~l.120) prend le MAX des probabilités horaires de la plage 
  (un pic isolé suffit) et l'affiche à côté d'une description issue des codes effectifs.
- Antibes affiche en plus `precipitation_mm` = 10,0 pour la journée (somme quotidienne, probablement tombée pendant la
  nuit, avant 06h) alors que les trois périodes affichées donnent 0,1 / 0 / 0.
- Le résumé de zone dit « Ciel dégagé le matin… » (cohérent) mais la carte affiche 93 % de pluie → contradiction visible.
- Pistes : afficher la probabilité seulement si cumul ≥ ~0,2 mm ou code pluvieux sur la période ; sinon utiliser la
  médiane ; calculer les mm du jour sur les heures restantes (pas la somme de la nuit passée) ; faire porter l'alerte
  « pluie » sur la même règle que l'affichage.

### 4. Marchés : correct mais une explication douteuse
- Brent +2,11 % expliqué par « Sébastien Lecornu annonce un apport de 10 millions de barils de gazole aux
  distributeurs » : lien causal faible (annonce nationale sur le gazole vs prix mondial du Brent, alors qu'une guerre
  au Moyen-Orient est en cours). Le garde-fou « un article qui parle du marché ou de la Bourse » est trop permissif :
  exiger la mention du pétrole/Brent dans l'article ET un lien de cause explicite.
- Indices européens −1,2 à −1,5 % sans explication (conforme à la règle « ne pas inventer »).

### 5. Anglais : mots toujours trop faciles
- Mots retenus : « art of surgery », « Artificial Intelligence », « leverage », « distinguish », « catastrophic »
  pour un niveau annoncé B2. Seuls « leverage » (et à la rigueur « distinguish ») ont une valeur d'apprentissage.
  La piste de liste de fréquence embarquée (ANALYSE_DEV_TEST_2026-10-06.md, défaut 2) n'est toujours pas faite.
- Traduction fidèle ; article NYT (IA et chirurgie au Canada) bien choisi.

### 6. Sport : bon retour, deux points de forme
- « Nanterre battu par Trabzonspor pour ses débuts en Ligue des champions » : ambiguïté, c'est la Ligue des champions
  FIBA de basket ; à préciser dans le texte (« Ligue des champions de basket »).
- ESPN NBA News et ESPN Top Headlines : 0 article à chaque run (flux probablement morts ou bloqués) ; L'Équipe Hand et
  Volley : 0 article (peut être normal). CNRS : « invalid token » toujours (4e tentative de correctif en échec).

## Ordre de travail proposé (sur `dev`, accord de l'utilisateur requis avant fusion)
1. Science : regex bilingue + règle Nobel/source primaire + interdire le mode approfondi sur source unique non
   primaire (ou liste de sujets pédagogiques sourcés). Ajouter `textes_sources` dans le JSON.
2. Actualité : pénaliser listes / entretiens / analyses ; débloquer le plafond Monde ; faire remonter peste en Russie,
   7-Octobre, migrants, journalistes.
3. Météo : règle de cohérence probabilité / mm / description, mm restants du jour.
4. Marchés : durcir l'explication (mot-clé de l'actif + lien causal).
5. Anglais : liste de fréquence, niveau réellement B2/C1.
6. Divers : libellé Ligue des champions basket, flux ESPN/CNRS morts.

## Rappels
- Jeton GitHub à régénérer avant le 25/10/2026 (et retirer les jetons en clair des fichiers du projet Claude).
- Retour arrière de la dernière fusion : `git revert -m 1 30c69b5` sur `main`.
- Règles dev/main et doc générale : SUIVI_CORRECTIFS.md, DEV_WORKFLOW.md, HANDOFF_LLM.md.
