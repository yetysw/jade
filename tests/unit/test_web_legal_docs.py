"""Documents legaux embarques (ragagent/web/app._legal_markdown).

`_legal_markdown` est une fonction de module (pas imbriquee dans create_app) :
testable directement, sans demarrer l'application ni charger de modele.
`BUNDLE_DIR`/`PROJECT_ROOT` sont rediriges vers `tmp_path` pour ne jamais
dependre des fichiers reels du depot (docs/CGU.md, docs/confidentialite-*.md).
"""

from __future__ import annotations

from ragagent import config
from ragagent.web.app import _LEGAL_FALLBACK, _legal_markdown


def test_cgu_lit_le_fichier_du_depot(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CGU.md").write_text("# CGU de test\n", encoding="utf-8")
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    assert _legal_markdown("cgu") == "# CGU de test\n"


def test_privacy_lit_le_fichier_du_depot(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "confidentialite-donnees.md").write_text(
        "# Confidentialite de test\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    assert _legal_markdown("privacy") == "# Confidentialite de test\n"


def test_fichier_absent_repli_sur_texte_par_defaut(tmp_path, monkeypatch):
    """Ni BUNDLE_DIR ni PROJECT_ROOT n'ont le fichier : repli, jamais
    d'exception (ne doit jamais bloquer l'ecran d'acceptation)."""
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path / "bundle-absent")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "projet-absent")
    assert _legal_markdown("cgu") == _LEGAL_FALLBACK["cgu"]
    assert _legal_markdown("privacy") == _LEGAL_FALLBACK["privacy"]


def test_nom_inconnu_repli_sur_le_texte_par_defaut_cgu(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path / "bundle-absent")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "projet-absent")
    assert _legal_markdown("nom-bidon") == _LEGAL_FALLBACK["cgu"]


def test_bundle_dir_prioritaire_sur_project_root(tmp_path, monkeypatch):
    """Le contenu embarque (PyInstaller, BUNDLE_DIR) prime sur celui du depot
    (PROJECT_ROOT) quand les deux existent."""
    bundle = tmp_path / "bundle"
    project = tmp_path / "projet"
    (bundle / "docs").mkdir(parents=True)
    (project / "docs").mkdir(parents=True)
    (bundle / "docs" / "CGU.md").write_text("depuis le bundle", encoding="utf-8")
    (project / "docs" / "CGU.md").write_text("depuis le depot", encoding="utf-8")
    monkeypatch.setattr(config, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(config, "PROJECT_ROOT", project)
    assert _legal_markdown("cgu") == "depuis le bundle"


def test_repli_sur_project_root_si_absent_du_bundle(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    project = tmp_path / "projet"
    bundle.mkdir()  # pas de docs/CGU.md ici
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "CGU.md").write_text("depuis le depot", encoding="utf-8")
    monkeypatch.setattr(config, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(config, "PROJECT_ROOT", project)
    assert _legal_markdown("cgu") == "depuis le depot"
