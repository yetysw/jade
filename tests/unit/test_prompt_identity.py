"""Identité de l'assistant et nom de l'utilisateur dans les prompts système.

Aucun réseau : on assemble les prompts et on vérifie leur contenu.
"""

from __future__ import annotations

from types import SimpleNamespace

from ragagent import rag

SETTINGS = SimpleNamespace(client_name="ACME")

ROLE_PROMPTS = [
    rag.SYSTEM_PROMPT,
    rag.WEB_SYSTEM_PROMPT,
    rag.SMALLTALK_PROMPT,
    rag.GENERAL_PROMPT,
    rag.VISION_SYSTEM_PROMPT,
]


def test_identite_presente_sur_tous_les_chemins():
    for role in ROLE_PROMPTS:
        out = rag.system_prompt(role, SETTINGS)
        assert "Jade" in out
        assert "Jade Sàrl" in out
        assert "en local" in out
        assert "ACME" in out  # nom du client injecté


def test_prompt_documentaire_reste_focalise():
    out = rag.system_prompt(rag.SYSTEM_PROMPT, SETTINGS)
    assert "[Source N]" in out
    assert "extraits de\ndocuments fournis" in out
    assert "Je ne trouve pas cette information dans les documents indexes." in out


def test_nom_utilisateur_injecte_et_prioritaire():
    out = rag.system_prompt(rag.SYSTEM_PROMPT, SETTINGS, user_name="Noé Kandel")
    assert "Noé Kandel" in out
    # le nom prime sur ce qu'un fait mémorisé pourrait raconter
    assert "aucun autre" in out


def test_sans_nom_interdiction_d_inventer():
    out = rag.system_prompt(rag.SYSTEM_PROMPT, SETTINGS)
    assert "n'en invente aucun" in rag.user_line("")
    assert "n'en invente aucun" in out


def test_faits_memorises_sont_signales_comme_faillibles():
    out = rag.system_prompt(rag.SYSTEM_PROMPT, SETTINGS, user_name="Noé",
                            memory_text="- Il est technicien")
    assert "Il est technicien" in out
    assert "le nom indiqué ci-dessus fait foi" in out


def test_build_messages_porte_identite_et_nom():
    hits = [{"text": "extrait", "meta": {"filename": "doc.pdf"}, "score": 0.9}]
    messages = rag.build_messages("question ?", hits, [], SETTINGS, user_name="Claire")
    system = messages[0]["content"]
    assert messages[0]["role"] == "system"
    assert "Jade" in system and "Claire" in system
    assert "[Source 1]" in messages[-1]["content"]


def test_date_du_jour_toujours_presente():
    out = rag.system_prompt(rag.GENERAL_PROMPT, SETTINGS)
    assert f"Nous sommes le {rag.today_fr()}." in out
