"""Zip de diagnostic (retour utilisateur) : POST /api/feedback ->
ragagent.web.app._diagnostic_zip (fonction imbriquee dans create_app).

Point sensible confidentialite : ce zip est propose a l'utilisateur pour
etre joint a un e-mail envoye A L'EXTERIEUR (support Jade). Il ne doit
JAMAIS contenir le corps des requetes sortantes journalisees dans
outbound.jsonl (ragagent/audit.py : log_outbound y ecrit le champ "body",
qui porte la question de l'utilisateur et les extraits de documents
transmis au LLM). Seuls horodatage/methode/URL sont attendus dans le zip.

`_diagnostic_zip` etant une fonction imbriquee (fermeture sur `settings`,
`store`, `state`), elle n'est atteignable qu'en demarrant reellement
l'application. La fixture `app_client` (tests/unit/conftest.py) le fait sans
reseau ni chargement de modele (thread de fond neutralise) ; les effets de
bord dangereux de /api/feedback (ouverture du client mail, de
l'explorateur) sont aussi neutralises.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

CORPS_RECONNAISSABLE = "EXTRAIT_DOCUMENT_CONFIDENTIEL_ET_QUESTION_UTILISATEUR"


def _write_outbound_log(settings, body_marker: str) -> Path:
    log_path = settings.outbound_log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": "2026-01-01T00:00:00+00:00",
        "method": "POST",
        "url": "https://llm.exemple.ch/api/chat",
        "headers": {"Content-Type": "application/json"},
        "body": {"messages": [{"role": "user", "content": body_marker}]},
    }
    log_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return log_path


def test_le_zip_est_produit_et_contient_etat_et_journal(app_client):
    client, settings = app_client
    _write_outbound_log(settings, CORPS_RECONNAISSABLE)

    resp = client.post("/api/feedback", json={"content": "un souci"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    zip_path = Path(body["zip"])
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        assert "etat.json" in names
        etat = json.loads(z.read("etat.json"))
        assert etat["app"] == "Jade"
        assert "logs/outbound.jsonl" in names


def test_absence_de_journal_et_de_logs_ne_fait_pas_echouer_le_zip(app_client):
    """Aucun outbound.jsonl, aucun jade.log : le zip doit quand meme etre
    produit, avec seulement l'etat applicatif."""
    client, settings = app_client
    assert not settings.outbound_log.exists()
    assert not (settings.log_dir / "jade.log").exists()

    resp = client.post("/api/feedback", json={"content": ""})
    assert resp.status_code == 200
    zip_path = Path(resp.json()["zip"])
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as z:
        assert z.namelist() == ["etat.json"]


def test_ligne_illisible_du_journal_ne_fait_pas_echouer_le_zip(app_client):
    """Une ligne non-JSON dans outbound.jsonl ne doit jamais empecher la
    production du zip de diagnostic."""
    client, settings = app_client
    log_path = settings.outbound_log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("{ceci n'est pas une ligne JSON valide\n", encoding="utf-8")

    resp = client.post("/api/feedback", json={"content": ""})
    assert resp.status_code == 200
    zip_path = Path(resp.json()["zip"])
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as z:
        assert "logs/outbound.jsonl" in z.namelist()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG confidentialite (ragagent/web/app.py, fonction _diagnostic_zip, "
        "~ligne 1362-1374) : outbound.jsonl est copie TEL QUEL dans le zip de "
        "diagnostic (zipfile.write brut), sans jamais retirer le champ "
        "'body' ecrit par ragagent.audit.log_outbound (ragagent/audit.py "
        "ligne 17-30). Ce champ porte le corps integral de chaque requete "
        "sortante -- question de l'utilisateur et extraits de documents "
        "transmis au LLM/SearXNG. Le zip est ensuite propose a l'utilisateur "
        "pour etre joint a un e-mail de support envoye a l'exterieur "
        "(POST /api/feedback) : le contenu documentaire/conversationnel "
        "quitte donc potentiellement le poste, en contradiction avec le "
        "commentaire du code (\"Aucun secret, aucun contenu de "
        "conversation\", app.py ligne ~1339) et avec la garantie de "
        "confidentialite attendue. A corriger : ne conserver dans le zip que "
        "l'horodatage/methode/URL de chaque entree (jamais 'body'/'headers')."
    ),
)
def test_journal_caviarde_ne_contient_jamais_le_corps_des_requetes(app_client):
    client, settings = app_client
    _write_outbound_log(settings, CORPS_RECONNAISSABLE)

    resp = client.post("/api/feedback", json={"content": ""})
    assert resp.status_code == 200
    zip_path = Path(resp.json()["zip"])

    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            content = z.read(name)
            assert CORPS_RECONNAISSABLE.encode("utf-8") not in content, (
                f"le corps d'une requete sortante est present dans {name} "
                "du zip de diagnostic"
            )
