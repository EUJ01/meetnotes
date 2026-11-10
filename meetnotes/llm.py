"""A minimal client for any OpenAI-compatible chat endpoint (LM Studio, Ollama, llama.cpp, vLLM, OpenAI, OpenRouter,
Gemini, Anthropic). Standard library only."""
import json
import os
import socket
import time
import urllib.error
import urllib.request

from meetnotes import Fail

RETRIES = 2


class LLMError(Fail):
    pass


def _key(cfg):
    name = cfg.get("api_key_env") or ""
    return os.environ.get(name, "").strip() if name else ""


def _url(cfg, path):
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise LLMError("no LLM configured: set [llm] base_url and model in config.toml, "
                       "or use the agent route (meetnotes new-update, see AGENTS.md)", 2)
    return base + path


def _request(url, cfg, body=None):
    headers = {"Content-Type": "application/json", "User-Agent": "meetnotes"}
    key = _key(cfg)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")


def _wait(err, attempt):
    after = err.headers.get("Retry-After") if getattr(err, "headers", None) else None
    try:
        return min(float(after), 60.0)
    except (TypeError, ValueError):
        return 2.0 * 2 ** attempt  # 2 s, then 4 s


def chat(cfg, messages, opener=urllib.request.urlopen, sleep=time.sleep):
    """Send messages, return the reply text. Retries timeouts, 429 and 5xx twice, then raises LLMError."""
    if not cfg.get("model"):
        raise LLMError("set [llm] model in config.toml (the model name your server or provider uses)", 2)
    url = _url(cfg, "/chat/completions")
    body = {"model": cfg["model"], "messages": messages, "max_tokens": int(cfg.get("max_tokens") or 4000)}
    if cfg.get("temperature") is not None:
        body["temperature"] = cfg["temperature"]
    for attempt in range(RETRIES + 1):
        try:
            with opener(_request(url, cfg, body), timeout=cfg.get("timeout") or 300) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:  # before URLError: HTTPError is a subclass of it
            detail = e.read().decode("utf-8", "replace")[:300]
            if (e.code == 429 or e.code >= 500) and attempt < RETRIES:
                sleep(_wait(e, attempt))
                continue
            hint = " (check the API key and api_key_env)" if e.code in (401, 403) else ""
            raise LLMError(f"{url} returned HTTP {e.code}{hint}: {detail}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as e:
            if attempt < RETRIES:
                sleep(_wait(e, attempt))
                continue
            reason = getattr(e, "reason", e)
            raise LLMError(f"cannot reach {url}: {reason}. Is the server running and base_url right?")
    try:
        choice = data["choices"][0]
        content = choice["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise LLMError(f"{url} sent an unexpected reply: {json.dumps(data)[:300]}")
    if choice.get("finish_reason") == "length":  # cut off: it can still hold all three headings, so check here
        raise LLMError(f"the reply was cut off at max_tokens ({body['max_tokens']}): raise [llm] max_tokens")
    if not content or not content.strip():
        raise LLMError(f"{url} sent an empty reply (model {cfg['model']}). Try a larger max_tokens or another model.")
    return content


def models(cfg, opener=urllib.request.urlopen):
    """The model ids the endpoint lists (for meetnotes doctor)."""
    url = _url(cfg, "/models")
    try:
        with opener(_request(url, cfg), timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(f"{url} returned HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as e:
        raise LLMError(f"cannot reach {url}: {getattr(e, 'reason', e)}")
    return [m.get("id", "?") for m in data.get("data", [])]
