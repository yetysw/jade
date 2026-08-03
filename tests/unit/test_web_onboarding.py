"""Parcours de premier lancement : endpoints /api/onboarding* et
/api/legal/doc (ragagent/web/app.py).

Utilise la fixture `app_client` (tests/unit/conftest.py) : application reelle
sur repertoires temporaires, thread de fond neutralise (aucun reseau, aucun
chargement de modele).
"""

from __future__ import annotations

from ragagent import prefs
from ragagent.web.app import LEGAL_VERSION


def test_etat_initial_rien_accepte_onboarding_pas_termine(app_client):
    client, _settings = app_client
    resp = client.get("/api/onboarding")
    assert resp.status_code == 200
    body = resp.json()
    assert body["legal_version"] == LEGAL_VERSION
    assert body["legal_accepted"] is False
    assert body["onboarding_done"] is False
    assert body["configured"] is False  # aucun dossier indexe configure


def test_acceptation_puis_etat_reflete_la_version_courante(app_client):
    client, _settings = app_client
    resp = client.post("/api/onboarding/accept-legal")
    assert resp.status_code == 200
    assert resp.json() == {"legal_accepted": True, "legal_version": LEGAL_VERSION}

    resp = client.get("/api/onboarding")
    assert resp.json()["legal_accepted"] is True


def test_changement_de_version_legale_force_re_acceptation(app_client):
    """Une acceptation enregistree pour une ANCIENNE version des CGU ne doit
    jamais etre traitee comme une acceptation de la version courante : c'est
    le mecanisme qui force la re-acceptation quand les CGU changent."""
    client, _settings = app_client
    # simule une acceptation deja donnee pour une version revolue
    prefs.set_str("LegalAcceptedVersion", "2020-01")
    assert "2020-01" != LEGAL_VERSION

    resp = client.get("/api/onboarding")
    body = resp.json()
    assert body["legal_version"] == LEGAL_VERSION
    assert body["legal_accepted"] is False  # pas re-acceptee automatiquement

    # l'utilisateur re-accepte : la version courante est desormais enregistree
    client.post("/api/onboarding/accept-legal")
    assert client.get("/api/onboarding").json()["legal_accepted"] is True


def test_onboarding_marque_termine_et_persistant(app_client):
    client, _settings = app_client
    assert client.get("/api/onboarding").json()["onboarding_done"] is False

    resp = client.post("/api/onboarding/complete")
    assert resp.status_code == 200
    assert resp.json() == {"onboarding_done": True}

    assert client.get("/api/onboarding").json()["onboarding_done"] is True


def test_configured_reflete_la_presence_de_index_roots(app_client):
    client, settings = app_client
    from ragagent.index_config import set_roots

    assert client.get("/api/onboarding").json()["configured"] is False
    set_roots(settings, [str(settings.docs_dir)])
    assert client.get("/api/onboarding").json()["configured"] is True


# --------------------------------------------------------- /api/legal/doc


def test_legal_doc_endpoint_cgu(app_client):
    client, _settings = app_client
    resp = client.get("/api/legal/doc", params={"name": "cgu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "cgu"
    assert isinstance(body["markdown"], str) and body["markdown"]


def test_legal_doc_endpoint_defaut_cgu_sans_parametre(app_client):
    client, _settings = app_client
    resp = client.get("/api/legal/doc")
    assert resp.status_code == 200
    assert resp.json()["name"] == "cgu"


def test_legal_doc_endpoint_privacy(app_client):
    client, _settings = app_client
    resp = client.get("/api/legal/doc", params={"name": "privacy"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "privacy"
