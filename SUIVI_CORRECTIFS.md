# Suivi des correctifs de contenu — À LIRE EN PREMIER pour reprendre le travail

> **03/10/2026 : tous les correctifs ci-dessous marqués « FAIT » ont été fusionnés dans `main` (commit 7c471ae, accord de l'utilisateur) ; `dev` a été réaligné dessus. Le premier run de production avec ce code est celui du lundi 05/10 à 06h10 : le vérifier (contenu du briefing + logs `Garde-fou`, `Marché`, `Sport:`) et corriger sur `dev` si besoin. En cas de régression grave : `git revert -m 1 7c471ae` sur `main`.**

Source des défauts : `ANALYSE_RUN_2026-10-01.md` (9 points). Le run du 02/10/2026 06:10 les a **reproduits à
l'identique** (techniquement 7/7 parties LLM OK ; le contenu est le problème) : CAC −3,0 % (variation sur 5 jours),
science avec chiffres/sources inventés, sport hors périmètre (foot féminin), basket vide, citation `null`,
Powell/Pike en double France/Monde. Contexte d'organisation : `DEV_WORKFLOW.md` (main = prod, dev = essais).

> **04/10/2026 : ces 4 correctifs (points 7, 8, 10, 11) sont FUSIONNÉS dans `main` (commit efc17b9, accord de l'utilisateur) ; premier run de production avec ce code = lundi 05/10 à 06h10. À vérifier ensuite sur le briefing publié et les logs (`Anglais :`, `Zone par contenu`, `Calendrier`, `Météo`) ; corriger sur `dev`. Régression grave : `git revert -m 1 efc17b9` sur `main`. L'anglais du jour n'a JAMAIS tourné avec un vrai LLM avant cette fusion.**
>
> (Historique) 03/10/2026 (soir) — 4 correctifs codés sur `dev` : anglais du jour, météo, affectation France/Monde par contenu, mention « rien d'intéressant » + prochain match au sport. 97 tests OK ; météo, zones et calendrier validés en réel par un Dev Test sans LLM ; l'anglais du jour reste à valider par un Dev Test AVEC LLM (un seul run suffit).

## Règles de travail (ne pas les enfreindre)
- On développe UNIQUEMENT sur `dev`. Jamais de commit de `docs/data/` ni `logs/` sur `dev`. Ne pas lancer `LLM probe` depuis `dev`.
- Test sans quota : `pip install -r requirements.txt pytest && python3 -m pytest -q tests` (tout est simulé, aucun réseau).
- Test réel : GitHub → Actions → **Dev Test** → Run workflow (branche `dev`) ; le résultat est un artefact téléchargeable,
  rien n'est publié. Il consomme les quotas LLM (Groq 8000 tokens/min, OpenRouter 50 req/j) : pas juste avant 06h10.
- Mise en production : fusion `dev` → `main` (le jeton n'a pas le droit de créer des Pull Requests : fast-forward direct
  ou PR faite par l'utilisateur dans l'interface GitHub), seulement après un Dev Test satisfaisant et l'accord de l'utilisateur.
- Priorité du projet : fiabilité > tout. En cas de doute, ne pas afficher plutôt qu'inventer.

## État des 9 points (mis à jour le 03/10/2026 en fin de session)
| # | Point | État | Où |
|---|-------|------|----|
| 1 | Science : chiffres/sources inventés | FAIT sur dev, **validé en réel** (Dev Test 03/10 : 2 phrases retirées, Sources par le code, titres propres) | `src/generation/science_guard.py`, tests `test_science_guard.py` |
| 2 | Marchés : variation sur 5 jours | FAIT sur dev, **validé en réel** (CAC +0,79 % ; l'ancienne base `chartPreviousClose` aurait donné ≈ −2 %) | `compute_session_change()` dans `src/collecte/markets.py` |
| 2b | Marchés : explication inventée (« dépenses de défense russe » → Nasdaq) | FAIT sur dev, **validé en réel** (4e run : explications null + phrase « Aucune cause fiable… ») | `guard_marches()` dans `src/generation/actu_guard.py` : explication gardée seulement si ≥ 50 % de ses mots sont dans les articles économie ; variations imposées par les données ; sinon « Aucune cause fiable… » |
| 3 | Actu : ajouts non sourcés | FAIT sur dev (partiel) | `guard_events()` (actu_guard.py) : phrases à nombre/marqueur (« ancien », « première fois »…) absent de la source retirées ; `consequences` et `pourquoi_important` non étayés préfixés « Hypothèse : » ; statut imposé par le code. Limite : heuristique lexicale, ne détecte pas tout |
| 4 | Doublons France/Monde | FAIT sur dev, **validé en réel** (6 événements fusionnés) | `merge_zones()` dans `src/analyse/dedup.py`, appelée dans `main.py` |
| 5 | Sport hors sujet, basket absent | FAIT sur dev, **vu en réel** (Dev Test 03/10 : 4 retenus = 2 foot Bleus/Italie, 1 basket, 1 autre ; foot féminin écarté). WNBA écartée ensuite (commit suivant), à revérifier | `src/analyse/sport_scoring.py` (périmètre §6, quota par catégorie, Spurs, foot féminin écarté via `sport.inclure_feminin` absent = false). NB : bug découvert : `dedup` ne recopiait pas `equipe_prioritaire`, le bonus Spurs ne s'appliquait jamais |
| 6 | Citation toujours `null` | FAIT sur dev, **vu en réel** (Pascal, Pensées 1670) | `config/citations.json` (22 citations avec œuvre+année) + `src/generation/citations.py` ; le LLM n'écrit plus de citation |
| 7 | Anglais du jour (niveau, « centrist ») | FAIT sur dev (tests OK, **non vérifié en réel**) | `src/generation/anglais_guard.py` (filtre mots faciles/absents du texte/doublons, glossaire de traductions imposées, score de sélection B2/C1) ; prompt `SYSTEM_ANGLAIS` (parts.py) ; `select_nyt_article` choisit par vocabulaire soutenu ; tests `test_anglais_guard.py` |
| 8 | Météo (code instantané, évolution jour) | FAIT sur dev, **validé en réel** (4 villes OK, périodes matin/après-midi/soir, « couvert » au lieu de « bruine forte » à 0 mm) | `src/collecte/weather.py` réécrit : prévisions horaires, périodes matin/après-midi/soir, description de la zone sur les 4 villes, alertes (rafales ≥ 60, pluie ≥ 20 mm, chaleur ≥ 35, gel), codes WMO ajoutés, code pluie sans pluie mesurée → « couvert » ; `resume` construit par le code ; frontend `renderSectionMeteo` ; tests `test_weather.py` |
| 9 | Divers (`resume_1_phrase` tronqué, CNRS, ESPN) | À FAIRE | `merge_results` (couper à la phrase entière) |
| 10 | Affectation France/Monde par contenu | FAIT sur dev, **validé en réel** (Dev Test sans LLM : 21 items France → Monde, 3 Monde → France, réaffectations plausibles ; à relire à l'œil au prochain run) | `src/analyse/zones.py` (`assigner_zones`, appelée dans `main.py` AVANT la dédup) : marqueurs France vs étranger (titre ×2, résumé ×1), réaffectation si écart ≥ 2, sinon zone du flux ; NYT reste en Monde ; `raw` non modifié. Prompt Monde : plus de lien France obligatoire dans `pourquoi_important` ; tests `test_zones.py` |
| 11 | Sport : « rien d'intéressant » + prochain match | FAIT sur dev, **validé en réel** (Dev Test sans LLM du 03/10 : prochain football = Lens – Lyon, prochain basket = Spurs – Atlanta Hawks ; la plage `dates=A-B` d'ESPN renvoie HTTP 400, le code retombe sur une requête par jour qui fonctionne) | `src/collecte/calendrier.py` (API publique ESPN scoreboard, config `calendrier:` dans config.yaml), appelée dans `main.py` après la génération ; ajoute `sport.rien_a_signaler` et `sport.prochains_matchs` ; frontend `renderSectionSport` ; tests `test_calendrier.py` |

## Session du 05/10/2026 — correctifs de SÉLECTION sur `dev` (sans LLM, tests sans réseau uniquement)
Point de départ : `dev` réaligné sur `main` (84f1dc0, fast-forward). Rapport source : `ANALYSE_RUN_2026-10-05.md`
(numéros #5, #6, #7 ci-dessous = numéros de ce rapport). **Rien n'est validé en réel** : aucun Dev Test lancé, aucun LLM appelé.

| # rapport | Point | État | Où |
|---|---|---|---|
| 5 | Scoring à sous-chaînes (« mort » = 9 pour un décès d'écrivain) | FAIT sur dev, tests OK, non validé en réel | `src/analyse/scoring.py` réécrit : mots ENTIERS (regex), thèmes majeurs/importants, MALUS (tribune, interview, fait divers, culture, tribune collective « par 500 anciens… »), expressions figurées neutralisées (« guerre ouverte »), +1 si le titre annonce un résultat, départage par nb de sources puis fraîcheur. `tests/test_scoring.py` |
| 6 | Brésil = avant-scrutin au lieu des résultats ; 5 emplacements pris par un seul sujet | FAIT sur dev, tests OK | bonus « résultat » (ci-dessus) + `src/analyse/diversite.py::selectionner_diversifie` : au plus 2 événements par entité/sujet et par zone, complément si la zone est trop courte. Branché dans `src/main.py` à la place de `[:max_par_zone]` |
| 7 | Doublon Christa Pike, classé France | FAIT sur dev, tests OK | `diversite.py::fusionner_par_entites` (>= 2 entités RARES communes, entité > 3 titres = banale) ; `zones.py` : comparaison SANS ACCENTS (« Etats-Unis » ne matchait pas « états-unis »), marqueurs États US / Ebola-RDC / Lettonie / Lula-Bolsonaro. `tests/test_diversite.py` |

Limites connues / à regarder au prochain Dev Test : (a) seuil des malus et des listes de mots calibrés à la main sur UN run — vérifier que les actus
internationales importantes ne sont pas écartées (log « Entonnoir actualité », titres retenus) ; (b) une nécrologie de personnalité culturelle
tombe à ~3-4/10 (volontaire, modifiable dans `MALUS_CULTURE`) ; (c) la diversité utilise des noms propres de TITRES : un titre sans nom propre n'est pas
limité ; (d) les points 8 (sport/NBA), 9-10-12 du rapport (OpenRouter vide, calendrier 400, horodatage) et les points de FIABILITÉ (#1 nom propre inventé, #2 explication de marché,
#3 science en mode découverte, #4 « Hypothèse : ») NE SONT PAS TRAITÉS : l'utilisateur a demandé de faire la sélection d'abord.
Règle : ne pas lancer de LLM ni de Dev Test sans demande de l'utilisateur.

### Session du 05/10/2026 (suite) — correctifs de FIABILITÉ sur `dev` (sans LLM, tests hors réseau, **non validés en réel**)
| # rapport | Point | État | Où |
|---|---|---|---|
| 1 | Nom propre inventé (« Olaf Scholz » au lieu de Merz) | FAIT sur dev, tests OK | `src/generation/actu_guard.py::unsupported_names` : tout mot capitalisé HORS début de phrase doit figurer dans titre+résumé source (sans accents/casse), sinon la phrase est retirée (`clean_text`). Liste `_NOMS_TOLERES` pour les mots génériques (France, Europe, gouvernement…). Règle ajoutée aussi au prompt (`parts.py`, 6bis). |
| 2 | Explication de marché sans lien (budget nucléaire → DAX/Euro Stoxx) | FAIT sur dev, tests OK | `actu_guard.py::explication_etayee` : l'explication doit être étayée par UN article économique qui (a) mentionne ce marché (alias `_ALIAS_MARCHE`) ou la Bourse (`_GENERIQUE_MARCHE`) et (b) recouvre >= 50 % de ses mots. Remplace l'ancien recouvrement sur le lot global. |
| 3 | Science « découverte » sur un simple résumé RSS (Floride/vaccination) | FAIT sur dev, tests OK | `briefing_generator.py::decouverte_qualifiee` + `select_science_topic` : vocabulaire de recherche, pas de politique dans le titre, résumé >= 200 car., >= 2 sources OU source primaire (CNRS, Nature… ; « Le Monde Sciences » n'en est pas une). Sinon mode « approfondi » (candidat de recherche non politique). |
| 4 | « Hypothèse : » sur tous les `pourquoi_important` | FAIT sur dev, tests OK | `actu_guard.py::guard_events` : étayé (recouvrement >= 40 %, `PI_MIN_OVERLAP`) -> conservé tel quel ; sinon ou formule creuse (`_CREUX`) -> `null` (le site n'affiche rien). Les `consequences` gardent le préfixe « Hypothèse : » (cahier §14). |

**Fusion dev → main faite le 05/10/2026 (commit 008fbf3, fast-forward, à la demande de l'utilisateur, SANS Dev Test préalable).** Le premier run réel de ces correctifs est le run de production du 06/10/2026 à 06h10 : à analyser en priorité (log « Entonnoir actualité », titres retenus, phrases retirées par les garde-fous, mode science choisi, `pourquoi_important` souvent null = voulu). Si un défaut grave apparaît : corriger sur `dev`, ne pas toucher `main` directement ; retour arrière possible par `git revert` des commits 27149c8 et 008fbf3.

Limites : (a) le contrôle des noms propres est lexical (pas de vérification sémantique) et peut retirer une phrase légitime qui reformule un nom d'une autre façon — vérifier les phrases retirées dans le log (« phrases retirées ») au prochain Dev Test ; (b) en mode « approfondi » l'article reste fondé sur UN titre+résumé RSS (pas de liste de sujets pédagogiques tournante : non implémenté) ; (c) `pourquoi_important` sera souvent `null` : c'est voulu ;
(d) les points 8-12 du rapport (sport/NBA, OpenRouter vide, calendrier ESPN 400, horodatage, `resume_1_phrase` tronqué) restent À FAIRE.

## Autres constats du Dev Test du 03/10 (non traités)
- La zone France contient encore de l'international (ex. budget militaire russe, Corée du Nord) : les flux « Le Monde — Une » / Libération sont classés `france` par flux, pas par contenu. Les « pourquoi important » forcent un lien avec la France (maintenant marqués « Hypothèse »). Piste : affectation par contenu, ou prompt « pourquoi important » sans obligation de lien France.
- OpenRouter renvoie « Réponse vide » / 429 sur `gemma-4-31b-it:free` à chaque run (le secours NVIDIA fonctionne, ~30 s perdues).
- Le nom du fournisseur d'une partie apparaît masqué (`actu_france=***`) dans les logs GitHub : sans conséquence.
- Faux positifs du garde-fou science : voulu (fiabilité d'abord) ; la fourchette de phrases retirées est loggée en WARNING.

## Comment lire un Dev Test depuis un environnement sans accès à blob.core.windows.net
Les logs et l'artefact d'un run sont inaccessibles dans certains sandbox (hôte bloqué). Le workflow Dev Test publie donc un
résumé en **annotations** (`scripts/test_summary.py`) : `GET /repos/{o}/{r}/check-runs/{job_id}/annotations` (titres `1-log-marches`,
`2-log-garde-fous`, `3-briefing`, `4-science`). Déclencher : `POST /repos/{o}/{r}/actions/workflows/372349191/dispatches`
avec `{"ref":"dev","inputs":{"ref":"dev","no_llm":"false"}}` (le jeton a le droit Actions). Le workflow lance maintenant `pytest`
(les tests plain-function de `tests/` ne tournaient pas sous `unittest discover`).

## Détails utiles sur les deux correctifs faits
- **Marchés** : la cause (hypothèse du 01/10) est confirmée par la lecture du code : `chartPreviousClose` de l'endpoint Yahoo
  « chart » avec `range=5d` = clôture d'avant la plage. Le log de chaque marché écrit maintenant
  `cours / ref / var / meta.chartPreviousClose / previousClose` : au prochain Dev Test, **vérifier dans le log** que la variation
  ressemble à une séance (CAC ≈ ±1 %) et que `ref` est la clôture de la veille. Un champ `date_reference` est ajouté aux cotations.
  Non vérifié contre Yahoo en réel (pas d'accès réseau depuis le sandbox de développement).
- **Science** : le garde-fou retire toute phrase contenant un nombre « significatif » (≥ 2 chiffres, décimal ou %) absent du
  titre+résumé de la source. Appliqué à l'article du 02/10 : 9 phrases retirées sur ~2000 mots (le contenu inventé : 30–55 %,
  « 10 maladies », etc.). Effets de bord connus : faux positifs rares (ex. « 24h/24 » retiré) et article plus court ; c'est voulu
  (fiabilité d'abord). Le nombre de phrases retirées est publié dans `science.phrases_retirees_garde_fou` et loggé (WARNING).
  La section « Sources » est désormais construite par le code (lien réel de l'article) ; les titres sont normalisés (`## Titre`).
  Limite de fond NON résolue : une source = un résumé RSS de quelques lignes ; l'article « approfondi » reste donc largement
  pédagogique/général. Piste (point 1e de l'analyse) : liste de sujets curés + sources primaires (Nature, CNRS, Inserm).

## Prochaine étape recommandée
1) Lire le Dev Test lancé sur le commit « citation du jour » (sport, citation, marchés, actu) ; corriger ce qui reste.
2) Si le contenu est satisfaisant : fusion `dev` → `main` **avec l'accord de l'utilisateur** (la production tourne à 06h10 en semaine).
   Avant la fusion, vérifier que `main` n'a pas de nouveaux commits « Briefing du… » en conflit (ils ne touchent que `docs/data` et `logs`).
3) Restent : point 9 (divers), puis fusion `dev` → `main` des points 7, 8, 10, 11 après vérification (accord de l'utilisateur).

## À vérifier au prochain Dev Test (points non validés en réel)
1. (VALIDÉ le 03/10, ne revérifier qu'en cas de régression) **Calendrier ESPN** : chercher dans les annotations les lignes `Calendrier football <slug>: N match(s)` ; si 0 partout, les `slug` de `config/config.yaml` (section `calendrier:`) ou le format du paramètre `dates=` sont à corriger. En cas d'échec le site dit seulement « Rien d'intéressant à signaler » (jamais de match inventé).
2. **Météo** : annotation `3c-meteo-anglais` → `periodes` (3 entrées), `resume` cohérent, plus de « bruine forte » sans pluie.
3. **Zones** : lignes `Zone par contenu: france -> monde | titre` ; vérifier qu'aucune réaffectation n'est absurde, ajuster `MARQUEURS_*` dans zones.py (faux positifs possibles sur les villes, ex. « Nice », « Rome »).
4. **Anglais** (nécessite un Dev Test AVEC LLM) : ligne `Anglais : N mots reçus -> M retenus`, vérifier que « centrist » → « centriste » et que les mots faciles ont disparu. Si M = 0 trop souvent, assouplir `MOTS_FACILES`.
- Un Dev Test `no_llm=true` suffit pour 1, 2 et 3 (aucun quota LLM consommé) ; seul le point 4 demande un run complet.

## Écart connu (résolu le 03/10 soir, voir point 11)
- Décision de l'utilisateur du 01/10 : quand le sport n'a rien d'intéressant, le briefing le dit et indique le prochain match intéressant → codé (point 11).
- Marchés : quand aucune cause fiable n'est trouvée, le site affiche « Aucune cause fiable n'a pu être établie… » (volontaire, cahier §5 : ne pas inventer). Pour avoir plus d'explications il faudrait enrichir le contexte économie (plus de flux/articles), pas assouplir le garde-fou.
- Quotas LLM : le Dev Test consomme les mêmes clés que la prod. 4 runs complets ont été faits le 03/10 (samedi) ; ne pas en relancer inutilement.

## Session du 05/10/2026 (suite 4) — Sport généraliste, indépendant de l'utilisateur (branche `dev` uniquement)

**Demande** : les articles sport ne doivent plus dépendre de l'utilisateur ; le site cherche des informations sur TOUT type de sport.
`main` n'est PAS modifiée (fusion seulement avec l'accord de l'utilisateur). Aucun LLM ni Dev Test lancé : 128 tests OK, rien validé en réel.

**Ce qui a changé**
- `config/config.yaml` : section `sport:` = liste plate `sources` (`{name, url, sport?}`) + `max_par_sport: 2`. Plus de `equipes_prioritaires`, `ligues_suivies`, `sports_conditionnels`, `mot_cle_france`. 14 flux : L'Équipe (11 sports), ESPN NBA, ESPN Top Headlines, BBC Sport. **Flux NON VÉRIFIÉS** (jamais testés, pas de réseau dans le sandbox) : L'Équipe Athlétisme/Formule 1/Golf, ESPN Top Headlines, BBC Sport -> lire `sources_rss_en_erreur` au prochain run ; corriger l'URL ou retirer le flux, sans toucher au code.
- `src/collecte/sports.py` : renvoie une LISTE d'items, chacun avec `sport` (indice du flux, sinon détecté par mots-clés). Plus de filtre « France », plus de drapeau `equipe_prioritaire`.
- `src/analyse/sport_scoring.py` : `detecter_sport()`, `score_sport_event()` (importance indépendante du sport/équipe/pays : grande compétition, résultat, finale, record, blessure/transfert ; malus anecdote/people/interview), `select_sport()` (tri par score, puis nb de sources, puis fraîcheur ; max `max_par_sport` par sport ; max `seuils.max_sport_total` au total, 4 par défaut). Plus de malus féminin, plus de bonus Spurs.
- `src/main.py` : dédup PAR sport, puis `select_sport`. `analysed["sport_events"]` reste un dict `{sport: [événements]}` (clés libres).
- `src/generation/sport_format.py` (nouveau) : format de sortie `sport = {"items": [{"sport", "texte"}]}`, repli sans LLM, normalisation tolérante de la réponse LLM (accepte l'ancien format, borne au nombre d'événements retenus).
- `src/generation/parts.py` : `SYSTEM_SPORT` généraliste (traduit les titres anglais, n'ajoute rien, `items: []` si rien).
- `src/collecte/calendrier.py` : « prochaines affiches » neutres (clubs phares européens, franchises NBA phares ; `equipe_nationale` vide par défaut = aucune préférence). Affichées seulement si AUCUN item sport n'est retenu : `sport.rien_a_signaler` (bool) et `sport.prochains_matchs` (liste, chaque entrée avec `sport`).
- `docs/app.js` : rendu par sport depuis `items` ; les anciens briefings (football/basketball/natation/autres, `prochains_matchs` en objet) restent lisibles.
- Tests : `tests/test_sport_scoring.py` et `tests/test_calendrier.py` réécrits ; `tests/test_llm_orchestrator.py` ajusté.

**À vérifier au prochain Dev Test (avec LLM)**
1. Les 14 flux répondent (annotations du résumé, `sources_rss_en_erreur`) ; combien d'articles par sport.
2. Les sports retenus sont variés (pas 4 items de football), les titres anglais sont bien traduits en français, aucun fait ajouté.
3. Détection du sport par mots-clés : surveiller les « autres » (mots-clés dans `SPORTS` de `sport_scoring.py`) et les faux positifs (ex. « hand » ou « ski » dans un autre mot).
4. Si rien n'est retenu : phrase « Rien d'intéressant » + affiches (le calendrier ESPN renvoyait HTTP 400 sur la plage de dates le 05/10 : le repli jour par jour existe, à confirmer).

**Limites connues** : le plafond global reste 4 items (décision du 24/09) ; l'importance est heuristique (mots-clés), pas sémantique ; les mots-clés sont en français + un peu d'anglais.
**Retour arrière** : `git revert` du commit de cette session sur `dev` (main inchangée).

### Fusion du 06/10/2026 (dev → main)
- Le run de production du 06/10 à 06h10 a validé les correctifs sélection + fiabilité (demande de l'utilisateur).
- `dev` (commit 8cfa890, sport généraliste : tous les sports, plus de préférences Spurs / équipe de France, format `sport.items`, calendrier neutre) fusionné dans `main` par merge `--no-ff` ; 128 tests OK (`pip install -r requirements.txt pytest`, puis `python -m pytest -q tests`).
- Rien du volet sport n'a encore été vu en run réel : à contrôler au prochain run de 06h10 (flux sport non vérifiés : L'Équipe Athlétisme/Formule 1/Golf, ESPN Top Headlines, BBC Sport ; variété des sports ; titres anglais traduits ; mention « Rien d'intéressant »).
- Retour arrière : `git revert -m 1 <commit de fusion>` sur `main`.
- `dev` réaligné sur `main` après cette fusion.

## Session du 06/10/2026 — correctifs par PARTIE (réf. ANALYSE_RUN_2026-10-06.md)

### Partie A — SCIENCE (FAIT sur `dev`, sans LLM, non validé en réel)
Problème : Nobel de médecine couvert par 4 articles FR/EN non regroupés -> « une seule source non primaire » -> mode approfondi sur UN résumé RSS -> LLM complète avec des noms techniques inventés (ArchT, ChR2, AAV), fuites « le résumé indique… », « : » orphelin, section Données vide.
- `src/analyse/science_events.py` (NOUVEAU) : `fusionner_evenements_science` regroupe les articles qui partagent >= 3 racines RARES (5 premières lettres, sans accents : « neurones »/« neurons » -> « neuro »), FR comme EN. Garde `textes_sources` (titre+résumé de chaque source) et le résumé le plus long. Branché dans `main.py` juste après `dedup.deduplicate(sciences)`.
- `briefing_generator.py` : `decouverte_qualifiee` additionne les résumés de toutes les sources fusionnées (seuil 200 car.) ; `_sujet` transmet au rédacteur `textes_sources` (4 max, 700 car. chacun) et `liens_sources`.
- `science_guard.py` : (1) `remove_meta_leaks` retire les phrases sur « le résumé / l'extrait », les absolus non sourcés (« non invasif », « sans risque ») et les amorces vides (« Par exemple. ») ; (2) `remove_unsupported_terms` retire les phrases avec identifiants mixtes (ChR2, ArchT), sigles hors liste tolérée (AAV ; ADN/IRM/… tolérés) ou « Prénom Nom » absents de TOUTES les sources ; (3) `fix_orphan_colons` ; (4) `ensure_sections_not_empty` (Données vide -> phrase standard, autre section vide supprimée) ; (5) section Sources = un lien par source ; nombres autorisés = ceux de toutes les sources.
- `parts.py` : prompts anti-invention durcis (plus de nom de protéine/sigle/méthode de mémoire, interdiction de parler du « résumé »).
- Tests : `tests/test_science_events.py` (4), `tests/test_science_guard.py` (+7) ; 139 tests OK. Rejeu du garde-fou sur le vrai article du 06/10 : fuites, ChR2, ArchT, AAV retirés, « : » corrigé.
- LIMITES : le code ne peut pas détecter une affirmation fausse écrite en mots courants (« la lumière est non invasive » n'est attrapée que par mots-clés) ni un terme technique en minuscules (« tyrosine hydroxylase »). Le mode « approfondi » reste fondé sur des résumés RSS : seule une liste de sujets pédagogiques avec sources (non implémentée) résoudrait le fond. Seuil de fusion (3 racines rares) à surveiller : trop bas = fusions abusives, trop haut = doublons (voir log « Fusion sciences »).
- À VÉRIFIER au prochain Dev Test avec LLM : log « Fusion sciences », mode retenu (découverte/approfondi), « Garde-fou science : N phrase(s) retirée(s) », lisibilité de l'article.

### Parties suivantes (ordre convenu) : B `consequences`, C sport (après le run du 07/10), D calendrier/OpenRouter/horodatage, E divers.
