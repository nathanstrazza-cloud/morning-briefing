# Analyse du Dev Test du 06/10/2026 (code `dev` = 32f5d83, parties A à E)

Run GitHub Actions n° 37482217409 (Dev Test, branche `dev`, avec LLM, lancé à 16:49 Paris), conclusion : success.
LIMITE D'ANALYSE : l'artefact (JSON complet, status.json, log complet) est stocké sur `productionresultssa1.blob.core.windows.net`, hôte BLOQUÉ pour l'environnement de Claude. Seules les annotations du job (étape « Résumé du test en annotations », tronquées à ~4 Ko chacune) ont pu être lues (API `check-runs/<id>/annotations`). Pour une analyse complète : autoriser cet hôte dans les paramètres réseau, ou déposer l'artefact dans la conversation.

## Vérifié et conforme
- **Calendrier ESPN** : un seul HTTP 400 (soccer/fra.1), puis « la plage de dates est refusée -> requêtes jour par jour » ; ensuite 13, 18, 18, 7… matchs, NBA 62 ; prochain football Manchester City – PSG. (Partie D OK.)
- **Plan LLM** : « Tour 1 : nvidia -> marches, anglais » ; parties rédigées 6/6 (actu_france et monde sur Groq/Mistral, marchés + anglais + sport sur NVIDIA, science_a sur Mistral) ; aucun passage par OpenRouter visible dans les extraits. 6 parties et non 7 : la science n'a qu'une partie (A) = très probablement le mode « découverte » (la fusion FR/EN a donc sans doute qualifié le Nobel) — À CONFIRMER avec le log complet.
- **Garde-fou actualité** : 1 « pourquoi_important non étayé » retiré côté France, 8 phrases côté Monde dont 2 « [consequences non étayées] » ; aucun préfixe « Hypothèse : » ; `conseq=None` sur tous les items visibles (voulu). (Partie B OK ; effet « presque toujours vide » confirmé.)
- **Marchés** : tous les symboles comparés à la clôture du 05/10 (or compris) -> base homogène, confirme que le « point or » n'était pas un défaut. Brent −1,74 % sans cause fiable (explication null : conforme).
- **Météo** 4/4 villes ; **citation** La Fontaine (même citation que le run de prod du matin : normal, même jour).

## Défauts constatés (nouveaux ou persistants)
1. **SPORT (partie C à faire)** — nouveau code jamais vu en réel, 108 items collectés, 4 retenus {rugby 1, tennis 2, football 1}, 3 affichés :
   - un titre ANGLAIS non traduit : « Shevchenko's son signs for seventh-tier club. » (la consigne 6 de `SYSTEM_SPORT` demande de traduire, le LLM ne l'a pas fait ; aucun contrôle déterministe derrière) ;
   - anecdote sans intérêt retenue (fils de Shevchenko) et phrase quasi incompréhensible : « Pierre Mignoni à Toulon, bilan chiffré insuffisant. » ;
   - 4 retenus mais 3 affichés : un élément (tennis) perdu entre sélection et rédaction ;
   - seul Alcaraz (« s'impose en deux manches contre Jiri Lehecka, premier titre depuis sept mois et demi ») est un bon item.
   Pistes : garde-fou anglais pour le sport (détecter une phrase non française et la retirer ou la faire retraduire), seuil/bonus de scoring (résultat > anecdote/transfert mineur), exiger une phrase complète avec sujet+verbe, vérifier que tout élément retenu est affiché.
2. **ANGLAIS** : les mots triviaux passent encore (« memories », « previous effort », « reviving » ; « faciles : 0 » dans le log) ; « Saudi-led » traduit « coalisé dirigé par l'Arabie Saoudite » (maladroit). La liste `MOTS_FACILES` ne suffit pas. Piste : embarquer une liste de fréquence (top ~5000 mots) dans le dépôt (fichier texte, sans dépendance réseau) et rejeter les mots simples fréquents.
3. **RÉSUMÉ SANS RAPPORT AVEC LE TITRE** (actualité France) : titre « La France réalise son premier tir d'exercice d'un missile nucléaire sans charge depuis un sous-marin, Emmanuel Macron assiste à l'essai » ; résumé affiché = propos d'un diplomate français à l'ONU sur l'avenir institutionnel d'un territoire (article « Macron ferme la porte à un dialogue sur la Polynésie sous l'égide de l'ONU », présent dans le même lot). Atteinte à la fiabilité (priorité 1). CAUSE NON ÉTABLIE (artefact inaccessible). Hypothèses : (a) dédup : `dedup.deduplicate` garde le titre le plus long mais le résumé du 1er article, ou la fusion inter-zones (`dedup_inter_zones`) a rapproché deux événements différents ; (b) repli `guard_events` : « si le résumé LLM est vidé, on reprend `src.resume` » avec `best_source` mal apparié. À reproduire avec `latest.json` + log « Déduplication » et à corriger : (1) exiger qu'un résumé de repli recoupe le titre de l'événement (`overlap_ratio(resume, titre)`), sinon null ; (2) ne fusionner deux articles que s'ils partagent des entités rares, pas seulement une similarité de titre.
4. **Journal** : le mot « groq » est masqué en `***` dans les logs (« actu_france=*** ») : une valeur de secret ou de variable égale à `groq` ; sans gravité mais gênant pour lire les logs.

## Non vérifié faute d'accès à l'artefact
Mode et contenu de la science (fusion FR/EN, « Garde-fou science : N phrase(s) retirée(s) »), lisibilité de l'article ; `derniere_mise_a_jour` / `debut_run` ; CNRS et ESPN NBA (décision de suppression en attente) ; absence/présence de 429 OpenRouter ; entonnoir complet (France 99 bruts -> 77 uniques -> 34 retenus ; Monde 98 -> 72 -> 34 : lu dans le log).

## Prochaines étapes proposées
1. Récupérer l'artefact (hôte autorisé) pour clore la vérification de la science et de l'horodatage.
2. Partie C sport : points du défaut 1.
3. Défaut 3 (résumé sans rapport) : priorité haute, à traiter avant la fusion `dev` -> `main`.
4. Défaut 2 (liste de fréquence anglaise).
5. Fusion `dev` -> `main` seulement après accord de l'utilisateur et résolution du défaut 3.
