"""Fusion RRF + tokenisation BM25 — cœur du classement des résultats."""

from ragagent.hybrid import _tok, rrf_fuse


def test_rrf_recompense_la_presence_dans_plusieurs_listes():
    # 'b' apparaît dans les deux classements -> doit primer sur 'a' (rang 0 d'une
    # seule liste)
    fused = rrf_fuse([["a", "b", "c"], ["b", "x", "y"]])
    assert fused["b"] > fused["a"]


def test_rrf_rang0_pese_plus_que_rang1():
    fused = rrf_fuse([["a", "b"]])
    assert fused["a"] > fused["b"]


def test_rrf_liste_vide():
    assert rrf_fuse([[]]) == {}


def test_tok_minuscule_et_mots():
    assert _tok("Le Chat 2026") == ["le", "chat", "2026"]
