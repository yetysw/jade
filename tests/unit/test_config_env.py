"""Chargement de la configuration (ragagent/config.py) depuis un .env.

Deterministe : chaque .env est ecrit dans tmp_path et charge via
load_settings(env_file=...). L'environnement de processus est restaure apres
chaque test (load_dotenv ecrit directement dans os.environ).
"""

from __future__ import annotations

import os

import pytest

from ragagent import config, security


@pytest.fixture(autouse=True)
def _clean_env():
    """load_dotenv modifie os.environ globalement : snapshot + restauration."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _write(tmp_path, text: str, encoding: str = "utf-8"):
    p = tmp_path / ".env"
    p.write_bytes(text.encode(encoding))
    return p


def test_valeurs_par_defaut_env_vide(tmp_path):
    s = config.load_settings(_write(tmp_path, ""))
    assert s.ollama_model == "qwen3.5:4b"
    assert s.top_k == 10
    assert s.min_score == 0.35
    assert s.grace_days == 7
    assert s.license_enabled is False
    assert s.ui_port == 8765
    assert s.client_name == "Jade"
    assert ".docx" in s.extensions


def test_parsing_valeurs_typees(tmp_path):
    env = (
        "OLLAMA_MODEL=qwen3.5:9b\n"
        "TOP_K=25\n"
        "MIN_SCORE=0.5\n"
        "GRACE_DAYS=14\n"
        "LICENSE_ENABLED=1\n"
        "WEB_FALLBACK=0\n"
        "CLIENT_NAME=Acme\n"
    )
    s = config.load_settings(_write(tmp_path, env))
    assert s.ollama_model == "qwen3.5:9b"
    assert s.top_k == 25
    assert s.min_score == 0.5
    assert s.grace_days == 14
    assert s.license_enabled is True
    assert s.web_fallback is False
    assert s.client_name == "Acme"


def test_booleens_zero_false_vide_sont_faux(tmp_path):
    env = "OCR_ENABLED=0\nHYBRID_ENABLED=false\nRERANK_ENABLED=\n"
    s = config.load_settings(_write(tmp_path, env))
    assert s.ocr_enabled is False
    assert s.hybrid_enabled is False
    assert s.rerank_enabled is False


def test_ui_port_auto_donne_zero(tmp_path):
    # load_dotenv n'ecrase pas une variable deja presente (override=False) : on
    # purge UI_PORT entre chaque chargement pour tester des valeurs successives.
    def _port_for(value: str) -> int:
        os.environ.pop("UI_PORT", None)
        return config.load_settings(_write(tmp_path, f"UI_PORT={value}\n")).ui_port

    assert _port_for("auto") == 0
    assert _port_for("0") == 0
    assert _port_for("  ") == 0
    assert _port_for("9000") == 9000


def test_port_helper_direct():
    assert config._port("auto") == 0
    assert config._port("") == 0
    assert config._port("AUTO") == 0
    assert config._port("1234") == 1234


def test_urls_nettoyees_de_leur_slash_final(tmp_path):
    env = "OLLAMA_URL=https://llm.example.ch/\nGITEA_API_URL=https://git.example.ch/\n"
    s = config.load_settings(_write(tmp_path, env))
    assert s.ollama_url == "https://llm.example.ch"
    assert s.gitea_api_url == "https://git.example.ch"


def test_fallback_cp1252_sur_env_non_utf8(tmp_path):
    """Un .env ecrit en cp1252 (accents ANSI de l'installateur Inno) ne doit pas
    faire planter le demarrage : load_dotenv utf-8 echoue -> repli cp1252."""
    # 0xE9 = 'e accent aigu' en cp1252, sequence invalide en UTF-8 isolee.
    p = _write(tmp_path, "CLIENT_NAME=Societe Genevoise\n".replace("Societe", "Soci\xe9t\xe9"),
               encoding="cp1252")
    s = config.load_settings(p)
    assert s.client_name == "Soci\xe9t\xe9 Genevoise"


def test_get_dpapi_transparent_hors_windows(tmp_path, monkeypatch):
    """get() applique unprotect : une valeur prefixee DPAPI est renvoyee telle
    quelle hors Windows (pas de dechiffrement possible), une valeur non prefixee
    passe toujours inchangee."""
    monkeypatch.setattr(security, "_WINDOWS", False)  # simule non-Windows
    scellee = security.DPAPI_MACHINE_PREFIX + "cGF5bG9hZA=="
    s = config.load_settings(_write(tmp_path, f"CLIENT_NAME={scellee}\nGITEA_TOKEN=clair-123\n"))
    assert s.client_name == scellee     # renvoye tel quel (no-op hors Windows)
    assert s.gitea_token == "clair-123"  # non prefixe -> inchange
