"""Client HTTPS sortant vers le LLM central (Ollama sur AI01, via Cloudflare Access).

- En-tetes CF-Access-Client-Id/Secret (service token) si configures.
- Chaque requete est journalisee AVANT emission (audit.py).
- Reponses non-JSON / 403 Cloudflare Access signalees comme erreur d'auth claire.
- keep_alive transmis a Ollama pour garder le modele charge en VRAM entre les
  questions (evite ~5-10 s de rechargement).
- chat_stream() : streaming token par token (NDJSON Ollama) avec stats de fin
  (duree prompt eval / generation, nb tokens).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

import httpx

from .audit import log_outbound
from .config import Settings

log = logging.getLogger(__name__)

RETRY_DELAYS = [2, 5]  # 3 tentatives au total


class LLMError(Exception):
    pass


class OllamaClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.headers = {"Content-Type": "application/json"}
        if settings.cf_access_client_id and settings.cf_access_client_secret:
            self.headers["CF-Access-Client-Id"] = settings.cf_access_client_id
            self.headers["CF-Access-Client-Secret"] = settings.cf_access_client_secret
        self._client = httpx.Client(
            timeout=httpx.Timeout(settings.request_timeout, connect=10.0),
            follow_redirects=False,
        )

    # ------------------------------------------------------------------ utils

    def _raise_for_status(self, status: int, text: str, url: str) -> None:
        if status in (301, 302, 303, 307, 308):
            raise LLMError(
                "Redirection recue (probable page de login Cloudflare Access). "
                "Verifier CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET."
            )
        if status >= 400:
            if "cloudflare access" in text[:2000].lower():
                raise LLMError(
                    f"Acces refuse par Cloudflare Access (HTTP {status}). "
                    "Renseigner CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET dans .env "
                    "(service token autorise dans la policy Access de l'application)."
                )
            raise LLMError(f"Erreur HTTP {status} de {url} : {text[:300]}")

    def _request(self, method: str, path: str, body: dict | None = None,
                 retry: bool = True, timeout: float | None = None) -> dict:
        """retry=False : une seule tentative (appels courts routeur/titre/suivi/
        warmup — sous saturation GPU, Ollama renvoie des 5xx ; réessayer 3× ces
        appels ne ferait qu'empiler des jobs et aggraver la saturation).
        timeout : plafond dédié (s) pour ne pas qu'un petit appel reste 120 s en
        file derrière de grosses générations."""
        url = f"{self.s.ollama_url}{path}"
        log_outbound(self.s.outbound_log, method, url, self.headers, body)
        last_error: Exception | None = None
        attempts = len(RETRY_DELAYS) + 1 if retry else 1
        for attempt in range(attempts):
            try:
                kw = {} if timeout is None else {"timeout": timeout}
                resp = self._client.request(
                    method, url, headers=self.headers, json=body, **kw)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                self._raise_for_status(resp.status_code, resp.text, url)
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    snippet = resp.text[:200].replace("\n", " ")
                    raise LLMError(
                        "Reponse non-JSON recue — probablement la page d'authentification "
                        f"Cloudflare Access. Debut de la reponse : {snippet!r}"
                    )
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout,
                    httpx.HTTPStatusError) as e:
                last_error = e
                if retry and attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    log.warning("Appel LLM echoue (%s), nouvel essai dans %ds", e, delay)
                    time.sleep(delay)
                else:
                    break
        raise LLMError(f"LLM central injoignable apres 3 tentatives : {last_error}")

    # ------------------------------------------------------------------- API

    def check(self) -> list[str]:
        """GET /api/tags — verifie l'acces et retourne la liste des modeles."""
        data = self._request("GET", "/api/tags")
        return [m.get("name", "?") for m in data.get("models", [])]

    def warmup(self) -> None:
        """Precharge en VRAM sur AI01 TOUS les modeles configures (pre-analyse,
        standard, performant) : evite les chargements a froid (~15-20 s) qui
        s'empilent sur les premieres questions et provoquent des timeouts."""
        models = []
        for m in (self.s.router_model, self.s.ollama_model, self.s.strong_model):
            if m and m not in models:
                models.append(m)
        for m in models:
            try:
                # charger AU BON num_ctx : Ollama recharge le modele (~8 s) si le
                # contexte demande differe de celui charge — on evite ce rechargement
                # sur la premiere vraie question en prechauffant deja a num_ctx.
                self._request(
                    "POST", "/api/generate",
                    {"model": m, "keep_alive": self.s.keep_alive,
                     "options": {"num_ctx": self.s.num_ctx}},
                    retry=False,  # au démarrage simultané de N sessions RDS, ne pas
                    # empiler 3× les préchauffages en cas de 5xx (saturation)
                )
                log.info("Modele %s precharge (num_ctx=%d)", m, self.s.num_ctx)
            except LLMError as e:
                log.warning("Prechargement de %s impossible : %s", m, e)

    def _chat_body(
        self, messages: list[dict], stream: bool,
        model: str | None = None, num_ctx: int | None = None,
        options: dict | None = None, think: bool | None = None,
    ) -> dict:
        # num_ctx explicite : sans lui, Ollama tronque silencieusement le contexte RAG
        opts = {"num_ctx": num_ctx or self.s.num_ctx, "temperature": 0.2}
        if options:
            opts.update(options)  # surcharge (routeur : temperature 0, num_predict court)
        body = {
            "model": model or self.s.ollama_model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.s.keep_alive,
            "options": opts,
        }
        # modèles à « raisonnement » (qwen3…) : think=False = pas de bloc <think>
        # (indispensable pour la pré-analyse, sinon la sortie structurée est noyée) ;
        # ignoré par les modèles sans thinking.
        if think is not None:
            body["think"] = think
        return body

    def chat(
        self, messages: list[dict], model: str | None = None,
        options: dict | None = None, think: bool | None = None,
        retry: bool = True, timeout: float | None = None,
    ) -> str:
        data = self._request(
            "POST", "/api/chat",
            self._chat_body(messages, stream=False, model=model, options=options, think=think),
            retry=retry, timeout=timeout,
        )
        try:
            return data["message"]["content"]
        except (KeyError, TypeError):
            raise LLMError(f"Reponse Ollama inattendue : {json.dumps(data)[:300]}")

    def chat_stream(
        self, messages: list[dict],
        model: str | None = None, num_ctx: int | None = None,
        think: bool | None = None,
    ) -> Iterator[dict]:
        """Yield {"delta": str} par token puis {"done": True, "stats": {...}}.

        stats : prompt_eval_ms, gen_ms, prompt_tokens, completion_tokens.
        model / num_ctx : surcharges (ex. modele de vision, contexte reduit).
        """
        url = f"{self.s.ollama_url}/api/chat"
        body = self._chat_body(messages, stream=True, model=model, num_ctx=num_ctx, think=think)
        log_outbound(self.s.outbound_log, "POST", url, self.headers, body)
        try:
            with self._client.stream("POST", url, headers=self.headers, json=body) as resp:
                if resp.status_code != 200:
                    text = resp.read().decode("utf-8", errors="replace")
                    self._raise_for_status(resp.status_code, text, url)
                    raise LLMError(f"HTTP {resp.status_code} : {text[:300]}")
                for line in resp.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        raise LLMError(
                            f"Flux non-JSON recu (auth Cloudflare ?) : {line[:200]!r}"
                        )
                    if data.get("error"):
                        raise LLMError(f"Erreur Ollama : {data['error']}")
                    if data.get("done"):
                        yield {
                            "done": True,
                            "stats": {
                                "prompt_eval_ms": round(data.get("prompt_eval_duration", 0) / 1e6),
                                "gen_ms": round(data.get("eval_duration", 0) / 1e6),
                                "prompt_tokens": data.get("prompt_eval_count", 0),
                                "completion_tokens": data.get("eval_count", 0),
                            },
                        }
                        return
                    delta = (data.get("message") or {}).get("content", "")
                    if delta:
                        yield {"delta": delta}
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise LLMError(f"LLM central injoignable : {e}")
        except httpx.ReadTimeout:
            raise LLMError("Timeout pendant la generation (REQUEST_TIMEOUT depasse)")

    def close(self) -> None:
        self._client.close()
