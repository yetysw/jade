"""Sauvegarde / migration de l'historique (ragagent/chat_store.py, 1.9.0).

Exerce le couple export_all() / import_all() sur des bases SQLite temporaires
(tmp_path) : aucun reseau, aucun modele. Le contenu est chiffre au repos (DPAPI)
quand il est disponible ; on passe volontairement par l'API publique
(export_all/get_conversation), transparente au chiffrement, pour rester
deterministe quel que soit l'etat DPAPI de l'hote.
"""

from __future__ import annotations

import pytest

from ragagent.chat_store import DEFAULT_TITLE, ChatStore


def _fresh_store(tmp_path, name: str = "chats.db") -> ChatStore:
    return ChatStore(tmp_path / name)


def _populate(store: ChatStore) -> dict:
    """Cree un jeu representatif : 1 dossier, 2 conversations (dont une epinglee
    et une archivee), des messages avec sources/timings/pieces jointes."""
    folder = store.create_folder("Dossier RH")

    c1 = store.create_conversation()["id"]
    store.rename(c1, "Congés 2026")
    store.add_message(c1, "user", "Combien de jours de congés ?")
    store.add_message(
        c1, "assistant", "Vingt-cinq jours ouvrés.",
        sources=[{"path": "doc.pdf", "score": 0.9}],
        timings={"total": 1.23},
        attachments=[{"name": "reglement.pdf", "path": "p", "kind": "doc"}],
    )
    store.set_conv_folder(c1, folder["id"])
    store.set_flag(c1, "pinned", True)

    c2 = store.create_conversation()["id"]
    store.rename(c2, "Ancienne discussion")
    store.add_message(c2, "user", "Bonjour")
    store.set_flag(c2, "archived", True)

    return {"folder": folder["id"], "c1": c1, "c2": c2}


def test_round_trip_export_import_egalite(tmp_path):
    """Export d'une base peuplee puis reimport dans une base neuve : les deux
    exports doivent etre strictement egaux (titres, messages, dossiers, drapeaux,
    horodatages preserves)."""
    src = _populate(_fresh_store(tmp_path, "src.db"))
    store_a = ChatStore(tmp_path / "src.db")
    exported = store_a.export_all()

    # structure attendue
    assert set(exported) == {"folders", "conversations"}
    assert len(exported["folders"]) == 1
    assert len(exported["conversations"]) == 2

    store_b = _fresh_store(tmp_path, "dst.db")
    counts = store_b.import_all(exported)
    assert counts == {"folders": 1, "conversations": 2, "messages": 3}

    # egalite profonde des deux exports
    assert store_b.export_all() == exported

    # verification ciblee du contenu migre (dechiffrement transparent)
    conv = store_b.get_conversation(src["c1"])
    assert conv["title"] == "Congés 2026"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["sources"] == [{"path": "doc.pdf", "score": 0.9}]
    assert conv["messages"][1]["timings"] == {"total": 1.23}
    assert conv["messages"][1]["attachments"][0]["name"] == "reglement.pdf"


def test_import_preserve_drapeaux_pinned_archived_et_dossier(tmp_path):
    src = _populate(_fresh_store(tmp_path, "src.db"))
    exported = ChatStore(tmp_path / "src.db").export_all()

    store_b = _fresh_store(tmp_path, "dst.db")
    store_b.import_all(exported)

    all_convs = {c["id"]: c for c in store_b.list_conversations(include_archived=True)}
    assert all_convs[src["c1"]]["pinned"] is True
    assert all_convs[src["c1"]]["archived"] is False
    assert all_convs[src["c1"]]["folder_id"] == src["folder"]
    assert all_convs[src["c2"]]["archived"] is True
    assert {f["id"] for f in store_b.list_folders()} == {src["folder"]}


def test_fusion_non_destructive_ids_existants_non_ecrases(tmp_path):
    """Un import ne doit ni ecraser ni dupliquer un id deja present : seuls les
    nouveaux dossiers/conversations sont inseres."""
    src = _populate(_fresh_store(tmp_path, "src.db"))
    exported = ChatStore(tmp_path / "src.db").export_all()

    # base cible qui possede DEJA c1 (avec un titre different) et son dossier
    dst = _fresh_store(tmp_path, "dst.db")
    # on reimporte d'abord tout, puis on renomme localement c1
    dst.import_all(exported)
    dst.rename(src["c1"], "Titre local a preserver")

    # second import du meme export : rien ne doit changer
    counts = dst.import_all(exported)
    assert counts == {"folders": 0, "conversations": 0, "messages": 0}

    # le titre local n'a pas ete ecrase, aucun doublon de messages
    conv = dst.get_conversation(src["c1"])
    assert conv["title"] == "Titre local a preserver"
    assert len(conv["messages"]) == 2  # pas de re-insertion des messages


def test_import_fusion_partielle_ajoute_uniquement_le_nouveau(tmp_path):
    src = _populate(_fresh_store(tmp_path, "src.db"))
    exported = ChatStore(tmp_path / "src.db").export_all()

    dst = _fresh_store(tmp_path, "dst.db")
    # cree une conversation independante dans la cible
    other = dst.create_conversation()["id"]
    dst.rename(other, "Deja presente")

    counts = dst.import_all(exported)
    assert counts["conversations"] == 2  # les 2 conversations de la source
    ids = {c["id"] for c in dst.list_conversations(include_archived=True)}
    assert ids == {other, src["c1"], src["c2"]}


def test_import_folder_id_orphelin_devient_non_classe(tmp_path):
    """Une conversation referencant un dossier absent de l'export ne doit pas
    echouer : elle devient non classee (folder_id NULL)."""
    dst = _fresh_store(tmp_path, "dst.db")
    data = {
        "folders": [],
        "conversations": [
            {
                "id": "conv123456",
                "title": "Orpheline",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "pinned": 0,
                "archived": 0,
                "folder_id": "dossier-inexistant",
                "messages": [{"role": "user", "content": "coucou",
                              "created_at": "2026-01-01T00:00:00+00:00"}],
            }
        ],
    }
    dst.import_all(data)
    assert dst.get_folder_id("conv123456") is None


def test_import_ignore_les_roles_invalides(tmp_path):
    dst = _fresh_store(tmp_path, "dst.db")
    data = {
        "folders": [],
        "conversations": [
            {
                "id": "conv999999",
                "title": "Roles",
                "messages": [
                    {"role": "user", "content": "ok"},
                    {"role": "system", "content": "a ignorer"},
                    {"role": "assistant", "content": "reponse"},
                ],
            }
        ],
    }
    counts = dst.import_all(data)
    assert counts["messages"] == 2  # 'system' rejete
    conv = dst.get_conversation("conv999999")
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]


def test_import_titre_par_defaut_si_absent(tmp_path):
    dst = _fresh_store(tmp_path, "dst.db")
    dst.import_all({"conversations": [{"id": "convabcdef", "messages": []}]})
    conv = dst.get_conversation("convabcdef")
    assert conv["title"] == DEFAULT_TITLE


@pytest.mark.parametrize("bad", [None, "chaine", 123, [], {}, {"folders": []}])
def test_import_structure_invalide_leve_valueerror(tmp_path, bad):
    dst = _fresh_store(tmp_path, "dst.db")
    with pytest.raises(ValueError):
        dst.import_all(bad)


def test_import_conversations_vide_ne_leve_pas(tmp_path):
    dst = _fresh_store(tmp_path, "dst.db")
    counts = dst.import_all({"conversations": []})
    assert counts == {"folders": 0, "conversations": 0, "messages": 0}
