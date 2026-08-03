"""Fixtures partagees pour les tests de l'application web (ragagent/web/app.py).

`create_app()` demarre normalement un thread de fond qui telecharge/charge les
modeles d'embeddings et fait un "warmup" reseau du LLM central. C'est
incompatible avec des tests deterministes, rapides et sans reseau : la
fixture `app_client` neutralise ce thread (sa cible n'est jamais executee),
redirige les repertoires de donnees utilisateur vers `tmp_path`, et
desactive les effets de bord dangereux (ouverture du client mail, de
l'explorateur Windows) avant de fournir un `TestClient`.

Aucune donnee reelle de l'utilisateur (prefs.json, %LOCALAPPDATA%\\Jade,
conversations, .env applicatif) n'est lue ni ecrite : tout est redirige vers
`tmp_path`.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from ragagent import config, prefs
from ragagent.web import app as app_module


class _NoOpThread:
    """Remplace `threading.Thread` pendant l'appel a `create_app()`.

    La cible (boucle de fond : telechargement/chargement des modeles,
    warmup reseau du LLM) n'est JAMAIS executee : seul `start()` est
    court-circuite, ce qui suffit a empecher tout acces reseau ou
    chargement de modele pendant les tests.
    """

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        pass

    def start(self) -> None:
        pass


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Fournit `(client, settings)` : une application Jade complete (toutes
    les routes reelles) tournant sur des repertoires temporaires, sans
    thread de fond, sans reseau, sans effet de bord systeme."""
    # prefs.json redirige vers tmp_path (jamais le fichier reel de l'utilisateur)
    monkeypatch.setattr(prefs, "_FILE", tmp_path / "prefs.json")
    # %LOCALAPPDATA%\Jade (ou equivalent) redirige vers tmp_path
    monkeypatch.setattr(config, "_user_data_dir", lambda *a, **k: str(tmp_path / "userdata"))

    env_path = tmp_path / ".env"
    env_path.write_text(
        f"DOCS_DIR={tmp_path / 'docs'}\n"
        f"DATA_DIR={tmp_path / 'data'}\n"
        f"LOG_DIR={tmp_path / 'logs'}\n"
        f"MODEL_CACHE_DIR={tmp_path / 'models'}\n"
        # port local invalide (echec de connexion immediat, pas de DNS) : au
        # cas ou un code non prevu tenterait un appel reseau, il echoue vite.
        "OLLAMA_URL=http://127.0.0.1:1\n",
        encoding="utf-8",
    )
    settings = config.load_settings(env_path)

    # threading.Thread neutralise UNIQUEMENT le temps de create_app() : le
    # scope se referme avant la creation du TestClient, donc le mecanisme de
    # threads internes de starlette/anyio (s'il y en a) n'est pas affecte.
    with monkeypatch.context() as thread_patch:
        thread_patch.setattr(threading, "Thread", _NoOpThread)
        app = app_module.create_app(settings, token="")

    # effets de bord systeme dangereux en test : client mail, explorateur
    monkeypatch.setattr(app_module, "open_url", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "reveal_path", lambda *a, **k: None)

    # host loopback explicite : le garde-fou anti DNS-rebinding de l'app
    # rejette le host "testserver" par defaut du TestClient.
    client = TestClient(app, base_url="http://127.0.0.1")
    yield client, settings
