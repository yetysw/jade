"""Pipeline RAG multi-tours : question -> retrieval local chronometre -> prompt FR.

Le retrieval est entierement local ; seuls la question, l'historique de
conversation (texte) et les extraits selectionnes partent vers le LLM.
"""

from __future__ import annotations

import re
import time

from .config import Settings
from .embedding import Embedder
from .store import Store

# Identité commune à TOUS les chemins où l'assistant s'adresse à l'utilisateur
# (documentaire, web, conversation, vision). Assemblée par system_prompt() : un
# seul point de vérité, sinon l'assistant « oublie » qui il est selon le chemin
# emprunté (c'était le cas : aucun prompt ne disait son nom ni son éditeur).
# Volontairement courte : sur le chemin documentaire, la consigne qui doit
# dominer reste l'usage des extraits et la citation des sources.
IDENTITY = """Tu es Jade, l'assistante documentaire éditée par Jade Sàrl, déployée chez {client}.
Tu fonctionnes en local sur le poste de l'utilisateur : ses documents sont indexés et
consultés sur cette machine et n'en sortent jamais ; seuls sa question et de courts
extraits sont transmis au serveur d'IA de Jade, le temps de rédiger la réponse.
Si on te demande qui tu es ou comment tu t'appelles, dis-le simplement, sans emphase.
Tu ne portes aucun autre nom que Jade et tu ne t'attribues aucune capacité que tu n'as pas.
Réponds en français, vouvoie l'utilisateur, ton sobre et professionnel, aucun emoji."""

SYSTEM_PROMPT = """Pour cette question, reponds uniquement a partir des extraits de
documents fournis et de l'historique de la conversation.
IMPORTANT — pertinence : certains extraits fournis peuvent etre HORS SUJET
(la recherche est approximative). N'utilise QUE les extraits qui repondent
reellement a la question ; ignore totalement les autres, ne les mentionne pas,
ne les melange jamais a ta reponse.
Si aucun extrait ne repond vraiment a la question, dis-le explicitement :
« Je ne trouve pas cette information dans les documents indexes. »
Citations : uniquement sous la forme [Source N] apres l'affirmation concernee.
N'ajoute JAMAIS de section « Sources » ou « References » en fin de reponse,
et n'ecris jamais le nom des fichiers sources dans le texte.
Ne jamais inventer de contenu. Utilise l'historique pour comprendre les
questions de suivi (pronoms, references implicites)."""

WEB_SYSTEM_PROMPT = """Pour cette question, reponds a partir des extraits de pages web
fournis (resultats d'une recherche que tu viens d'effectuer) et de l'historique
de la conversation.
N'utilise que les extraits reellement pertinents ; ignore les pages hors sujet.
Citations : uniquement [Source N] apres l'affirmation concernee — jamais de
section « Sources » en fin de reponse, jamais d'URL dans le texte.
Si les pages ne repondent pas a la question, dis-le simplement (ne parle PAS
de « documents indexes » : c'est une recherche web)."""

SMALLTALK_PROMPT = """Reponds brievement, avec naturel. C'est un echange
conversationnel (salutation, remerciement, propos personnel, question sur toi) :
ne cite aucun document et NE FAIS AUCUNE recherche. Si l'utilisateur te confie une
information sur lui (metier, age, preference), accuse simplement reception avec
naturel. Si on te demande ce que tu sais faire, explique que tu reponds aux
questions sur les documents internes de {client} en citant tes sources, que tu
peux chercher sur le web et creer des fichiers a la demande."""

# Aucun document ne correspond ET pas d'intention web explicite : on répond
# quand même utilement (culture générale / conversation) plutôt que de lancer
# une recherche web pour un rien.
GENERAL_PROMPT = """Pour cette question, reponds utilement et avec bon sens,
sans jamais lancer de recherche.
La question ne correspond a aucun document interne indexe. Selon le cas :
- petite conversation, propos personnel, remerciement -> reponds naturellement et brievement ;
- question de culture generale -> reponds si tu la connais, sans pretendre que cela vient des documents ;
- question qui devrait figurer dans les documents de l'entreprise -> dis simplement, sans dramatiser,
  que tu ne l'as pas trouvee dans les documents indexes.
N'invente jamais de faits specifiques a l'entreprise. Ne cite aucune source."""

# Message conversationnel (salutation, politesse...) : pas de recherche documentaire
_SMALLTALK = re.compile(
    r"^(salut|bonjour|bonsoir|hello|hey|coucou|yo|merci( beaucoup)?|ok|d'accord"
    r"|super|cool|parfait|top|ca va( et toi)?|ça va( et toi)?|comment vas[- ]tu"
    r"|comment ca va|comment ça va|au revoir|a plus|à plus|bonne (journee|journée|soiree|soirée)"
    r"|qui es[- ]tu|tu es qui|que sais[- ]tu faire|tu fais quoi|test|aide|help"
    # questions d'identité : réponse directe (l'identité est dans le prompt),
    # inutile de payer une pré-analyse ni une recherche documentaire
    r"|comment (tu )?t'?appelles?[- ]?(tu)?|tu t'?appelles comment"
    r"|(c'est )?quoi ton nom|quel est ton nom|ton nom|qui t'a (cree|créé|fait))"
    r"[\s!?.,:)]*$",
    re.IGNORECASE,
)


# Énoncé personnel (présentation, préférence, demande de mémorisation) :
# réponse directe elle aussi, sans recherche documentaire — c'est de là que
# la mémoire tire l'essentiel de ses faits.
_PERSONAL = re.compile(
    r"\b(je m'appelle|je me nomme|mon (nom|prénom|prenom|rôle|role|poste|équipe|equipe)"
    r"|je suis \w|je travaille|je bosse|j'?ai \d+\s*ans|je préfère|je prefere|j'aime"
    r"|retiens( bien)? que|souviens[- ]toi|rappelle[- ]toi|note que|mémorise|memorise)",
    re.IGNORECASE,
)


def is_smalltalk(question: str) -> bool:
    q = question.strip()
    if len(q) <= 60 and _SMALLTALK.match(q):
        return True
    return len(q) <= 220 and bool(_PERSONAL.search(q))


VISION_SYSTEM_PROMPT = """Analyse les images jointes par l'utilisateur et decris ce qui est
pertinent pour sa question. Si des documents joints ou extraits sont fournis, cite-les
par leur nom. Ne jamais inventer de contenu."""

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre"]


def today_fr() -> str:
    """Date du jour en français (« mardi 7 juillet 2026 ») — indépendante de la
    locale système. Injectée dans le prompt pour que « hier », « cette semaine »
    aient un sens pour le modèle."""
    from datetime import date

    d = date.today()
    return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]} {d.year}"


def user_line(user_name: str = "") -> str:
    """Phrase qui présente l'interlocuteur à l'assistant.

    Le nom fourni fait autorité sur tout le reste (faits mémorisés, contenu des
    documents) : c'est précisément un fait mémorisé erroné (« Je m'appelle Léo »,
    extrait d'une réponse de l'assistant) qui faisait appeler l'utilisateur par
    un prénom qu'il n'avait jamais donné.
    """
    name = " ".join((user_name or "").split())
    if name:
        return (f"L'utilisateur avec qui tu échanges s'appelle « {name} ». "
                "Si tu t'adresses à lui par son nom, utilise celui-là et aucun "
                "autre, même si un autre prénom apparaît dans les faits mémorisés, "
                "l'historique ou les documents.")
    return ("Tu ne connais pas le nom de l'utilisateur : ne l'appelle jamais par un "
            "prénom et n'en invente aucun.")


def system_prompt(role_prompt: str, settings: Settings, user_name: str = "",
                  memory_text: str = "") -> str:
    """Prompt système complet : identité de Jade, rôle du moment (documentaire,
    web, conversation, vision), date, interlocuteur, puis faits mémorisés.

    Point d'assemblage unique : l'identité et le nom de l'utilisateur sont ainsi
    garantis identiques sur TOUS les chemins de réponse.
    """
    parts = [
        IDENTITY.format(client=settings.client_name),
        role_prompt.format(client=settings.client_name),
        f"Nous sommes le {today_fr()}.",
        user_line(user_name),
    ]
    if memory_text:
        parts.append(
            "Faits mémorisés sur cet utilisateur (conversations précédentes, à "
            "utiliser s'ils sont pertinents). Ils peuvent être inexacts ou périmés ; "
            "le nom indiqué ci-dessus fait foi :\n" + memory_text)
    return "\n\n".join(parts)


HISTORY_LIMIT = 8  # 4 echanges


def _source_label(meta: dict) -> str:
    parts = [meta.get("filename", "?")]
    if meta.get("section"):
        parts.append(meta["section"])
    if meta.get("sheet"):
        parts.append(f"feuille {meta['sheet']}")
    if meta.get("pages"):
        parts.append(f"page(s) {meta['pages']}")
    return " — ".join(parts)


def retrieval_query(question: str, history: list[dict]) -> str:
    """Question de suivi courte ("et pour X ?") : enrichit la requete de
    retrieval avec la question utilisateur precedente pour la coreference."""
    if len(question) < 30 and history:
        prev_user = [m["content"] for m in history if m["role"] == "user"]
        if prev_user:
            return f"{prev_user[-1]} {question}"
    return question


# Nombre de candidats récupérés par voie (vectoriel / BM25). Large exprès :
# le pipeline standard est retrieval top-50 -> reranking cross-encoder -> top-8.
RECALL = 50
# Candidats passés au cross-encoder après fusion RRF : 24 ≈ 1 s sur 2 threads
# CPU (50 ≈ 2,1 s mesurés) — le rappel au-delà du top-24 fusionné est marginal.
RERANK_POOL = 24


def retrieve_timed(
    question: str, history: list[dict], settings: Settings, embedder: Embedder, store: Store,
    bm25=None, reranker=None, readable=None,
) -> tuple[list[dict], dict]:
    """Retourne (hits, timings). Recherche hybride si bm25 est fourni :
    vectoriel + BM25 fusionnés (RRF), reranker optionnel. Sinon vectoriel seul.

    Nombre de sources adaptatif : 0 à 10 selon la pertinence — parfois une seule,
    parfois aucune (question hors du périmètre des documents).

    `readable` : prédicat optionnel `chemin -> bool` (droits NTFS de l'utilisateur
    courant). Appliqué AVANT la troncature finale : un utilisateur restreint reçoit
    ainsi jusqu'à N extraits *lisibles* au lieu de « N moins les masqués » (sinon
    des extraits lisibles plus bas dans le classement seraient perdus)."""
    from .hybrid import rrf_fuse

    def _ok(c: dict) -> bool:
        return readable is None or readable((c.get("meta") or {}).get("path"))

    query = retrieval_query(question, history)
    t0 = time.perf_counter()
    embedding = embedder.embed_query(query)
    t1 = time.perf_counter()

    try:
        vec_hits = store.query_ids(embedding, max(settings.top_k, RECALL))
    except Exception as e:  # noqa: BLE001 — ex. index d'une autre dimension
        # fenêtre de migration (changement de modèle d'embeddings, réindexation
        # en cours) : le vectoriel est indisponible, BM25 continue de répondre.
        import logging

        logging.getLogger(__name__).warning(
            "Recherche vectorielle indisponible (%s) — repli BM25 seul", e)
        vec_hits = []
    t2 = time.perf_counter()

    if not (settings.hybrid_enabled and bm25):
        # vectoriel seul : seuil absolu + relatif
        hits = [{"text": h["text"], "meta": h["meta"], "score": h["score"]} for h in vec_hits]
        if hits:
            cutoff = max(settings.min_score, hits[0]["score"] - 0.2)
            hits = [h for h in hits if h["score"] >= cutoff and _ok(h)][:10]
        return hits, {"embed_ms": round((t1 - t0) * 1000),
                      "search_ms": round((t2 - t1) * 1000)}

    # --- hybride : fusion vectoriel + BM25 ---
    bm_ids = bm25.search(query, RECALL)
    t3 = time.perf_counter()
    by_id = {h["id"]: {"text": h["text"], "meta": h["meta"], "score": h["score"]} for h in vec_hits}
    missing = [i for i in bm_ids if i not in by_id]
    for i, rec in store.get_by_ids(missing).items():
        by_id[i] = {"text": rec["text"], "meta": rec["meta"], "score": None}

    fused = rrf_fuse([[h["id"] for h in vec_hits], bm_ids])
    order = sorted(fused, key=lambda i: fused[i], reverse=True)
    candidates = [dict(by_id[i]) for i in order if i in by_id]

    timings = {"embed_ms": round((t1 - t0) * 1000),
               "search_ms": round((t2 - t1) * 1000),
               "bm25_ms": round((t3 - t2) * 1000)}

    if reranker and candidates:
        # pipeline qualité : fusion RRF -> cross-encoder sur le top-24 -> top-8.
        # La similarité d'embedding trie « ce qui ressemble » ; le cross-encoder
        # juge « ce qui répond vraiment » (scores sigmoïde 0..1).
        t4 = time.perf_counter()
        pool = candidates[:RERANK_POOL]
        scores = reranker.scores(question, [c["text"] for c in pool])
        for c, s in zip(pool, scores):
            c["score"] = round(s, 4)
        pool = sorted(pool, key=lambda c: c["score"], reverse=True)
        timings["rerank_ms"] = round((time.perf_counter() - t4) * 1000)
        best = pool[0]["score"] if pool else 0
        hits = [c for c in pool
                if c["score"] >= max(settings.min_score, best - 0.25) and _ok(c)][:8]
        return hits, timings

    # sans reranker : garder les candidats pertinents — vectoriel au-dessus du
    # seuil, OU parmi les TOUT MEILLEURS BM25 (correspondance de termes exacte :
    # référence, IP, numéro). Limiter aux 5 premiers BM25 évite de noyer la
    # réponse sous des extraits qui ne partagent que des mots communs.
    bm_top = set(bm_ids[:5])
    keep = []
    for i in order:
        c = by_id.get(i)
        if not c:
            continue
        if not _ok(c):
            continue
        if (c["score"] is not None and c["score"] >= settings.min_score) or i in bm_top:
            keep.append(c)
    return keep[:10], timings


def format_sources(hits: list[dict]) -> list[dict]:
    return [
        {
            "n": i + 1,
            "label": _source_label(h["meta"]),
            "filename": h["meta"].get("filename", "?"),
            "path": h["meta"].get("path", ""),
            "url": h["meta"].get("url", ""),
            "web": bool(h["meta"].get("web")),
            "detail": h["meta"].get("section") or h["meta"].get("sheet")
            or (f"page(s) {h['meta']['pages']}" if h["meta"].get("pages") else ""),
            "score": h["score"],
            "text": h["text"],
        }
        for i, h in enumerate(hits)
    ]


def build_messages(
    question: str,
    hits: list[dict],
    history: list[dict],
    settings: Settings,
    attachments_text: str = "",
    images: list[str] | None = None,
    memory_text: str = "",
    user_name: str = "",
) -> list[dict]:
    """Messages Ollama : system + historique (texte brut) + question courante
    accompagnee des extraits recuperes, des pieces jointes texte et des
    images (base64, pour un modele de vision)."""
    is_web = bool(hits and hits[0]["meta"].get("web"))
    context_blocks: list[str] = []
    if hits:
        context_blocks.append(
            "Extraits de pages web publiques (recherche web) :" if is_web
            else "Extraits de documents :"
        )
        context_blocks.append("")
        for i, hit in enumerate(hits, start=1):
            context_blocks.append(f"[Source {i}] {_source_label(hit['meta'])}")
            context_blocks.append(hit["text"])
            context_blocks.append("")
    if attachments_text:
        context_blocks.append(
            "Documents joints par l'utilisateur a cette question "
            "(cite-les par leur nom de fichier, pas par [Source N]) :"
        )
        context_blocks.append(attachments_text)
        context_blocks.append("")
    context_blocks.append(f"Question : {question}")

    if images:
        prompt = VISION_SYSTEM_PROMPT
    elif is_web:
        prompt = WEB_SYSTEM_PROMPT
    else:
        prompt = SYSTEM_PROMPT
    system = system_prompt(prompt, settings, user_name=user_name,
                           memory_text=memory_text)
    messages = [{"role": "system", "content": system}]
    messages.extend(history[-HISTORY_LIMIT:])
    user_msg: dict = {"role": "user", "content": "\n".join(context_blocks)}
    if images:
        user_msg["images"] = images
    messages.append(user_msg)
    return messages
