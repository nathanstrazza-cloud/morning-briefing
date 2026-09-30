"""Tests du moteur d'orchestration LLM (répartition par parties + secours en chaîne).

Exécution (depuis la racine du dépôt) :   python -m unittest discover -s tests -v
Aucun accès réseau : les fournisseurs sont des faux (FakeProvider) qui réussissent ou échouent
selon un scénario, et enregistrent l'ordre des appels dans CALLS.
"""
import json
import os
import unittest

from src.generation import llm_orchestrator as orch
from src.generation import parts as parts_mod
from src.generation.llm_orchestrator import Part
from src.generation.llm_provider import LLMError

PLAN = orch.load_plan()


class FakeProvider:
    """`fail` = ensemble de parties en échec ; `fail_429` = échec avec code 429 ; `raw` = réponse brute imposée."""
    def __init__(self, name, calls, fail=(), fail_429=(), raw=None):
        self.name, self.calls, self.fail, self.fail_429, self.raw = name, calls, set(fail), set(fail_429), raw or {}

    def complete(self, system, user, max_tokens=0):
        part = system.replace("SYS_", "")
        self.calls.append((self.name, part, len(user)))
        if part in self.fail_429:
            raise LLMError("429 rate limit", status_code=429)
        if part in self.fail:
            raise LLMError("500 boom", status_code=500)
        if part in self.raw:
            return self.raw[part]
        return json.dumps({"k": part, "provider": self.name})


def simple_parts(names, budgets=(100, 10)):
    return {n: Part(n, "SYS_" + n, lambda mc, n=n: "x" * mc, 100, ("k",), budgets) for n in names}


def stage_chains(wave_idx, stage_idx, names):
    st = PLAN["waves"][wave_idx]["stages"][stage_idx]["parts"]
    return {n: list(st[n]) for n in names}


class TestSecours(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def pool(self, **fails):
        return {n: FakeProvider(n, self.calls, **fails.get(n, {})) for n in ("groq", "mistral", "nvidia", "openrouter")}

    def test_nominal_chaque_partie_sur_son_principal(self):
        res = orch.run_plan(PLAN, simple_parts(["actu_france", "actu_monde", "marches", "anglais", "science_a", "science_b", "sport"]),
                            self.pool(), sleep=lambda s: None)
        got = {n: r.provider for n, r in res.items()}
        self.assertEqual(got, {"actu_france": "groq", "actu_monde": "mistral", "marches": "nvidia", "anglais": "openrouter",
                               "science_a": "mistral", "science_b": "groq", "sport": "openrouter"})
        self.assertEqual(len(self.calls), 7)      # aucun appel inutile

    def test_les_deux_actu_echouent_les_deux_autres_font_le_secours_AVANT_leur_partie(self):
        pool = self.pool(groq={"fail": ["actu_france"]}, mistral={"fail": ["actu_monde"]})
        res = orch.run_plan(PLAN, simple_parts(["actu_france", "actu_monde", "marches", "anglais"]), pool, sleep=lambda s: None)
        self.assertEqual(res["actu_france"].provider, "nvidia")
        self.assertEqual(res["actu_monde"].provider, "openrouter")
        order = [(p, part) for p, part, _ in self.calls]
        # secours de l'actualité (nvidia/openrouter) strictement avant marchés/anglais
        self.assertLess(order.index(("nvidia", "actu_france")), order.index(("nvidia", "marches")))
        self.assertLess(order.index(("openrouter", "actu_monde")), order.index(("openrouter", "anglais")))
        self.assertTrue(res["marches"].ok and res["anglais"].ok)

    def test_un_seul_fournisseur_actu_en_panne(self):
        res = orch.run_plan(PLAN, simple_parts(["actu_france", "actu_monde", "marches", "anglais"]),
                            self.pool(groq={"fail": ["actu_france"]}), sleep=lambda s: None)
        self.assertEqual((res["actu_france"].provider, res["actu_monde"].provider), ("nvidia", "mistral"))

    def test_science_secours_par_le_fournisseur_inutilise_puis_sport(self):
        # science_b (groq) et sport (openrouter) échouent : nvidia sert science_b d'abord, puis sport
        pool = self.pool(groq={"fail": ["science_b"]}, openrouter={"fail": ["sport"]})
        res = orch.run_plan(PLAN, simple_parts(["science_a", "science_b", "sport"]), pool, sleep=lambda s: None)
        self.assertEqual((res["science_b"].provider, res["sport"].provider), ("nvidia", "nvidia"))
        nv = [part for p, part, _ in self.calls if p == "nvidia"]
        self.assertEqual(nv, ["science_b", "sport"])            # science prioritaire

    def test_science_a_et_b_en_panne_nvidia_les_reprend_dans_l_ordre(self):
        pool = self.pool(mistral={"fail": ["science_a"]}, groq={"fail": ["science_b"]})
        res = orch.run_plan(PLAN, simple_parts(["science_a", "science_b", "sport"]), pool, sleep=lambda s: None)
        self.assertEqual([part for p, part, _ in self.calls if p == "nvidia"], ["science_a", "science_b"])
        self.assertEqual(res["sport"].provider, "openrouter")   # sport non affecté

    def test_fournisseur_sans_cle_est_saute(self):
        pool = self.pool()
        del pool["nvidia"]
        res = orch.run_plan(PLAN, simple_parts(["marches"]), pool, sleep=lambda s: None)
        self.assertEqual(res["marches"].provider, "openrouter")  # chaîne : nvidia (absent) -> openrouter

    def test_echec_partout_donne_body_none_et_details(self):
        pool = self.pool(**{n: {"fail": ["marches"]} for n in ("groq", "mistral", "nvidia", "openrouter")})
        res = orch.run_plan(PLAN, simple_parts(["marches"]), pool, sleep=lambda s: None)
        self.assertFalse(res["marches"].ok)
        self.assertEqual(len(res["marches"].attempts), 4)
        self.assertIn("nvidia", res["marches"].error)

    def test_429_pas_de_nouvelle_tentative_sur_le_meme_fournisseur(self):
        pool = self.pool(nvidia={"fail_429": ["marches"]})
        res = orch.run_plan(PLAN, simple_parts(["marches"]), pool, sleep=lambda s: None)
        self.assertEqual(len([c for c in self.calls if c[0] == "nvidia"]), 1)   # pas de 2e tentative à budget réduit
        self.assertEqual(res["marches"].provider, "openrouter")

    def test_erreur_autre_que_429_reessaie_avec_prompt_plus_petit(self):
        pool = self.pool(nvidia={"fail": ["marches"]})
        orch.run_plan(PLAN, simple_parts(["marches"]), pool, sleep=lambda s: None)
        tailles = [n for p, part, n in self.calls if p == "nvidia"]
        self.assertEqual(tailles, [100, 10])

    def test_json_avec_balises_ou_texte_autour_est_accepte(self):
        raw = {"marches": '```json\n{"k": 1}\n```'}
        res = orch.run_plan(PLAN, simple_parts(["marches"]), {"nvidia": FakeProvider("nvidia", self.calls, raw=raw)}, sleep=lambda s: None)
        self.assertTrue(res["marches"].ok)
        raw2 = {"marches": 'Voici le JSON : {"k": 2} merci'}
        res2 = orch.run_plan(PLAN, simple_parts(["marches"]), {"nvidia": FakeProvider("nvidia", self.calls, raw=raw2)}, sleep=lambda s: None)
        self.assertEqual(res2["marches"].body["k"], 2)

    def test_cle_obligatoire_manquante_declenche_le_secours(self):
        raw = {"marches": json.dumps({"autre": 1})}
        pool = {"nvidia": FakeProvider("nvidia", self.calls, raw=raw), "openrouter": FakeProvider("openrouter", self.calls)}
        res = orch.run_plan(PLAN, simple_parts(["marches"], budgets=(100,)), pool, sleep=lambda s: None)
        self.assertEqual(res["marches"].provider, "openrouter")

    def test_pause_entre_les_deux_appels(self):
        pauses = []
        orch.run_plan(PLAN, simple_parts(["actu_france", "science_a", "sport"]), self.pool(), sleep=pauses.append)
        self.assertEqual(pauses, [150])

    def test_pause_surchargeable_par_variable_d_environnement(self):
        pauses = []
        os.environ["LLM_WAVE_GAP_SECONDS"] = "0"
        try:
            orch.run_plan(PLAN, simple_parts(["actu_france", "science_a"]), self.pool(), sleep=pauses.append)
        finally:
            del os.environ["LLM_WAVE_GAP_SECONDS"]
        self.assertEqual(pauses, [])


ANALYSED = {
    "actualite_france": [{"titre": "F1", "resume": "r", "statut_verification": "fait_confirme", "sources": [{"nom": "Le Monde"}]}],
    "actualite_monde": [{"titre": "M1", "resume": "r", "statut_verification": "fait_confirme", "sources": [{"nom": "AFP"}]}],
    "actualite_economie": [], "marches_data": {"mouvements_significatifs": []},
    "sport_events": {"football": [{"titre": "PSG gagne"}], "basketball": []},
}
TOPIC_APPROF = {"mode": "approfondi", "contenu_source": {"titre": "Sommeil", "url": "https://x"}}
TOPIC_DECOUV = {"mode": "decouverte", "contenu_source": {"titre": "Découverte", "url": "https://x"}}
NYT = {"titre": "T", "resume": "R", "url": "u", "source": "NYT"}


class TestParts(unittest.TestCase):
    def test_science_b_absente_en_mode_decouverte(self):
        self.assertIn("science_b", parts_mod.build_parts(ANALYSED, TOPIC_APPROF, NYT, False))
        self.assertNotIn("science_b", parts_mod.build_parts(ANALYSED, TOPIC_DECOUV, NYT, False))

    def test_anglais_absent_sans_article_nyt(self):
        self.assertNotIn("anglais", parts_mod.build_parts(ANALYSED, TOPIC_APPROF, None, False))

    def test_prompts_ne_contiennent_que_leur_zone(self):
        p = parts_mod.build_parts(ANALYSED, TOPIC_APPROF, NYT, False)
        self.assertIn("F1", p["actu_france"].build_prompt(12000))
        self.assertNotIn("M1", p["actu_france"].build_prompt(12000))
        self.assertIn("M1", p["actu_monde"].build_prompt(12000))

    def _base(self):
        from src.generation import briefing_generator as bg
        return bg.fallback_briefing(ANALYSED, TOPIC_APPROF, NYT, None, False)

    def _res(self, **oks):
        out = {}
        for n, body in oks.items():
            r = orch.PartResult(n)
            if body is not None:
                r.body, r.provider = body, "x"
            else:
                r.attempts = ["x: échec"]
            out[n] = r
        return out

    def test_merge_science_a_et_b(self):
        base = self._base()
        parts_mod.merge_results(base, self._res(
            science_a={"science": {"mode": "approfondi", "titre": "Titre", "contenu_markdown": "## 1\nA"}},
            science_b={"contenu_markdown": "## 5\nB"}), NYT)
        self.assertEqual(base["science"]["contenu_markdown"], "## 1\nA\n\n## 5\nB")

    def test_merge_science_b_manquante_ajoute_une_mention(self):
        base = self._base()
        parts_mod.merge_results(base, self._res(
            science_a={"science": {"mode": "approfondi", "titre": "T", "contenu_markdown": "A"}}, science_b=None), NYT)
        self.assertTrue(base["science"]["contenu_markdown"].endswith(parts_mod.NOTE_SUITE_ABSENTE))

    def test_merge_science_a_manquante_garde_le_repli_meme_si_b_reussit(self):
        base = self._base()
        avant = base["science"]["contenu_markdown"]
        parts_mod.merge_results(base, self._res(science_a=None, science_b={"contenu_markdown": "B orpheline"}), NYT)
        self.assertEqual(base["science"]["contenu_markdown"], avant)

    def test_merge_actu_et_citation_et_resume(self):
        base = self._base()
        parts_mod.merge_results(base, self._res(
            actu_france={"actualite_france": [{"titre": "Titre France."}], "citation": {"texte": "t", "auteur": "a"}},
            actu_monde={"actualite_monde": [{"titre": "Titre Monde"}]}), NYT)
        self.assertEqual(base["actualite"]["france"][0]["titre"], "Titre France.")
        self.assertEqual(base["citation"]["auteur"], "a")
        self.assertEqual(base["meta"]["resume_1_phrase"], "À la une : Titre France ; Titre Monde.")

    def test_une_partie_en_echec_garde_son_contenu_brut(self):
        base = self._base()
        brut = base["sport"]
        parts_mod.merge_results(base, self._res(sport=None), NYT)
        self.assertEqual(base["sport"], brut)


if __name__ == "__main__":
    unittest.main()
