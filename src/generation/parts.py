"""Les PARTIES du briefing confiées chacune à un appel LLM (cf. config/llm_plan.yaml).

  appel 1 : actu_france (+ citation), actu_monde, marches, anglais
  appel 2 : science_a, science_b (2 moitiés du même article), sport

`build_parts()` fabrique les objets Part (prompt + schéma + budget) ; `merge_results()` réinjecte
les réponses dans le briefing de repli (chaque partie qui échoue garde son contenu brut).
Le moteur qui exécute tout cela est llm_orchestrator.py ; les règles éditoriales (cahier §11,
§14) sont dans _REGLES_COMMUNES : elles s'appliquent à TOUTES les parties rédigées.
"""
from __future__ import annotations

import difflib
import logging
import re

from .llm_orchestrator import Part, PartResult, looks_like_leak
from .citations import pick_citation
from .actu_guard import guard_events, guard_marches
from .science_guard import guard_science_article
from .anglais_guard import filtrer_mots
from . import sport_format

logger = logging.getLogger("morning_briefing.generation")

# --- budgets ---------------------------------------------------------------------------------
# Groq (gpt-oss-120b) est limité à 8 000 tokens/minute : prompt + sortie doivent tenir dans cette
# fenêtre (~3 caractères = 1 token). 12 000 caractères de prompt (~4 000 tokens) + 1 500 de
# sortie = OK. En cas de rognage, RETRY_CHARS est la 2e tentative du même fournisseur.
PROMPT_CHARS = 12_000
RETRY_CHARS = 4_000
PLANCHER_ACTUALITE = 2          # on ne réduit jamais une zone sous 2 événements (cahier §4)

TOKENS_ACTU = 1500
TOKENS_MARCHES = 1200
TOKENS_SPORT = 900
TOKENS_ANGLAIS = 900
TOKENS_SCIENCE_MOITIE = 2200    # ~1 000 mots par moitié ; le raisonnement de Groq est réglé "low"
TOKENS_SCIENCE_COMPLET = 3000   # mode "découverte" (un seul appel)

_REGLES_COMMUNES = """RÈGLES ABSOLUES (à respecter strictement) :
1. Utilise UNIQUEMENT les informations fournies dans les données ci-dessous. N'invente jamais un
   fait, un chiffre, une explication ni une source que tu ne peux pas justifier avec ces données.
2. Style : clair, factuel, sans sensationnalisme, sans opinion politique, sans exagération, en
   français.
3. Respecte le statut de vérification fourni pour chaque événement : si \"information_rapportee\",
   commence la phrase par \"Selon [source], ...\" ; si \"fait_confirme\", formule-le normalement.
   Les conséquences possibles sont toujours distinguées des faits et jamais présentées comme
   certaines.
4. Ne remplis pas artificiellement : peu d'événements réellement importants = peu d'éléments.
5. Réponds STRICTEMENT en JSON valide conforme au schéma donné, sans texte avant/après, sans
   balises markdown autour du JSON.
6bis. FAITS DU TEXTE UNIQUEMENT : \"resume\" ne contient que des faits présents dans le titre/résumé
   fourni. N'ajoute ni date, ni chiffre, ni fonction (« ancien », « actuel »), ni « première fois »,
   ni « les autorités n'ont pas commenté », ni contexte tiré de ta mémoire. N'écris AUCUN nom propre
   (personne, institution, lieu) qui ne figure pas mot pour mot dans le titre/résumé fourni : ne
   « complète » jamais un nom de mémoire (ex. n'écris pas un autre prénom/dirigeant que celui du texte).
   Un contrôle automatique supprime toute phrase contenant un élément absent des données. \"pourquoi_important\" : une phrase
   fondée sur les données, sinon null. \"consequences\" : null sauf si les données en parlent."""

_SCHEMA_EVENT = ('{\"titre\": str, \"resume\": str, \"pourquoi_important\": str, '
                 '\"consequences\": str|null, \"statut\": str, \"sources\": [str]}')

SYSTEM_ACTU_FRANCE = f"""Tu es le rédacteur d'un briefing matinal personnel en français. Tu rédiges ICI
uniquement l'actualité FRANCE (le monde, les marchés, le sport et la science sont générés
séparément par d'autres appels : ne les mentionne pas).

{_REGLES_COMMUNES}
6. Pour chaque actualité, réponds implicitement à Quoi / Où / Quand / Pourquoi c'est important ;
   pour les sujets complexes, ajoute les conséquences possibles (\"consequences\") ou null.
7. N'écris AUCUNE citation : elle est ajoutée automatiquement par le programme.

SCHÉMA JSON ATTENDU :
{{
  \"actualite_france\": [{_SCHEMA_EVENT}]
}}"""

SYSTEM_ACTU_MONDE = f"""Tu es le rédacteur d'un briefing matinal personnel en français. Tu rédiges ICI
uniquement l'actualité MONDE (géopolitique, conflits, diplomatie, catastrophes, décisions
internationales). La France, les marchés, le sport et la science sont générés séparément.

{_REGLES_COMMUNES}
6. Pour chaque actualité, réponds implicitement à Quoi / Où / Quand / Pourquoi c'est important ;
   pour les sujets complexes, ajoute les conséquences possibles (\"consequences\") ou null.

7. \"pourquoi_important\" n'a AUCUNE obligation de lien avec la France : n'invente pas d'angle
   français ; si les données ne donnent pas l'enjeu, mets null.

SCHÉMA JSON ATTENDU :
{{
  \"actualite_monde\": [{_SCHEMA_EVENT}]
}}"""

SYSTEM_MARCHES = f"""Tu es le rédacteur de la section MARCHÉS FINANCIERS d'un briefing matinal en
français. Tu rédiges UNIQUEMENT cette section (actualité, sport, science : autres appels).

{_REGLES_COMMUNES}
6. Pour chaque mouvement de \"donnees_marches.mouvements_significatifs\", cherche une cause dans
   \"actualite_economie_contexte\" (et, si pertinent, dans \"titres_france\"/\"titres_monde\") : événement,
   annonce, donnée macro, contexte géopolitique qui l'explique raisonnablement. Si tu en trouves
   une, résume-la en une courte phrase dans \"explication\". Sinon \"explication\": null -- ne
   répète PAS la variation chiffrée en guise d'explication et n'invente JAMAIS une cause.
7. \"resume_court\" = une ou deux phrases de CONTEXTE (ce qui se passe et pourquoi, si connu),
   jamais une énumération d'indices et de pourcentages (ils sont affichés à part).

SCHÉMA JSON ATTENDU :
{{
  \"marches\": {{
    \"resume_court\": str,
    \"mouvements_notables\": [{{\"nom\": str, \"variation_pct\": float, \"explication\": str|null}}]
  }}
}}"""

SYSTEM_SPORT = f"""Tu es le rédacteur de la section SPORT d'un briefing matinal en français. Tu rédiges
UNIQUEMENT cette section (actualité, marchés, science : autres appels). Elle couvre TOUS les sports,
sans préférence pour un sport, une équipe ou un pays : tu traites seulement ce qui figure dans les données.

{_REGLES_COMMUNES}
6. Une courte phrase factuelle par élément fourni (résultat, classement significatif, blessure,
   transfert, record). Les titres peuvent être en anglais : traduis-les, sans rien ajouter. Ne fais pas
   de compte rendu exhaustif et ne regroupe pas des éléments sans rapport.
7. \"sport\" = nom du sport en français, en minuscules (ex. \"football\", \"tennis\"), repris des données.
8. Si les données ne contiennent aucun élément : \"items\": [].

SCHÉMA JSON ATTENDU :
{{
  \"sport\": {{\"items\": [{{\"sport\": str, \"texte\": str}}]}}
}}"""

SYSTEM_ANGLAIS = f"""Tu es un professeur d'anglais qui aide un francophone de bon niveau (visé : B2 vers C1) à
progresser à partir d'un court extrait du New York Times fourni ci-dessous (titre + résumé, en
anglais). Tu rédiges UNIQUEMENT cette section.

RÈGLES ABSOLUES (à respecter strictement) :
1. \"traduction_titre\" et \"traduction_resume\" : traduction française FIDÈLE et naturelle. N'ajoute,
   ne déduis et n'invente AUCUN fait absent du texte anglais fourni. Attention aux faux amis et aux
   termes politiques : \"centrist\" = \"centriste\" (jamais \"centré\"), \"to resume\" = \"reprendre\",
   \"eventually\" = \"finalement\", \"actually\" = \"en réalité\", \"to attend\" = \"assister à\".
2. \"mots_importants\" : 4 à 8 mots ou expressions anglaises COPIÉS tels quels du titre ou du résumé
   (jamais un mot absent du texte). Choisis du vocabulaire de niveau B2/C1 : verbes à particule,
   collocations, termes politiques/économiques précis, mots à faux ami. EXCLUS les mots que tout
   apprenant connaît (president, prime minister, government, lawyer, politician, election, police,
   court, war, company, market, country, leader, etc.). Si le texte offre moins de 4 mots
   intéressants, n'en donne que 2 ou 3 : mieux vaut peu de mots utiles que des mots triviaux.
   Pour chacun : \"mot\" (tel qu'il apparaît), \"traduction\" (sens exact DANS CE CONTEXTE, en
   français, avec la nature du mot si utile), \"exemple\" (UNE phrase anglaise naturelle de niveau
   B2, différente de la phrase du texte, qui montre l'usage typique du mot ; cette phrase peut être
   inventée : c'est un exemple de langue, pas un fait d'actualité, et elle ne doit citer aucune
   personne réelle).
3. \"niveau\" : le niveau CECRL du texte pour un apprenant francophone, parmi \"B1\", \"B2\", \"C1\", \"C2\".
4. Réponds STRICTEMENT en JSON valide conforme au schéma donné, sans texte avant/après, sans
   balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
{{
  \"traduction_titre\": str,
  \"traduction_resume\": str,
  \"mots_importants\": [{{\"mot\": str, \"traduction\": str, \"exemple\": str}}],
  \"niveau\": str
}}"""

_TON_SCIENCE = """Ton d'une bonne revue de vulgarisation scientifique : précis, pédagogique,
compréhensible, sans sensationnalisme, sans déformer les connaissances pour simplifier.
RÈGLES ANTI-INVENTION (strictes, un contrôle automatique supprime les phrases fautives) :
- Tu disposes UNIQUEMENT du titre et du résumé d'un article (champ science_source). Tout nombre,
  pourcentage, date, nom de chercheur, d'institution, d'étude ou de revue doit figurer dans ce champ ;
  sinon NE L'ÉCRIS PAS (pas de « environ », pas d'ordre de grandeur de mémoire).
- Tu peux expliquer les mécanismes par des connaissances scientifiques de manuel, sans chiffre.
- Si la source ne donne pas de résultats chiffrés, la section « Données et résultats » dit simplement
  que le résumé disponible n'en précise pas, et renvoie à l'article source.
- N'écris aucune phrase de transition interne (« fin de la moitié A », « la suite abordera »).
- Titres de section : « ## Titre » sans numéro ni gras. Si un point est incertain, dis-le."""

_PLAN_ARTICLE = """PLAN DE L'ARTICLE (10 sections, écrit en DEUX moitiés par deux rédacteurs différents) :
  Moitié A : 1. Introduction  2. Pourquoi le sujet est important  3. Explication du phénomène
             4. Fonctionnement / mécanismes
  Moitié B : 5. Données et résultats scientifiques  6. Ce que les scientifiques savent
             7. Ce qui reste incertain  8. Limites et controverses éventuelles  9. Conclusion
             10. Sources (NE PAS l'écrire : la section Sources est ajoutée automatiquement par le programme)"""

SYSTEM_SCIENCE_A = f"""Tu es le rédacteur de la section science d'un briefing matinal en français. Tu écris
la MOITIÉ A d'un article pédagogique approfondi (~5 minutes de lecture pour cette moitié).

{_PLAN_ARTICLE}

Tu écris UNIQUEMENT les sections 1 à 4, chacune avec un titre markdown de niveau 2 (## ...). Un
autre rédacteur écrit les sections 5 à 10 en parallèle : ne les écris pas, ne conclus pas, ne
résume pas l'article, et termine ta moitié sur les mécanismes (sans phrase de conclusion).
{_TON_SCIENCE}
FORMAT DE SORTIE : du texte markdown SIMPLE (pas de JSON, pas de bloc de code, aucune phrase
d'introduction ni de commentaire sur ta réponse). La PREMIÈRE ligne est exactement :
TITRE: <titre de l'article>
puis une ligne vide, puis les sections."""

SYSTEM_SCIENCE_B = f"""Tu es le rédacteur de la section science d'un briefing matinal en français. Tu écris
la MOITIÉ B d'un article pédagogique approfondi (~5 minutes de lecture pour cette moitié).

{_PLAN_ARTICLE}

Tu écris UNIQUEMENT les sections 5 à 10, chacune avec un titre markdown de niveau 2 (## ...). Un
autre rédacteur écrit les sections 1 à 4 en parallèle (introduction, importance, phénomène,
mécanismes) : ne les répète pas, n'écris pas d'introduction générale, suppose que le lecteur les
vient de lire. Commence directement par la section 5. Sois particulièrement rigoureux sur la
frontière entre ce qui est établi, ce qui est incertain et ce qui est débattu.
{_TON_SCIENCE}
FORMAT DE SORTIE : du texte markdown SIMPLE (pas de JSON, pas de bloc de code, aucune phrase
d'introduction ni de commentaire). Ne mets PAS de ligne TITRE. Commence directement par « ## 5. »."""

SYSTEM_SCIENCE_DECOUVERTE = f"""Tu es le rédacteur de la section science d'un briefing matinal en français.
Rédige un article COURT sur la découverte majeure fournie : ce qui a été trouvé, par qui, pourquoi
c'est important, ce qui reste incertain. Vérifie que l'importance n'est pas exagérée.
{_TON_SCIENCE}
FORMAT DE SORTIE : du texte markdown SIMPLE (pas de JSON, pas de bloc de code, aucune phrase
d'introduction ni de commentaire). La PREMIÈRE ligne est exactement :
TITRE: <titre de l'article>
puis une ligne vide, puis l'article."""


# --- lecture des réponses TEXTE (science) -----------------------------------------------------
# Pourquoi du texte et pas du JSON : un long article markdown dans une chaîne JSON casse sans cesse
# (guillemets « " » non échappés, retours à la ligne : constaté avec ministral le 30/09).
def _strip_fence(t: str) -> str:
    t = t.strip()
    m = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", t, re.S)
    return m.group(1).strip() if m else t


def _texte_science(raw: str, avec_titre: bool, min_mots: int) -> tuple[str | None, str]:
    t = _strip_fence(raw or "")
    if looks_like_leak(t):
        raise ValueError("réponse de raisonnement / hors sujet (pas un article)")
    titre = None
    if avec_titre:
        m = re.match(r"\s*(?:#+\s*)?\**TITRE\**\s*:\s*(.+)", t, re.I)
        if not m:
            raise ValueError("ligne « TITRE: » manquante")
        titre = m.group(1).strip().strip('*"«» ').strip()
        t = t[m.end():].strip()
    if len(t.split()) < min_mots:
        raise ValueError(f"article trop court ({len(t.split())} mots, minimum {min_mots})")
    return titre, t


def parse_science_a(mode: str, min_mots: int):
    def _p(raw: str) -> dict:
        titre, texte = _texte_science(raw, True, min_mots)
        return {"science": {"mode": mode, "titre": titre, "contenu_markdown": texte}}
    return _p


def parse_science_b(raw: str) -> dict:
    _, texte = _texte_science(raw, False, 250)
    return {"contenu_markdown": texte}


# --- construction des prompts utilisateur ---------------------------------------------------
def _bg():
    from . import briefing_generator as bg   # import tardif : évite l'import circulaire
    return bg


def _zone_prompt(key: str, events: list[dict], is_monday: bool, max_chars: int, intro: str) -> str:
    bg = _bg()
    evs = [bg._light_event(e) for e in events]
    ser = lambda: bg._serialize({"jour_lundi_couvre_weekend": is_monday, key: evs})  # noqa: E731
    s = ser()
    while len(s) > max_chars and len(evs) > PLANCHER_ACTUALITE:
        evs.pop()          # listes triées par score décroissant : on retire les moins importants
        s = ser()
    return intro + "\n\n" + s


def _marches_prompt(analysed: dict, is_monday: bool, max_chars: int) -> str:
    bg = _bg()
    eco = [bg._light_event(e) for e in analysed.get("actualite_economie", [])]
    tf = [e["titre"] for e in analysed["actualite_france"]]
    tm = [e["titre"] for e in analysed["actualite_monde"]]

    def ser() -> str:
        return bg._serialize({
            "jour_lundi_couvre_weekend": is_monday,
            "donnees_marches": analysed["marches_data"],
            "actualite_economie_contexte": eco,
            "titres_france": tf, "titres_monde": tm,
        })
    s = ser()
    while len(s) > max_chars and (eco or tf or tm):
        for lst in (eco, tm, tf):        # on rogne d'abord l'économie (contexte), jamais les marchés
            if lst:
                lst.pop()
                break
        s = ser()
    return "Voici les données marchés et leur contexte pour le briefing de ce matin.\n\n" + s


def _sport_prompt(analysed: dict, is_monday: bool, max_chars: int) -> str:
    bg = _bg()
    sport = {cat: [e["titre"] for e in evs] for cat, evs in analysed["sport_events"].items()}
    ser = lambda: bg._serialize({"jour_lundi_couvre_weekend": is_monday, "sport": sport})  # noqa: E731
    s = ser()
    while len(s) > max_chars and any(sport.values()):
        cat = max(sport, key=lambda c: len(sport[c]))
        sport[cat].pop()
        s = ser()
    return "Voici les événements sportifs retenus pour le briefing de ce matin.\n\n" + s


def _science_prompt(science_topic: dict, moitie: str | None) -> str:
    bg = _bg()
    payload = {"science_mode": science_topic["mode"], "science_source": science_topic["contenu_source"]}
    tete = "Voici le sujet scientifique sélectionné pour le briefing de ce matin"
    if moitie:
        tete += f" (tu écris la moitié {moitie} de l'article ; le sujet est le MÊME pour les deux moitiés)"
    return tete + ".\n\n" + bg._serialize(payload)


def build_parts(analysed: dict, science_topic: dict, nyt_article: dict | None, is_monday: bool) -> dict[str, Part]:
    """Parties du jour. `science_b` n'existe qu'en mode \"approfondi\" ; `anglais` que si un
    article NYT a été trouvé."""
    bg = _bg()
    budgets = (PROMPT_CHARS, RETRY_CHARS)
    parts: dict[str, Part] = {
        "actu_france": Part(
            "actu_france", SYSTEM_ACTU_FRANCE,
            lambda mc: _zone_prompt("actualite_france", analysed["actualite_france"], is_monday, mc,
                                    "Voici les événements FRANCE collectés et vérifiés pour ce matin."),
            TOKENS_ACTU, ("actualite_france",), budgets),
        "actu_monde": Part(
            "actu_monde", SYSTEM_ACTU_MONDE,
            lambda mc: _zone_prompt("actualite_monde", analysed["actualite_monde"], is_monday, mc,
                                    "Voici les événements MONDE collectés et vérifiés pour ce matin."),
            TOKENS_ACTU, ("actualite_monde",), budgets),
        "marches": Part(
            "marches", SYSTEM_MARCHES, lambda mc: _marches_prompt(analysed, is_monday, mc),
            TOKENS_MARCHES, ("marches",), budgets),
    }
    if nyt_article:
        parts["anglais"] = Part(
            "anglais", SYSTEM_ANGLAIS,
            lambda mc: ("Voici l'extrait du New York Times à traduire et dont il faut extraire le "
                        "vocabulaire important pour ce matin.\n\n"
                        + bg._serialize({"titre_anglais": nyt_article["titre"],
                                         "resume_anglais": nyt_article["resume"]})),
            TOKENS_ANGLAIS, ("traduction_titre", "traduction_resume", "mots_importants"))
    if science_topic["mode"] == "approfondi":
        parts["science_a"] = Part("science_a", SYSTEM_SCIENCE_A, lambda mc: _science_prompt(science_topic, "A"),
                                  TOKENS_SCIENCE_MOITIE, ("science",), parser=parse_science_a("approfondi", 300))
        parts["science_b"] = Part("science_b", SYSTEM_SCIENCE_B, lambda mc: _science_prompt(science_topic, "B"),
                                  TOKENS_SCIENCE_MOITIE, ("contenu_markdown",), parser=parse_science_b)
    else:
        parts["science_a"] = Part("science_a", SYSTEM_SCIENCE_DECOUVERTE, lambda mc: _science_prompt(science_topic, None),
                                  TOKENS_SCIENCE_COMPLET, ("science",), parser=parse_science_a("decouverte", 80))
    parts["sport"] = Part(
        "sport", SYSTEM_SPORT, lambda mc: _sport_prompt(analysed, is_monday, mc),
        TOKENS_SPORT, ("sport",), budgets)
    return parts


# --- fusion des réponses dans le briefing de repli -------------------------------------------
NOTE_SUITE_ABSENTE = "*La suite de l'article n'a pas pu être générée ce matin.*"


def _normalise_marches(m: dict, brut: dict | None) -> dict:
    """Le site lit `mouvements_notables`. Un modèle peut recopier la clé d'entrée
    `mouvements_significatifs` (constaté le 30/09 avec ministral) : on la remappe, et si la liste est
    absente on garde les mouvements bruts (sans explication) plutôt que de les perdre."""
    m = dict(m)
    if "mouvements_notables" not in m:
        m["mouvements_notables"] = m.pop("mouvements_significatifs", None) or list((brut or {}).get("mouvements_notables", []))
    m.pop("mouvements_significatifs", None)
    m["mouvements_notables"] = [
        {"nom": x.get("nom"), "variation_pct": x.get("variation_pct"), "explication": x.get("explication")}
        for x in m["mouvements_notables"] if isinstance(x, dict)
    ]
    m.setdefault("resume_court", "")
    return m


def _garde_actu(events: list[dict], analysed: dict | None, cle: str) -> list[dict]:
    """Applique actu_guard aux événements rédigés (sans `analysed`, on ne touche à rien)."""
    if not analysed or not isinstance(events, list):
        return events
    gardes, retirees = guard_events(events, analysed.get(cle) or [])
    if retirees:
        logger.warning("Garde-fou actualité (%s) : %d phrase(s) retirée(s) : %s", cle, len(retirees),
                       " | ".join(x[:80] for x in retirees[:8]))
    return gardes


def merge_results(resultat: dict, results: dict[str, PartResult], nyt_article: dict | None,
                  science_source: dict | None = None, analysed: dict | None = None) -> None:
    """Remplace, partie par partie, le contenu brut du briefing de repli par ce que les LLM ont
    rédigé. Une partie en échec garde son contenu brut (cf. cahier §21). Modifie `resultat`."""
    r = results
    # Citation : banque vérifiée, tirage par date (le LLM n'intervient plus, cf. citations.py).
    from datetime import datetime
    from zoneinfo import ZoneInfo
    resultat["citation"] = pick_citation(datetime.now(ZoneInfo("Europe/Paris")).date())
    if "actu_france" in r and r["actu_france"].ok:
        resultat["actualite"]["france"] = _garde_actu(
            r["actu_france"].body["actualite_france"], analysed, "actualite_france")
    if "actu_monde" in r and r["actu_monde"].ok:
        resultat["actualite"]["monde"] = _garde_actu(
            r["actu_monde"].body["actualite_monde"], analysed, "actualite_monde")
    if "marches" in r and r["marches"].ok:
        resultat["marches"] = guard_marches(
            _normalise_marches(r["marches"].body["marches"], resultat.get("marches")), analysed)
    if "sport" in r and r["sport"].ok:
        resultat["sport"] = sport_format.normaliser(r["sport"].body.get("sport"), analysed["sport_events"])

    if "anglais" in r and r["anglais"].ok and nyt_article:
        b = r["anglais"].body
        resultat["anglais"] = {
            "titre_anglais": nyt_article["titre"], "resume_anglais": nyt_article["resume"],
            "url": nyt_article["url"], "source": nyt_article["source"],
            "traduction_titre": b.get("traduction_titre"), "traduction_resume": b.get("traduction_resume"),
            "niveau": b.get("niveau"),
        }
        # Contrôles déterministes : mots triviaux/absents du texte retirés, traductions à piège corrigées.
        mots, stats = filtrer_mots(b.get("mots_importants", []), nyt_article["titre"], nyt_article["resume"])
        resultat["anglais"]["mots_importants"] = mots
        logger.info("Anglais : %d mots reçus -> %d retenus (%s)", stats["recus"], len(mots), stats)

    # Science : la moitié A est INDISPENSABLE (titre + introduction) ; sans elle on garde le repli,
    # jamais une moitié B orpheline. Sans la moitié B, on publie A avec une mention explicite.
    if "science_a" in r and r["science_a"].ok:
        sci = dict(r["science_a"].body["science"])
        contenu = str(sci.get("contenu_markdown", "")).strip()
        if "science_b" in r:
            if r["science_b"].ok:
                contenu += "\n\n" + str(r["science_b"].body["contenu_markdown"]).strip()
            else:
                contenu += "\n\n" + NOTE_SUITE_ABSENTE
        if science_source is not None:
            contenu, retirees = guard_science_article(contenu, science_source)
            sci["phrases_retirees_garde_fou"] = len(retirees)
            if retirees:
                logger.warning("Garde-fou science : %d phrase(s) retirée(s) (chiffres absents de la source) : %s",
                               len(retirees), " | ".join(x[:80] for x in retirees[:8]))
        sci["contenu_markdown"] = contenu
        resultat["science"] = sci

    # Phrase de synthèse : construite à partir des titres réellement publiés, sans appel LLM
    # supplémentaire ni risque d'invention.
    titres = []
    for zone in ("france", "monde"):
        lst = resultat["actualite"].get(zone) or []
        if lst and lst[0].get("titre"):
            titres.append(str(lst[0]["titre"]).rstrip(" ."))
    if len(titres) == 2 and difflib.SequenceMatcher(None, titres[0].lower(), titres[1].lower()).ratio() > 0.6:
        titres = titres[:1]        # même événement en tête des deux zones : une seule mention
    if titres and any(k in r and r[k].ok for k in ("actu_france", "actu_monde")):
        phrase = "À la une : " + " ; ".join(t.replace("EN DIRECT, ", "") for t in titres)
        resultat["meta"] = {"resume_1_phrase": (phrase[:217] + "…") if len(phrase) > 220 else phrase + "."}


def diagnostics(results: dict[str, PartResult]) -> dict:
    """Champs de diagnostic. `_bloc`/`_science`/`_anglais` restent présents pour le frontend
    existant (onglet Erreurs, cf. storage.save_briefing) ; `_parts` donne le détail par partie."""
    def _grp(names: list[str]) -> dict:
        rs = [results[n] for n in names if n in results]
        ok = [x for x in rs if x.ok]
        errs = [f"{x.name}[{x.error}]" for x in rs if x.error]
        return {"genere_par_llm": bool(ok),
                "provider": "+".join(sorted({x.provider for x in ok})) or None,
                "erreur": " | ".join(errs)[:400] or None}
    return {
        "_parts": {n: {"genere_par_llm": x.ok, "provider": x.provider, "erreur": x.error,
                       "essais_echoues": len(x.attempts)} for n, x in results.items()},
        "_bloc": _grp(["actu_france", "actu_monde", "marches", "sport"]),
        "_science": _grp(["science_a", "science_b"]),
        "_anglais": _grp(["anglais"]),
    }
