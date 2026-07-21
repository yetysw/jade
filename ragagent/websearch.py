"""Recherche web de repli — quand la question sort du perimetre des documents.

Deux moteurs, dans l'ordre de preference :
1. SearXNG self-hosted (SEARXNG_URL, ex. sur AI01) — cible production : le poste
   client ne parle qu'a l'infrastructure Jade.
2. DuckDuckGo HTML (sans cle API) — repli automatique si SEARXNG_URL est vide.

Chaque appel sortant (recherche + telechargement de pages) est journalise dans
l'audit. Desactive en mode hors ligne.
"""

from __future__ import annotations

import html as htmllib
import logging
import re
import time
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from .audit import log_outbound
from .config import Settings

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

MAX_PAGE_CHARS = 6000

# Detection d'intention web explicite dans la question
_WEB_INTENT = re.compile(
    r"(sur (le |l')?(web|internet)|en ligne|news|actualit|derni[eè]res nouvelles"
    r"|site (web )?de|cherche sur|recherche web|googl)",
    re.IGNORECASE,
)


def wants_web(question: str) -> bool:
    return bool(_WEB_INTENT.search(question))


# Question contextuelle (« vérifie si TES informations sont à jour », « c'est
# toujours vrai ? ») : envoyée telle quelle à un moteur, elle ne veut rien dire.
# On la complète avec la question utilisateur précédente.
_REFERENTIAL = re.compile(
    r"\b(tes|ta |ton |ces|cette|cela|c'est|ça|toujours|encore|v[ée]rifie|[àa] jour)\b",
    re.IGNORECASE,
)


def web_query(question: str, history: list[dict]) -> str:
    """Requête moteur : enrichie du contexte si la question est référentielle."""
    if history and (_REFERENTIAL.search(question) or len(question) < 30):
        prev = [m["content"] for m in history if m.get("role") == "user"]
        if prev:
            return f"{prev[-1][:150]} {question}"[:250]
    return question


# Fraîcheur : une question sur « hier »/« aujourd'hui » doit interroger les
# resultats des dernieres 24 h, pas la page d'accueil intemporelle d'un site.
_FRESH_DAY = re.compile(
    r"\b(hier|aujourd'?hui|ce (matin|soir)|cette nuit|en ce moment|maintenant)\b", re.I
)
_FRESH_WEEK = re.compile(
    r"\b(derni[eè]re?s?|r[ée]cent(e|es|s)?|cette semaine|actualit[ée]s?|news|nouvelles)\b",
    re.I,
)


def _time_range(query: str) -> str:
    """'' | 'day' | 'week' — filtre de fraîcheur pour les moteurs."""
    if _FRESH_DAY.search(query):
        return "day"
    if _FRESH_WEEK.search(query):
        return "week"
    return ""


def search(query: str, settings: Settings, max_results: int = 3) -> list[dict]:
    """Retourne [{title, url, snippet}] — [] si echec.

    SearXNG (interne Jade) est prioritaire ; en cas d'indisponibilité (token
    Cloudflare non autorisé, API JSON désactivée, aucun résultat), repli
    automatique sur DuckDuckGo pour ne jamais laisser l'utilisateur sans réponse.
    """
    if settings.searxng_url:
        try:
            hits = _search_searxng(query, settings, max_results)
            if hits:
                return hits
            log.warning("SearXNG : aucun résultat exploitable, repli DuckDuckGo")
        except Exception as e:  # noqa: BLE001
            log.warning("SearXNG indisponible (%s), repli DuckDuckGo", e)
    try:
        return _search_ddg(query, settings, max_results)
    except Exception as e:  # noqa: BLE001
        log.warning("Recherche web echouee : %s", e)
        return []


def _search_searxng(query: str, settings: Settings, max_results: int) -> list[dict]:
    url = f"{settings.searxng_url}/search"
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/html;q=0.9",
        "Accept-Language": "fr-CH,fr;q=0.9,en;q=0.8",
    }
    # Service token Cloudflare Access propre à l'instance SearXNG (distinct du LLM)
    if settings.searxng_cf_client_id and settings.searxng_cf_client_secret:
        headers["CF-Access-Client-Id"] = settings.searxng_cf_client_id
        headers["CF-Access-Client-Secret"] = settings.searxng_cf_client_secret
    log_outbound(settings.outbound_log, "GET", f"{url}?q={quote_plus(query)}", headers, None)
    params = {"q": query, "format": "json", "language": "fr", "safesearch": "0"}
    tr = _time_range(query)
    if tr:
        params["time_range"] = tr

    # 1) API JSON si activée dans SearXNG (résultats + extraits structurés)
    try:
        rj = httpx.get(
            url, params=params,
            headers=headers, timeout=15, follow_redirects=True,
        )
        if rj.status_code == 200 and "json" in rj.headers.get("content-type", ""):
            hits = [
                {"title": r.get("title", "?"), "url": r["url"], "snippet": r.get("content", "")}
                for r in rj.json().get("results", [])[:max_results]
                if r.get("url")
            ]
            if hits:
                return hits
    except Exception as e:  # noqa: BLE001 — on tente le repli HTML
        log.debug("SearXNG API JSON indisponible (%s), lecture de la page HTML", e)

    # 2) repli : page de résultats HTML (fonctionne même si l'API JSON est désactivée)
    hparams = {"q": query, "language": "fr"}
    if tr:
        hparams["time_range"] = tr
    rh = httpx.get(
        url, params=hparams,
        headers=headers, timeout=15, follow_redirects=True,
    )
    rh.raise_for_status()
    if "cloudflareaccess.com" in str(rh.url):
        raise RuntimeError(
            "redirigé vers Cloudflare Access — service token non autorisé "
            "(policy « Service Auth » manquante sur l'application SearXNG)"
        )
    return _parse_searxng_html(rh.text, max_results)


def _parse_searxng_html(html: str, max_results: int) -> list[dict]:
    """Extrait titre/url/extrait des <article class="result…"> d'une page SearXNG."""
    results: list[dict] = []
    for block in re.findall(
        r'<article[^>]*class="[^"]*result[^"]*".*?</article>', html, re.S
    ):
        m = re.search(r'<h3>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        link = htmllib.unescape(m.group(1))
        if not link.startswith("http"):
            continue
        title = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        cm = re.search(r'<p[^>]*class="content"[^>]*>(.*?)</p>', block, re.S)
        snippet = ""
        if cm:
            snippet = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", cm.group(1)))).strip()
        if title and not any(r["url"] == link for r in results):
            results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _ddg_deref(href: str) -> str:
    href = htmllib.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:  # lien de redirection DDG
        q = parse_qs(urlparse(href).query)
        href = unquote(q.get("uddg", [href])[0])
    return href


def _search_ddg(query: str, settings: Settings, max_results: int) -> list[dict]:
    """DuckDuckGo sans clé API. Essaie l'endpoint HTML puis, en repli, l'endpoint
    « lite » (souvent plus tolérant côté anti-scraping)."""
    endpoints = ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/")
    data = {"q": query}
    tr = _time_range(query)
    if tr:
        data["df"] = {"day": "d", "week": "w"}[tr]  # filtre de fraîcheur DDG
    last_error: Exception | None = None
    for url in endpoints:
        try:
            log_outbound(settings.outbound_log, "POST", url, {}, data)
            resp = httpx.post(
                url, data=data, headers={"User-Agent": UA},
                timeout=15, follow_redirects=True,
            )
            resp.raise_for_status()
            results: list[dict] = []
            # endpoint HTML : liens class="result__a" ; endpoint lite : liens
            # de résultats dans un tableau — on capte les deux formes de <a href>.
            for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S):
                href = m.group(1)
                if "duckduckgo.com" in href and "uddg=" not in href:
                    continue
                href = _ddg_deref(href)
                if not href.startswith("http") or "duckduckgo.com" in href:
                    continue
                title = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
                if title and len(title) > 1 and not any(r["url"] == href for r in results):
                    results.append({"title": title, "url": href, "snippet": ""})
                if len(results) >= max_results:
                    break
            if results:
                return results
        except Exception as e:  # noqa: BLE001 — on tente l'endpoint suivant
            last_error = e
            log.warning("DuckDuckGo (%s) a échoué : %s", url, e)
    if last_error:
        raise last_error
    return []


def fetch_page(url: str, settings: Settings) -> str:
    """Telecharge une page et la reduit en texte brut (~6000 caracteres max)."""
    log_outbound(settings.outbound_log, "GET", url, {}, None)
    resp = httpx.get(
        url, headers={"User-Agent": UA}, timeout=10,
        follow_redirects=True,
    )
    resp.raise_for_status()
    if "text/html" not in resp.headers.get("content-type", "text/html"):
        return ""
    return _html_to_text(resp.text)[:MAX_PAGE_CHARS]


def _html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style|nav|header|footer|svg|noscript)[^>]*>.*?</\1>",
                  " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = htmllib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def web_context(question: str, settings: Settings,
                search_query: str | None = None) -> tuple[list[dict], dict]:
    """Recherche + telechargement. Retourne (hits_web, timings).

    hits_web a la meme forme que les hits locaux ({text, meta, score}) pour
    reutiliser build_messages() ; meta contient url + hostname.
    search_query : requete moteur (ex. enrichie du contexte) ; defaut = question.
    """
    t0 = time.perf_counter()
    # on ramene plus de candidats que necessaire : les pages sans substance
    # (accueil, page de navigation) sont ecartees au profit des suivantes
    results = search(search_query or question, settings, max(settings.web_results * 2, 6))
    t1 = time.perf_counter()

    def _hit(r: dict, text: str) -> dict:
        return {
            "text": text,
            "score": None,
            "meta": {
                "filename": r["title"],
                "section": urlparse(r["url"]).hostname or "",
                "url": r["url"],
                "web": True,
            },
        }

    MIN_SUBSTANCE = 500  # caracteres de texte reel pour qu'une page « compte »
    hits: list[dict] = []
    weak: list[dict] = []  # pages maigres, gardees en dernier recours
    for r in results:
        if len(hits) >= settings.web_results:
            break
        try:
            text = fetch_page(r["url"], settings)
        except Exception as e:
            log.warning("Page web ignoree (%s) : %s", r["url"], e)
            text = ""
        if not text and r.get("snippet"):
            text = r["snippet"]
        if not text:
            continue
        if len(text) >= MIN_SUBSTANCE:
            hits.append(_hit(r, text))
        else:
            weak.append(_hit(r, text))
    while len(hits) < settings.web_results and weak:
        hits.append(weak.pop(0))
    t2 = time.perf_counter()
    timings = {
        "web_search_ms": round((t1 - t0) * 1000),
        "web_fetch_ms": round((t2 - t1) * 1000),
    }
    return hits, timings
