"""Semver de l'auto-update — le test le plus rentable : un bug ici casse
silencieusement la mise à jour de TOUT le parc (tri lexical, suffixes)."""

from ragagent.updater import _is_newer, _parse_version, _pick_asset


def test_parse_ignore_prefixe_et_build():
    assert _parse_version("v1.6.0") == (1, 6, 0)
    assert _parse_version("1.6.0+2") == (1, 6, 0)
    assert _parse_version("1.4.3-rc1") == (1, 4, 3)
    assert _parse_version("") == (0,)


def test_comparaison_numerique_pas_lexicale():
    assert _is_newer("1.4.10", "1.4.2") is True   # piège du tri lexical
    assert _is_newer("1.6.0", "1.6.0") is False
    assert _is_newer("1.5.0", "1.6.0") is False


def test_pick_asset_choisit_le_bon_suffixe():
    assets = [
        {"name": "notes.txt", "browser_download_url": "u0"},
        {"name": "Jade-Setup-1.6.0.exe", "browser_download_url": "u1"},
        {"name": "Jade.dmg", "browser_download_url": "u2"},
    ]
    picked = _pick_asset(assets)
    assert picked is not None
    # sur l'hôte de test (Windows) : l'installateur .exe, jamais le .dmg
    assert picked["name"].endswith(".exe")
    assert _pick_asset([{"name": "readme.md"}]) is None
