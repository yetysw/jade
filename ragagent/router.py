"""Routeur de requêtes — décide la source d'information pour chaque question.

Trois destinations possibles :
- ``docs``  : la réponse se trouve dans les documents internes de l'entreprise ;
- ``web``   : elle dépend d'informations publiques et actuelles (Internet) ;
- ``direct``: ni l'un ni l'autre — conversation, culture générale stable,
  rédaction, création de fichier à partir de connaissances générales.

La décision est prise par une classification LLM courte (rapide, déterministe),
avec repli heuristique si le modèle est indisponible ou répond hors format.
Objectif : ne fouiller les documents que lorsque la réponse peut s'y trouver et
ne chercher sur le web que lorsque c'est réellement utile — c'était la principale
source de réponses hors-sujet avec l'ancien routage par mots-clés.
"""

from __future__ import annotations

import logging
import re

from .websearch import wants_web, web_query

log = logging.getLogger(__name__)

ROUTER_SYSTEM = """Tu es le pré-analyseur d'un assistant d'entreprise (Jade). Pour chaque
message, tu produis 3 informations, SANS jamais répondre à la question.

1. SOURCE — d'où doit venir la réponse :
   - DOCUMENTS : documents internes de l'entreprise (procédures, contrats,
     factures, RH, finances, clients, projets ; « notre », « nos », « chez nous »,
     noms de collègues/clients internes).
   - WEB : information publique ET actuelle (actualités, sport, météo, cours/prix,
     versions/sorties récentes, société ou personnalité publique) ou demande
     explicite de chercher en ligne / de vérifier que tes infos sont à jour.
   - DIRECT : bavardage, propos personnel, culture générale stable, DÉFINITION
     ou explication d'un concept technique ou général (« qu'est-ce que… »,
     « explique… », « c'est quoi… ») — ce sont des connaissances stables, PAS du
     web —, traduction, calcul, rédaction ; OU quand on demande de mettre en
     fichier ce qui vient d'être dit dans la conversation.
   Ne choisis WEB que si la réponse CHANGE dans le temps (actualité, prix, météo,
   version récente) ou si l'utilisateur demande explicitement de chercher en ligne.
   Une demande de fichier NE change PAS la source : classe selon le CONTENU
   (« exporte notre inventaire en Excel » = DOCUMENTS ; « fais un pdf des jours
   fériés suisses » = DIRECT).

2. FICHIER — l'utilisateur veut-il un fichier téléchargeable, et lequel ? Un seul
   parmi : docx, xlsx, pdf, pptx, csv, txt, md, html — ou NON. Réponds au format
   même s'il est implicite (« un truc que j'ouvre dans Excel » = xlsx ; « une
   présentation » = pptx ; « une page web » = html).

3. NIVEAU — effort de réflexion nécessaire :
   - SIMPLE : salutation, fait court, définition brève, petite question directe.
   - COMPLEXE : analyse, comparaison, rédaction longue, raisonnement en plusieurs
     étapes, synthèse de plusieurs sources, procédure détaillée, code.

4. QUERY — si SOURCE=WEB, une requête de recherche courte et précise ; sinon -

Réponds STRICTEMENT sur quatre lignes, rien d'autre :
SOURCE: <DOCUMENTS|WEB|DIRECT>
FICHIER: <docx|xlsx|pdf|pptx|csv|txt|md|html|NON>
NIVEAU: <SIMPLE|COMPLEXE>
QUERY: <requête ou ->

Exemples :
Message : quelle est notre politique de télétravail ?
SOURCE: DOCUMENTS
FICHIER: NON
NIVEAU: SIMPLE
QUERY: -

Message : résultats des matchs de la coupe du monde d'hier
SOURCE: WEB
FICHIER: NON
NIVEAU: SIMPLE
QUERY: résultats coupe du monde football hier

Message : je suis informaticien, j'ai 18 ans
SOURCE: DIRECT
FICHIER: NON
NIVEAU: SIMPLE
QUERY: -

Message : qu'est-ce qu'un ransomware ?
SOURCE: DIRECT
FICHIER: NON
NIVEAU: SIMPLE
QUERY: -

Message : qu'est-ce que le protocole DNS ?
SOURCE: DIRECT
FICHIER: NON
NIVEAU: SIMPLE
QUERY: -

Message : compare les avantages et inconvénients du RAID 5 et du RAID 10 pour un serveur de fichiers
SOURCE: DIRECT
FICHIER: NON
NIVEAU: COMPLEXE
QUERY: -

Message : fais-moi un tableau des jours fériés suisses de 2026 en Excel
SOURCE: DIRECT
FICHIER: xlsx
NIVEAU: SIMPLE
QUERY: -

Message : exporte en PDF l'inventaire informatique de notre parc
SOURCE: DOCUMENTS
FICHIER: pdf
NIVEAU: SIMPLE
QUERY: -

Message : rédige une procédure détaillée de reprise après sinistre pour nos serveurs
SOURCE: DOCUMENTS
FICHIER: NON
NIVEAU: COMPLEXE
QUERY: -

Message : prépare une présentation PowerPoint sur la cybersécurité
SOURCE: DIRECT
FICHIER: pptx
NIVEAU: COMPLEXE
QUERY: -"""

_ROUTE_RE = re.compile(r"SOURCE\s*[:=]\s*(DOCUMENTS|DOCS|WEB|DIRECT)", re.I)
_FILE_RE = re.compile(r"FICHIER\s*[:=]\s*(docx|xlsx|pdf|pptx|csv|txt|md|html|NON|-)", re.I)
_LEVEL_RE = re.compile(r"NIVEAU\s*[:=]\s*(SIMPLE|COMPLEXE|COMPLEX)", re.I)
_QUERY_RE = re.compile(r"QUERY\s*[:=]\s*(.+)", re.I)
_VALID_FMT = {"docx", "xlsx", "pdf", "pptx", "csv", "txt", "md", "html"}


def _heuristic(question: str, history: list[dict], has_docs: bool) -> tuple[str, str | None]:
    """Repli sans LLM : intention web explicite -> web, sinon documents (ou
    direct si l'index est vide)."""
    if wants_web(question):
        return "web", web_query(question, history)
    return ("docs" if has_docs else "direct"), None


def _guard(
    route: str, query: str | None, question: str, history: list[dict],
    has_docs: bool, allow_web: bool,
) -> tuple[str, str | None]:
    """Cohérence finale : pas de web si désactivé, pas de docs si index vide."""
    if route == "web" and not allow_web:
        route = "docs" if has_docs else "direct"
        query = None
    if route == "docs" and not has_docs:
        route = "direct"
        query = None
    if route == "web" and not query:
        query = web_query(question, history)
    return route, query


def route_question(
    llm, question: str, history: list[dict] | None,
    has_docs: bool, allow_web: bool = True, model: str | None = None,
) -> tuple[str, str | None, str | None, str]:
    """Pré-analyse : (route, requête_web|None, format_fichier|None, niveau).

    route ∈ {"web", "docs", "direct"} ; format_fichier ∈ SAVERS ou None ;
    niveau ∈ {"simple", "complexe"} (choix du modèle de génération).
    Une seule requête courte au LLM (déterministe, petit modèle si `model` fourni,
    sans « thinking »). En cas d'échec / hors format, repli heuristique."""
    history = history or []
    try:
        ctx = ""
        prev = [m["content"] for m in history if m.get("role") == "user"]
        if prev:
            ctx = f"Question précédente de l'utilisateur : {prev[-1][:150]}\n"
        out = (llm.chat(
            [
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user", "content": f"{ctx}Message : {question}"},
            ],
            model=model or None,
            options={"temperature": 0, "num_predict": 80},
            think=False,  # qwen3… : pas de bloc <think> qui noierait la sortie
            # pré-analyse bloquante avant le 1er token : pas de retry (n'amplifie
            # pas la saturation) et timeout court (le repli heuristique prend le
            # relais si ça traîne, plutôt que de bloquer 120 s).
            retry=False, timeout=20.0,
        ) or "").strip()
        m = _ROUTE_RE.search(out)
        if not m:
            log.debug("Pré-analyse hors format (%r), repli heuristique", out[:80])
            r, q = _heuristic(question, history, has_docs)
            return (*_guard(r, q, question, history, has_docs, allow_web), None, "simple")
        r = m.group(1).lower()
        r = "docs" if r in ("documents", "docs") else r
        query = None
        qm = _QUERY_RE.search(out)
        if qm:
            q = qm.group(1).strip().strip('"«»').strip()
            if q and q not in ("-", "—", "–"):
                query = q[:250]
        file_fmt = None
        fm = _FILE_RE.search(out)
        if fm and fm.group(1).lower() in _VALID_FMT:
            file_fmt = fm.group(1).lower()
        lm = _LEVEL_RE.search(out)
        level = "complexe" if (lm and lm.group(1).lower().startswith("complex")) else "simple"
        route, query = _guard(r, query, question, history, has_docs, allow_web)
        return route, query, file_fmt, level
    except Exception as e:  # noqa: BLE001 — la pré-analyse ne doit jamais bloquer
        log.debug("Pré-analyse LLM indisponible (%s), repli heuristique", e)
        r, q = _heuristic(question, history, has_docs)
        return (*_guard(r, q, question, history, has_docs, allow_web), None, "simple")
