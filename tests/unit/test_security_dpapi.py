"""Chiffrement au repos (ragagent/security.py) : comportement portable.

On teste le chemin hors Windows de facon deterministe sur n'importe quel hote en
forcant security._WINDOWS = False (monkeypatch). Le chemin DPAPI reel (Windows)
n'est pas exerce ici : il depend d'API systeme et de l'etat du compte, on ne
verifie donc que la degradation controlee et les invariants d'API (prefixes,
passe-plat unprotect).
"""

from __future__ import annotations

import pytest

from ragagent import security


@pytest.fixture
def _non_windows(monkeypatch):
    monkeypatch.setattr(security, "_WINDOWS", False)


def test_prefixes_constants():
    assert security.DPAPI_PREFIX == "dpapi:"
    assert security.DPAPI_MACHINE_PREFIX == "dpapi-m:"


def test_unprotect_valeur_sans_prefixe_inchangee(_non_windows):
    assert security.unprotect("valeur en clair") == "valeur en clair"
    assert security.unprotect("") == ""


def test_unprotect_valeur_prefixee_no_op_hors_windows(_non_windows):
    """Hors Windows, une valeur scellee ne peut pas etre dechiffree : renvoyee
    telle quelle plutot que de faire planter (retro-compat / degradation)."""
    scellee_u = security.DPAPI_PREFIX + "cGF5bG9hZA=="
    scellee_m = security.DPAPI_MACHINE_PREFIX + "cGF5bG9hZA=="
    assert security.unprotect(scellee_u) == scellee_u
    assert security.unprotect(scellee_m) == scellee_m


def test_protect_leve_hors_windows(_non_windows):
    with pytest.raises(OSError):
        security.protect("secret")


def test_protect_machine_leve_hors_windows(_non_windows):
    with pytest.raises(OSError):
        security.protect_machine("secret")


def test_dpapi_available_faux_hors_windows(_non_windows):
    assert security.dpapi_available() is False


def test_encrypt_at_rest_cree_le_dossier_et_renvoie_faux(tmp_path, _non_windows):
    cible = tmp_path / "data" / "chiffre"
    assert security.encrypt_at_rest(cible) is False  # EFS indisponible hors Windows
    assert cible.is_dir()  # mais le dossier est bien cree (best-effort)
