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

from .llm_orchestrator import Part, PartResult

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
   balises markdown autour du JSON."""

_SCHEMA_EVENT = ('{\"titre\": str, \"resume\": str, \"pourquoi_important\": str, '
                 '\"consequences\": str|null, \"statut\": str, \"sources\": [str]}')

SYSTEM_ACTU_FRANCE = f"""Tu es le rédacteur d'un briefing matinal personnel en français. Tu rédiges ICI
uniquement l'actualité FRANCE (le monde, les marchés, le sport et la science sont générés
séparément par d'autres appels : ne les mentionne pas) et la citation du jour.

{_REGLES_COMMUNES}
6. Pour chaque actualité, réponds implicitement à Quoi / Où / Quand / Pourquoi c'est important ;
   pour les sujets complexes, ajoute les conséquences possibles (\"consequences\") ou null.
7. Citation du jour : uniquement si tu es CERTAIN de l'authenticité de l'attribution (auteur ET
   contenu). Sinon \"citation\": null. Aucune citation d'attribution douteuse.

SCHÉMA JSON ATTENDU :
{{
  \"actualite_france\": [{_SCHEMA_EVENT}],
  \"citation\": {{\"texte\": str, \"auteur\": str}}|null
}}"""

SYSTEM_ACTU_MONDE = f"""Tu es le rédacteur d'un briefing matinal personnel en français. Tu rédiges ICI
uniquement l'actualité MONDE (géopolitique, conflits, diplomatie, catastrophes, décisions
internationales). La France, les marchés, le sport et la science sont générés séparément.

{_REGLES_COMMUNES}
6. Pour chaque actualité, réponds implicitement à Quoi / Où / Quand / Pourquoi c'est important ;
   pour les sujets complexes, ajoute les conséquences possibles (\"consequences\") ou null.

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
UNIQUEMENT cette section (actualité, marchés, science : autres appels).

{_REGLES_COMMUNES}
6. Une courte phrase factuelle par élément (résultat, classement significatif, blessure,
   transfert). Basket : niveau de détail supérieur pour les San Antonio Spurs si des données sont
   fournies. Ne fais pas de compte rendu exhaustif.
7. \"natation\" et \"autres\" : null s'il n'y a rien dans les données.

SCHÉMA JSON ATTENDU :
{{
  \"sport\": {{\"football\": [str], \"basketball\": [str], \"natation\": [str]|null, \"autres\": [str]|null}}
}}"""

SYSTEM_ANGLAIS = f"""Tu es un professeur d'anglais qui aide un francophone à apprendre l'anglais à
partir d'un court extrait du New York Times fourni ci-dessous (titre + résumé, en anglais). Tu
rédiges UNIQUEMENT cette section.

RÈGLES ABSOLUES (à respecter strictement) :
1. \"traduction_titre\" et \"traduction_resume\" : traduction française FIDÈLE. N'ajoute, ne déduis et
   n'invente AUCUN fait absent du texte anglais fourni.
2. \"mots_importants\" : 5 à 8 mots ou expressions anglaises TIRÉS du titre ou du résumé, utiles à
   apprendre (vocabulaire soutenu, faux-amis, expressions, termes d'actualité), pas de mots
   triviaux. Pour chacun : \"mot\" (tel qu'il apparaît), \"traduction\" (français), \"exemple\" (UNE
   phrase anglaise simple et courte ; cette phrase peut être inventée : c'est un exemple de
   langue, pas un fait d'actualité).
3. \"niveau\" : estimation honnête (ex. \"intermédiaire\", \"avancé\") pour un apprenant francophone.
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
compréhensible, sans sensationnalisme, sans déformer les connaissances pour simplifier. N'invente
aucune donnée chiffrée, aucune étude, aucun nom de chercheur : utilise les données fournies et des
connaissances scientifiques largement établies et non controversées sur ce sujet précis ; si un
point est incertain, dis-le."""

_PLAN_ARTICLE = """PLAN DE L'ARTICLE (10 sections, écrit en DEUX moitiés par deux rédacteurs différents) :
  Moitié A : 1. Introduction  2. Pourquoi le sujet est important  3. Explication du phénomène
             4. Fonctionnement / mécanismes
  Moitié B : 5. Données et résultats scientifiques  6. Ce que les scientifiques savent
             7. Ce qui reste incertain  8. Limites et controverses éventuelles  9. Conclusion
             10. Sources (uniquement celles fournies dans les données ; sinon écris que les sources
             détaillées sont à consulter dans la source indiquée)"""

SYSTEM_SCIENCE_A = f"""Tu es le rédacteur de la section science d'un briefing matinal en français. Tu écris
la MOITIÉ A d'un article pédagogique approfondi (~5 minutes de lecture pour cette moitié).

{_PLAN_ARTICLE}

Tu écris UNIQUEMENT les sections 1 à 4, chacune avec un titre markdown de niveau 2 (## ...). Un
autre rédacteur écrit les sections 5 à 10 en parallèle : ne les écris pas, ne conclus pas, ne
résume pas l'article, et termine ta moitié sur les mécanismes (sans phrase de conclusion).
{_TON_SCIENCE}
Réponds STRICTEMENT en JSON valide, sans texte avant/après, sans balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
{{\"science\": {{\"mode\": \"approfondi\", \"titre\": str, \"contenu_markdown\": str}}}}"""

SYSTEM_SCIENCE_B = f"""Tu es le rédacteur de la section science d'un briefing matinal en français. Tu écris
la MOITIÉ B d'un article pédagogique approfondi (~5 minutes de lecture pour cette moitié).

{_PLAN_ARTICLE}

Tu écris UNIQUEMENT les sections 5 à 10, chacune avec un titre markdown de niveau 2 (## ...). Un
autre rédacteur écrit les sections 1 à 4 en parallèle (introduction, importance, phénomène,
mécanismes) : ne les répète pas, n'écris pas d'introduction générale, suppose que le lecteur les
vient de lire. Commence directement par la section 5. Sois particulièrement rigoureux sur la
frontière entre ce qui est établi, ce qui est incertain et ce qui est débattu.
{_TON_SCIENCE}
Réponds STRICTEMENT en JSON valide, sans texte avant/après, sans balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
{{\"contenu_markdown\": str}}"""

SYSTEM_SCIENCE_DECOUVERTE = f"""Tu es le rédacteur de la section science d'un briefing matinal en français.
Rédige un article COURT sur la découverte majeure fournie : ce qui a été trouvé, par qui, pourquoi
c'est important, ce qui reste incertain. Vérifie que l'importance n'est pas exagérée.
{_TON_SCIENCE}
Réponds STRICTEMENT en JSON valide, sans texte avant/après, sans balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
{{\"science\": {{\"mode\": \"decouverte\", \"titre\": str, \"contenu_markdown\": str}}}}"""


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
                                  TOKENS_SCIENCE_MOITIE, ("science",))
        parts["science_b"] = Part("science_b", SYSTEM_SCIENCE_B, lambda mc: _science_prompt(science_topic, "B"),
                                  TOKENS_SCIENCE_MOITIE, ("contenu_markdown",))
    else:
        parts["science_a"] = Part("science_a", SYSTEM_SCIENCE_DECOUVERTE, lambda mc: _science_prompt(science_topic, None),
                                  TOKENS_SCIENCE_COMPLET, ("science",))
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


def merge_results(resultat: dict, results: dict[str, PartResult], nyt_article: dict | None) -> None:
    """Remplace, partie par partie, le contenu brut du briefing de repli par ce que les LLM ont
    rédigé. Une partie en échec garde son contenu brut (cf. cahier §21). Modifie `resultat`."""
    r = results
    if "actu_france" in r and r["actu_france"].ok:
        resultat["actualite"]["france"] = r["actu_france"].body["actualite_france"]
        resultat["citation"] = r["actu_france"].body.get("citation")
    if "actu_monde" in r and r["actu_monde"].ok:
        resultat["actualite"]["monde"] = r["actu_monde"].body["actualite_monde"]
    if "marches" in r and r["marches"].ok:
        resultat["marches"] = _normalise_marches(r["marches"].body["marches"], resultat.get("marches"))
    if "sport" in r and r["sport"].ok:
        resultat["sport"] = r["sport"].body["sport"]

    if "anglais" in r and r["anglais"].ok and nyt_article:
        b = r["anglais"].body
        resultat["anglais"] = {
            "titre_anglais": nyt_article["titre"], "resume_anglais": nyt_article["resume"],
            "url": nyt_article["url"], "source": nyt_article["source"],
            "traduction_titre": b.get("traduction_titre"), "traduction_resume": b.get("traduction_resume"),
            "mots_importants": b.get("mots_importants", []), "niveau": b.get("niveau"),
        }

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
