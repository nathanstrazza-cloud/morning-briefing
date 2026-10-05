# Analyse du run de production du lundi 05/10/2026 (premier run avec les correctifs de efc17b9)

Source : `logs/2026-10-05_061043.log` + `docs/data/briefings/2026-10-05.json` (commit d96ca1c).
Statut global : run OK (6/6 parties rédigées par LLM, 0 erreur finale). Les défauts ci-dessous sont des défauts de CONTENU ou de FIABILITÉ,
classés par priorité (cahier : fiabilité > robustesse > sélection > rédaction > design). Aucun correctif de code n'a été fait : voir « Ordre proposé ».

## Ce qui fonctionne (à ne pas casser)
- Cron externe à l'heure (06:10), fenêtre du lundi = vendredi 18:00 → lundi (week-end couvert).
- Marchés sur une séance (CAC +0,79 %, plus de variation sur 5 jours). Météo en matin/après-midi/soir, 4 villes. Citation vérifiée (Montaigne, Essais I, 39).
- Zones France/Monde par contenu (35 France→Monde, 3 Monde→France). Dédup inter-zones (5 fusions). Calendrier ESPN (prochain foot France–Belgique, Spurs–Hawks).
- Anglais du jour : 5 mots retenus sur 6, glossaire/garde-fou OK, texte NYT + traduction.

## Défauts de FIABILITÉ (priorité 1)
1. **Nom propre inventé par le LLM** — actualite.monde[1] : « visite du chancelier allemand *Olaf Scholz* ». Le titre source dit « visite de Merz » et le log parle de Friedrich Merz.
   Rédigé par Mistral (actu_monde). `actu_guard.py` ne vérifie que les NOMBRES, pas les noms propres.
   → Ajouter au garde-fou : tout nom propre (mot capitalisé / nom de personne) absent du texte source est retiré ou la phrase supprimée ; au minimum interdire d'ajouter un prénom/une fonction non présents.
2. **Explication de marché sans lien causal sourcé** — DAX +1,17 % et Euro Stoxx +1,02 % « expliqués » par « Le budget 2027 prévoit des garanties pour les réacteurs nucléaires » (item France sans rapport avec un mouvement d'indice allemand/européen). Même phrase recopiée pour les deux.
   Cahier §5 : « Si aucune cause fiable n'est identifiée, ne pas inventer d'explication ». → Exiger que l'explication provienne d'un article économique qui cite explicitement le mouvement/le marché ; sinon `explication: null`. Mouvements < ~1,5 % sans cause = ne rien dire (le cahier demande d'ignorer les petites variations). `resume_court` est vide.
3. **Science : article pauvre et trompeur** — mode « découverte » déclenché par un simple résumé RSS du Monde (« Et si la Floride arrêtait de vacciner… »). Le texte écrit « Une étude publiée dans *Le Monde Sciences* » (Le Monde est un journal, pas une revue ; l'étude n'est pas identifiée),
   admet « le résumé ne fournit pas de chiffres » et se contredit (« centaines de décès » puis « sans quantification exacte »). Très loin des ~10 min de lecture du cahier §7.
   `science_b` n'a pas été lancé (plan : « absente si mode découverte »).
   → Un mode « découverte » exige une source primaire (étude, communiqué) ou ≥ 2 sources ; sinon basculer en mode 2 « sujet approfondi » (le LLM écrit alors un article pédagogique ; faire passer le garde-fou sur les nombres). Vérifier aussi que « modèle de simulation » est bien dans la source.
4. **Mentions « Hypothèse : » systématiques** dans `pourquoi_important` (tous les items France/Monde) — effet de bord des prompts anti-invention : le champ est devenu une formule creuse (« met en lumière les controverses… »). À remplacer : soit un vrai « pourquoi » tiré du texte, soit vide ; réserver « Hypothèse » aux conséquences (champ `consequences`, toujours null aujourd'hui).

## Défauts de SÉLECTION (priorité 2)
5. **Scoring par mots-clés à sous-chaînes** (`src/analyse/scoring.py`) : `"mort" in texte` donne 9 à « Cheikh Hamidou Kane est mort à 98 ans » (décès d'un écrivain) alors que l'élection présidentielle brésilienne
   (résultats du 1er tour : Flavio Bolsonaro « frôle la victoire ») et l'alerte Ebola en RDC ne passent pas devant. Risque de faux positifs aussi sur « loi » (emploi, déploiement), « record », « mort » (Mortier…). → mots entiers (regex `\b`), pondération par type d'événement, bonus pour géopolitique/élections/guerre/santé publique, malus faits divers/tribunes/interviews.
6. **Item « Brésil » = l'avant-scrutin** (« oppose Lula à Bolsonaro », statut `information_rapportee`) alors qu'un article de résultats existait dans les flux. → préférer, parmi les items fusionnés, le plus récent / celui qui contient le résultat.
7. **Doublon dans France** : deux items Christa Pike (Libération+20 Minutes / France Info) non fusionnés, et cet événement américain est classé « France » (la zone par contenu ne le réattribue pas : pas de mot-clé « États-Unis » dans le titre FR de France Info).
   → étendre `zones.py` (États-Unis/Tennessee/CNN…) et baisser le seuil de dédup pour des titres à entités communes (Christa Pike). Du bruit éditorial passe aussi : tribune d'opinion (500 anciens ministres), interview (Michael I. Jordan), fait divers (conflit de voisinage à Lagor) au même rang que l'actu internationale ; Monde = seulement 4 items.
8. **Sport peu pertinent** : « Godts est confiant sur sa capacité à s'imposer au PSG » (football), trophée Alain Gilles (Gabby Williams devant Wembanyama — vérifier que c'est bien pertinent), aucune info Spurs/NBA (flux ESPN NBA = 0 article à chaque run). `prochains_matchs` vide alors que le calendrier a trouvé France–Belgique et Spurs–Hawks (n'est utilisé que si « rien à signaler » : OK par conception, à confirmer).

## Défauts de ROBUSTESSE (priorité 3)
9. **OpenRouter renvoie « Réponse vide » à chaque appel** (anglais et sport aujourd'hui, déjà souvent avant) : +30 s à +15 s perdus, puis NVIDIA reprend. Cause probable : modèle de raisonnement qui consomme max_tokens (comme gpt-oss sur Groq). → baisser/figer le modèle, réduire le raisonnement, ou le remplacer en tête de `anglais`/`sport` par NVIDIA/Groq dans `config/llm_plan.yaml` (aucun code à changer).
10. **Calendrier ESPN : HTTP 400 sur la plage de dates, à chaque run** (7 requêtes en échec avant repli jour par jour) → supprimer la requête par plage et passer directement au jour par jour (ou mémoriser l'échec).
11. **Flux RSS** : CNRS « invalid token » (4e fix infructueux, toujours le même bug connu), ESPN NBA, L'Équipe Hand et Volley = 0 article (probablement normal pour Hand/Volley ; NBA à investiguer car Spurs prioritaires).
12. **Horodatage** : le commit dit « 04:15 (Europe/Paris) » alors que le runner est en UTC (04:15 UTC = 06:15 Paris) → `date` dans `.github/workflows/briefing.yml` ligne ~55 sans `TZ=Europe/Paris`. De plus `derniere_mise_a_jour` = heure de DÉBUT du run (06:10:43), pas de fin (06:15:13) ; le cahier demande « l'heure de la dernière mise à jour ». `meta.resume_1_phrase` coupe une phrase au milieu (« …une offensive p… »).
13. Citation : OK ce matin ; vérifier qu'elle ne se répète pas (historique) et que la banque de 22 citations ne s'épuise pas (≈ 1 mois).

## Qualité rédactionnelle (priorité 4, mineur)
- Anglais : niveau trop facile pour « B2/C1 » (jails, exposing, false information ; 0 mot « difficile »), majuscules parasites (« Jails », « Deep Rifts »), mot « Exposing » = forme conjuguée peu utile. Resserrer le prompt/filtre sur le vocabulaire moins courant.

## Ordre proposé (à valider avec l'utilisateur ; à coder sur `dev`, jamais directement sur `main`)
1. Garde-fou noms propres (#1) — le plus grave (faux fait publié).
2. Explications de marché (#2) et mode science (#3).
3. Scoring par mots entiers + malus opinion/fait divers + dédup/zones (#5, #6, #7).
4. Retirer le préfixe « Hypothèse » de `pourquoi_important` (#4).
5. OpenRouter (#9), calendrier (#10), horodatage (#12).
6. Sport / NBA (#8, #11), anglais (#rédaction).
Règles : voir `SUIVI_CORRECTIFS.md` et `DEV_WORKFLOW.md` (dev → Dev Test manuel → fusion avec accord ; ne jamais committer docs/data ni logs sur `dev`).
