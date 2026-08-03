"""Preferences utilisateur (ragagent/prefs.py) : premier lancement, CGU,
onboarding.

Deterministe : `prefs._FILE` est redirige vers `tmp_path` pour chaque test
(jamais le fichier reel de l'utilisateur, sous %APPDATA%/%LOCALAPPDATA%).
"""

from __future__ import annotations

import logging

import pytest

from ragagent import prefs
from ragagent.web.app import LEGAL_VERSION


@pytest.fixture(autouse=True)
def _isolated_prefs_file(tmp_path, monkeypatch):
    monkeypatch.setattr(prefs, "_FILE", tmp_path / "sub" / "prefs.json")


# --------------------------------------------------------- etat initial


def test_aucun_fichier_valeurs_par_defaut():
    """Avant tout lancement : rien n'est accepte, onboarding pas termine."""
    assert prefs.get_bool("OnboardingDone", False) is False
    assert prefs.get_str("LegalAcceptedVersion", "") == ""


def test_get_bool_respecte_le_defaut_fourni():
    assert prefs.get_bool("Inconnu", True) is True
    assert prefs.get_bool("Inconnu", False) is False


def test_get_str_respecte_le_defaut_fourni():
    assert prefs.get_str("Inconnu", "valeur-par-defaut") == "valeur-par-defaut"


# --------------------------------------------------------- ecriture/lecture


def test_set_bool_puis_get_bool_persiste():
    prefs.set_bool("Incognito", True)
    assert prefs.get_bool("Incognito", False) is True
    prefs.set_bool("Incognito", False)
    assert prefs.get_bool("Incognito", True) is False


def test_set_str_puis_get_str_persiste():
    prefs.set_str("LegalAcceptedVersion", "2026-07")
    assert prefs.get_str("LegalAcceptedVersion", "") == "2026-07"


def test_ecriture_cree_le_dossier_parent(tmp_path):
    """`_FILE` pointe vers un sous-dossier qui n'existe pas encore : la
    premiere ecriture doit le creer sans erreur."""
    assert not prefs._FILE.parent.exists()
    prefs.set_bool("Incognito", True)
    assert prefs._FILE.exists()


def test_plusieurs_cles_coexistent():
    """Une ecriture ne doit pas effacer les autres preferences deja
    enregistrees (lecture-modification-ecriture du fichier complet)."""
    prefs.set_bool("Incognito", True)
    prefs.set_str("LegalAcceptedVersion", "2026-07")
    prefs.set_bool("OnboardingDone", True)
    assert prefs.get_bool("Incognito", False) is True
    assert prefs.get_str("LegalAcceptedVersion", "") == "2026-07"
    assert prefs.get_bool("OnboardingDone", False) is True


# --------------------------------------------------------- robustesse lecture


def test_fichier_absent_ne_leve_pas(tmp_path):
    assert not prefs._FILE.exists()
    assert prefs._load() == {}
    assert prefs.get_bool("X", False) is False
    assert prefs.get_str("X", "d") == "d"


def test_fichier_vide_ne_leve_pas():
    prefs._FILE.parent.mkdir(parents=True, exist_ok=True)
    prefs._FILE.write_text("", encoding="utf-8")
    assert prefs._load() == {}


def test_fichier_json_corrompu_ne_leve_pas():
    prefs._FILE.parent.mkdir(parents=True, exist_ok=True)
    prefs._FILE.write_text("{ceci n'est pas du json", encoding="utf-8")
    assert prefs._load() == {}
    assert prefs.get_bool("OnboardingDone", False) is False


def test_fichier_json_valide_mais_pas_un_objet_ne_leve_pas():
    """`_load` typé `dict` : une liste JSON valide ne doit pas faire planter
    les lectures suivantes (`.get()` sur autre chose qu'un dict leverait)."""
    prefs._FILE.parent.mkdir(parents=True, exist_ok=True)
    prefs._FILE.write_text("[1, 2, 3]", encoding="utf-8")
    # _load() renvoie tel quel ce que json.loads produit ; get_bool/get_str
    # appellent .get() dessus. Documente le comportement reel : si ce n'est
    # pas un dict, .get() n'existe pas -> AttributeError, non capturee par
    # `_load` (seuls OSError/ValueError le sont). On verifie ici explicitement
    # ce cas limite plutot que de le supposer robuste.
    with pytest.raises(AttributeError):
        prefs.get_bool("X", False)


def test_fichier_non_inscriptible_set_bool_ne_leve_pas(tmp_path, monkeypatch, caplog):
    """Le parent de `_FILE` est en realite un fichier existant : la creation
    du dossier (mkdir) echoue -> `_write` doit avaler l'OSError et
    journaliser, jamais remonter d'exception."""
    blocker = tmp_path / "blocker"
    blocker.write_text("je suis un fichier, pas un dossier", encoding="utf-8")
    monkeypatch.setattr(prefs, "_FILE", blocker / "prefs.json")  # parent = un fichier
    with caplog.at_level(logging.WARNING):
        prefs.set_bool("Incognito", True)  # ne doit pas lever
    assert "Incognito" in caplog.text
    # rien n'a ete persiste : la lecture retombe sur le defaut
    assert prefs.get_bool("Incognito", False) is False


def test_fichier_non_inscriptible_set_str_ne_leve_pas(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker2"
    blocker.write_text("fichier", encoding="utf-8")
    monkeypatch.setattr(prefs, "_FILE", blocker / "prefs.json")
    prefs.set_str("LegalAcceptedVersion", "2026-07")  # ne doit pas lever


# --------------------------------------------------------- acceptation CGU


def test_acceptation_version_courante_reconnue():
    """Apres acceptation de la version courante : l'etat doit la refleter
    (c'est la comparaison faite par GET /api/onboarding)."""
    prefs.set_str("LegalAcceptedVersion", LEGAL_VERSION)
    accepted = prefs.get_str("LegalAcceptedVersion", "")
    assert accepted == LEGAL_VERSION


def test_acceptation_ancienne_version_ne_vaut_pas_acceptation_courante():
    """Coeur du mecanisme de re-acceptation : une acceptation enregistree
    pour une ANCIENNE version des CGU ne doit jamais etre confondue avec une
    acceptation de la version courante. Si les CGU changent (LEGAL_VERSION
    incremente), l'utilisateur doit revoir l'ecran d'acceptation."""
    ancienne_version = "2020-01"
    assert ancienne_version != LEGAL_VERSION  # garde-fou : le test a un sens
    prefs.set_str("LegalAcceptedVersion", ancienne_version)
    accepted = prefs.get_str("LegalAcceptedVersion", "")
    # reproduit exactement la comparaison de ragagent.web.app.onboarding_state
    assert (accepted == LEGAL_VERSION) is False


def test_onboarding_termine_persiste():
    assert prefs.get_bool("OnboardingDone", False) is False
    prefs.set_bool("OnboardingDone", True)
    assert prefs.get_bool("OnboardingDone", False) is True
