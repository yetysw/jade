"""Routeur (pré-analyse) : parsing de la sortie LLM + gardes + repli. Utilise un
faux LLM — aucun réseau, aucun Ollama."""

from ragagent import router


class FakeLLM:
    def __init__(self, out: str):
        self._out = out

    def chat(self, *args, **kwargs) -> str:  # accepte retry=/timeout=/think=…
        return self._out


def test_parse_docs_fichier_niveau():
    llm = FakeLLM("SOURCE: DOCUMENTS\nFICHIER: xlsx\nNIVEAU: COMPLEXE\nQUERY: -")
    route, query, fmt, level = router.route_question(
        llm, "exporte notre inventaire en Excel", [], has_docs=True)
    assert route == "docs"
    assert fmt == "xlsx"
    assert level == "complexe"


def test_web_refuse_si_desactive():
    llm = FakeLLM("SOURCE: WEB\nFICHIER: NON\nNIVEAU: SIMPLE\nQUERY: meteo demain")
    route, *_ = router.route_question(
        llm, "meteo demain", [], has_docs=True, allow_web=False)
    assert route != "web"  # web interdit -> repli docs/direct


def test_repli_heuristique_si_llm_plante():
    class Boom:
        def chat(self, *a, **k):
            raise RuntimeError("ollama down")

    route, *_ = router.route_question(Boom(), "bonjour", [], has_docs=False)
    assert route == "direct"  # jamais d'exception propagée


def test_docs_devient_direct_si_index_vide():
    llm = FakeLLM("SOURCE: DOCUMENTS\nFICHIER: NON\nNIVEAU: SIMPLE\nQUERY: -")
    route, *_ = router.route_question(llm, "un truc", [], has_docs=False)
    assert route == "direct"  # pas de docs indexés -> direct
