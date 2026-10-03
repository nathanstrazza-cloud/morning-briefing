"""Résumé lisible d'un Dev Test, émis en annotations GitHub (::notice::).

Pourquoi : les logs et l'artefact d'un run sont servis par un hôte (blob.core.windows.net) que le
sandbox de développement de l'IA ne peut pas joindre ; les annotations, elles, sont lisibles via
l'API `GET /repos/{o}/{r}/check-runs/{id}/annotations`. Usage : python scripts/test_summary.py test-output
"""
import glob
import json
import sys


LIMITE = 3500   # GitHub tronque les annotations vers 4 000 caractères : on découpe en morceaux numérotés


def emit(titre: str, lignes: list[str]) -> None:
    texte = "\n".join(lignes)
    morceaux = [texte[i:i + LIMITE] for i in range(0, len(texte), LIMITE)] or [""]
    for n, m in enumerate(morceaux[:6], 1):
        suffixe = f"-{n}" if len(morceaux) > 1 else ""
        msg = m.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title={titre}{suffixe}::{msg}")


def main(out: str) -> None:
    logs = sorted(glob.glob(f"{out}/logs/*.log"))
    texte = open(logs[-1], encoding="utf-8").read().splitlines() if logs else []
    emit("1-log-marches", [l for l in texte if "Marché " in l or "marches" in l.lower()][:20] or ["(aucune ligne marché)"])
    emit("2-log-garde-fous", [l for l in texte if "Garde-fou" in l or "inter-zones" in l or "Sport" in l or "Parties rédigées" in l
                              or "ERROR" in l or "Entonnoir" in l or "Zone par contenu" in l or "Affectation France" in l
                              or "Calendrier" in l or "Anglais :" in l or "Météo" in l][:60] or ["(rien)"])
    try:
        b = json.load(open(f"{out}/latest.json", encoding="utf-8"))["briefing"]
    except Exception as exc:  # noqa: BLE001
        emit("3-briefing", [f"latest.json illisible: {exc}"])
        return
    act = b.get("actualite") or {}
    emit("3a-sport-citation", ["SPORT: " + json.dumps(b.get("sport"), ensure_ascii=False),
                               "CITATION: " + json.dumps(b.get("citation"), ensure_ascii=False)])
    lignes = ["MARCHES: " + json.dumps(b.get("marches"), ensure_ascii=False)]
    for z in ("france", "monde"):
        for e in act.get(z) or []:
            lignes.append(f"ACTU {z} [{e.get('statut')}] {e.get('titre')}\n   resume={e.get('resume')}\n   pourquoi={e.get('pourquoi_important')}\n   conseq={e.get('consequences')}")
    emit("3b-actu", lignes)
    emit("3c-meteo-anglais", ["METEO: " + json.dumps(b.get("meteo"), ensure_ascii=False)[:2500],
                              "ANGLAIS: " + json.dumps(b.get("anglais"), ensure_ascii=False)[:2500]])
    s = b.get("science") or {}
    emit("4-science", [f"titre={s.get('titre')} retirees={s.get('phrases_retirees_garde_fou')}",
                       (s.get("contenu_markdown") or "")[:30000]])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "test-output")
