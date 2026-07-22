"""Jade — backend documentaire local (Jade).

Tout le traitement documentaire (scan, parsing, chunking, embeddings,
vector store, retrieval) est local. Seul un payload texte minimal
(question + extraits) part en HTTPS sortant vers le LLM central.
"""

# Versionnage sémantique MAJEUR.MINEUR.CORRECTIF (voir CHANGELOG.md).
__version__ = "1.3.0"
