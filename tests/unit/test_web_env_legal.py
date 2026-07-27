"""Fonctions utilitaires module-level de l'app web (ragagent/web/app.py, 1.9.0).

- _write_env_values : mise a jour en place du .env (preservation des lignes,
  commentaires et de l'ordre ; ajout des cles absentes).
- _legal_markdown : lecture d'un document legal embarque, avec repli sur un
  texte par defaut si le fichier est absent.

Deterministe : PROJECT_ROOT / BUNDLE_DIR sont redirigees vers tmp_path via
monkeypatch. Aucun reseau, aucun modele.
"""

from __future__ import annotations

from ragagent import config
from ragagent.web import app


# --------------------------------------------------------- _write_env_values

def test_write_env_met_a_jour_cle_existante_et_preserve_le_reste(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    env = tmp_path / ".env"
    env.write_text(
        "# configuration Jade\n"
        "OLLAMA_URL=https://old.example.ch\n"
        "SEARXNG_URL=https://searx.example.ch\n"
        "\n"
        "# secrets\n"
        "CF_ACCESS_CLIENT_ID=abc\n",
        encoding="utf-8",
    )

    written = app._write_env_values({"OLLAMA_URL": "https://new.example.ch"})
    assert written == env

    lines = env.read_text(encoding="utf-8").splitlines()
    assert "OLLAMA_URL=https://new.example.ch" in lines
    # les autres lignes, commentaires et la ligne vide sont preserves
    assert "# configuration Jade" in lines
    assert "SEARXNG_URL=https://searx.example.ch" in lines
    assert "# secrets" in lines
    assert "CF_ACCESS_CLIENT_ID=abc" in lines
    assert "" in lines  # ligne vide conservee
    # une seule occurrence de la cle mise a jour (pas de doublon)
    assert sum(1 for line in lines if line.startswith("OLLAMA_URL=")) == 1


def test_write_env_ajoute_cle_absente_a_la_fin(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    env = tmp_path / ".env"
    env.write_text("OLLAMA_URL=https://old\n", encoding="utf-8")

    app._write_env_values({"OLLAMA_URL": "https://old", "NOUVELLE_CLE": "valeur"})

    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "NOUVELLE_CLE=valeur"
    assert "OLLAMA_URL=https://old" in lines


def test_write_env_preserve_l_ordre_des_lignes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    env = tmp_path / ".env"
    env.write_text("A=1\nB=2\nC=3\n", encoding="utf-8")

    app._write_env_values({"B": "20"})

    assert env.read_text(encoding="utf-8").splitlines() == ["A=1", "B=20", "C=3"]


def test_write_env_ignore_les_commentaires_ressemblant_a_des_cles(tmp_path, monkeypatch):
    """Une cle commentee (# OLLAMA_URL=...) ne doit pas etre confondue avec la
    vraie cle : la mise a jour ajoute la cle reelle sans toucher au commentaire."""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    env = tmp_path / ".env"
    env.write_text("# OLLAMA_URL=commentaire\n", encoding="utf-8")

    app._write_env_values({"OLLAMA_URL": "https://reel"})

    lines = env.read_text(encoding="utf-8").splitlines()
    assert "# OLLAMA_URL=commentaire" in lines  # commentaire intact
    assert "OLLAMA_URL=https://reel" in lines    # cle reelle ajoutee


def test_write_env_cree_le_fichier_si_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    env = tmp_path / ".env"
    assert not env.exists()

    written = app._write_env_values({"OLLAMA_URL": "https://x", "SEARXNG_URL": "https://y"})

    assert written.exists()
    lines = env.read_text(encoding="utf-8").splitlines()
    assert "OLLAMA_URL=https://x" in lines
    assert "SEARXNG_URL=https://y" in lines


# ------------------------------------------------------------- _legal_markdown

def test_legal_markdown_lit_le_fichier_embarque(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CGU.md").write_text("# CGU réelles\ncontenu", encoding="utf-8")

    assert app._legal_markdown("cgu") == "# CGU réelles\ncontenu"


def test_legal_markdown_privacy_lit_le_bon_fichier(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "confidentialite-donnees.md").write_text("# Confidentialité", encoding="utf-8")

    assert app._legal_markdown("privacy") == "# Confidentialité"


def test_legal_markdown_repli_si_fichier_absent(tmp_path, monkeypatch):
    """docs/ absent : on retombe sur le texte minimal embarque plutot que
    de bloquer l'ecran d'acceptation."""
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    assert app._legal_markdown("cgu") == app._LEGAL_FALLBACK["cgu"]
    assert app._legal_markdown("privacy") == app._LEGAL_FALLBACK["privacy"]


def test_legal_markdown_nom_inconnu_replie_sur_cgu(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    assert app._legal_markdown("inexistant") == app._LEGAL_FALLBACK["cgu"]


def test_legal_markdown_bundle_dir_prioritaire_sur_project_root(tmp_path, monkeypatch):
    """BUNDLE_DIR (bundle PyInstaller) est consulte avant PROJECT_ROOT."""
    bundle = tmp_path / "bundle"
    project = tmp_path / "project"
    for base, txt in ((bundle, "depuis bundle"), (project, "depuis project")):
        d = base / "docs"
        d.mkdir(parents=True)
        (d / "CGU.md").write_text(txt, encoding="utf-8")
    monkeypatch.setattr(config, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(config, "PROJECT_ROOT", project)

    assert app._legal_markdown("cgu") == "depuis bundle"
