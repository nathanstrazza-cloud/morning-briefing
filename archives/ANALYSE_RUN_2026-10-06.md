# Analyse du run de production du 06/10/2026 (06h10 Paris)

Code exécuté : `main` à 977f541 (AVANT la fusion du sport généraliste, c06e55c). Pipeline OK : 7/7 parties LLM, aucune erreur bloquante.
Source : `docs/data/briefings/2026-10-06.json`, `logs/2026-10-06_061043.log`, `status.json`. Aucun correctif de code fait à ce stade.

## Ce qui est validé par ce run
Marchés sur une séance (CAC −0,8 % contre −3 % avant), garde-fous actualité/science actifs (phrases retirées dans le log), zones France/Monde, citation vérifiée (La Fontaine), météo à périodes, anglais du jour avec vrai LLM (nvidia, B2), calendrier (prochain match trouvé), 7/7 parties LLM (secours NVIDIA qui fonctionne).

## Erreurs / défauts restants (par priorité)
1. **Science : article « approfondi » rempli de connaissances non sourcées.** Sujet = Nobel de médecine 2026 (optogénétique). Le mode « découverte » est refusé (« une seule source non primaire ») alors que le même événement est couvert par plusieurs articles (Le Monde FR, Nature « Medicine Nobel awarded… », etc.) : le regroupement FR/EN des articles d'un même événement n'existe pas pour la science. Résultat : mode approfondi sur UN résumé RSS, et le LLM complète avec ses connaissances générales (ArchT, tyrosine hydroxylase, AAV, IRM fonctionnelle, « lumière non invasive ») que le garde-fou ne détecte pas (il ne vérifie que les nombres). Défauts de forme : fuite « Le résumé indique… / Aucun chiffre n'est fourni dans le résumé », liste vide après « interrupteurs : » (puces retirées par le garde-fou, deux-points orphelin), faute « en silencieux ». Fait vérifiable seulement par recoupement : l'attribution du Nobel (3 lauréats) vient du titre RSS.
2. **« Hypothèse : » encore présent dans `consequences`** (Kharkiv). Le correctif du 05/10 n'a touché que `pourquoi_important` ; `actu_guard.py` ligne ~140 préfixe encore systématiquement.
3. **`pourquoi_important` = null sur 8 actualités sur 9** (4 + 5 phrases retirées par le garde-fou « non étayé »). Voulu, mais le cahier §14 demande « pourquoi est-ce important ». À arbitrer avec l'utilisateur (ex. génération déterministe d'une phrase de contexte, ou accepter).
4. **Sport (code AVANT fusion) : citations de tribune au lieu du résultat.** Deux phrases « Zidane a déclaré… / Giresse a déclaré… » après France–Belgique, sans le score ni le résultat du match ; « podcast Crunch » classé « autres ». La fusion 8cfa890 réécrit le scoring sport : À RE-VÉRIFIER demain, notamment un bonus « résultat/score » et un malus « déclaration/podcast ».
5. **Actualité : choix éditorial discutable.** « Colère des lycéens : vue de l'étranger » (méta-article sur la presse étrangère, résumé = citation d'El Mundo) classé en France ; « cyclone méditerranéen » : résumé qui mélange un sujet sans rapport (pré-COP aux Fidji) copié du RSS, source unique (France 24) ; seuls 4 sujets Monde affichés pour 36 retenus (plafond), à confirmer si voulu.
6. **Marchés : base de comparaison hétérogène.** Indices comparés à la clôture du 02/10 (vendredi), or comparé au 05/10 (cotation continue) : incohérence mineure à documenter ou aligner. Pas d'explication Brent −1,5 % / Nasdaq +1,05 % (« aucune cause fiable » : acceptable).
7. **OpenRouter : 429 en amont à chaque run** (anglais et sport, 1er essai). Le secours NVIDIA rattrape, mais OpenRouter est de fait inutilisable en rôle principal (50 req/j gratuites + upstream saturé). Envisager de le déclasser en dernier secours.
8. **Calendrier ESPN : HTTP 400 sur la plage de dates, 7 fois par run** (soccer ×6 + NBA), puis repli par jour qui fonctionne (13, 18, 18, 10, 10, 62 matchs). Perte ≈ 15–20 s et 7 WARNING parasites : passer directement à la requête par jour.
9. **Horodatage.** `derniere_mise_a_jour` = heure de DÉBUT (06:10:43) alors que le briefing est sauvegardé à 06:16:08 ; message de commit « 04:16 (Europe/Paris) » est en réalité UTC (heure de Paris = 06:16).
10. **`meta.resume_1_phrase` tronqué** avec « … » en plein titre (« promette… »).
11. **Anglais : vocabulaire trop facile** pour B2 (« documents », « action », « goalkeeper » listés). Phrases d'exemple inventées OK par conception.
12. **Sources RSS** : CNRS « invalid token » (4 correctifs inefficaces, abandonner ou remplacer la source) ; ESPN NBA 0 article à chaque run (flux mort probable : remplacer) ; L'Équipe Hand/Volley vides (probablement normal).
13. **Statut `information_rapportee`** correct (cyclone, cargo turc) mais une seule source ; pas de recoupement automatique.

## Ordre de travail proposé (sur `dev`, sans LLM, puis Dev Test)
A. Science : regrouper les articles d'un même événement (FR/EN) AVANT le test « sources multiples » ; vérifier les noms/termes techniques absents de la source (comme `unsupported_names`) ; supprimer les fuites « le résumé » et les deux-points orphelins.
B. `consequences` : appliquer la même règle que `pourquoi_important` (pas de préfixe creux).
C. Sport : contrôler le run du 07/10 après fusion, ajuster.
D. Calendrier direct par jour ; OpenRouter déclassé ; horodatage (fin de run + libellé UTC/Paris).
E. Divers : résumé 1 phrase, vocabulaire anglais, flux morts.
