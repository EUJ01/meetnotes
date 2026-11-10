"""A minimal client for any OpenAI-compatible chat endpoint (LM Studio, Ollama, llama.cpp, vLLM, OpenAI, OpenRouter,
Gemini, Anthropic). Standard library only."""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from meetnotes import Fail

RETRIES = 2
LOCAL = {"localhost", "127.0.0.1", "::1"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # never follow: urllib would send the Authorization header on to the new host


OPEN = urllib.request.build_opener(_NoRedirect()).open  # also used for Telegram (the bot token is in the URL)


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
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" and parts.hostname not in LOCAL:
            raise LLMError(f"refusing to send the API key over plain http to {parts.hostname}: use an https base_url", 2)
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")


def _wait(err, attempt):
    after = err.headers.get("Retry-After") if getattr(err, "headers", None) else None
    try:
        return min(float(after), 60.0)
    except (TypeError, ValueError):
        return 2.0 * 2 ** attempt  # 2 s, then 4 s


def _stderr(msg):
    print(msg, file=sys.stderr, flush=True)


def _read(r, url, log):
    """(content, finish_reason, tool calls) from a streamed reply (server-sent events) or a plain JSON one.
    Tool calls: [{"id", "name", "arguments" (a JSON string)}]."""
    if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
        data = json.loads(r.read().decode("utf-8"))
        try:
            choice = data["choices"][0]
            calls = [{"id": c.get("id", ""), "name": c["function"]["name"], "arguments": c["function"].get("arguments") or "{}"}
                     for c in choice["message"].get("tool_calls") or []]
            return choice["message"].get("content"), choice.get("finish_reason"), calls
        except (KeyError, IndexError, TypeError, AttributeError):
            raise LLMError(f"{url} sent an unexpected reply: {json.dumps(data)[:300]}")
    parts, finish, seen, last, calls = [], None, 0, time.monotonic(), {}
    for raw in r:  # the socket timeout applies to each read: a slow model is fine as long as it keeps writing
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if event.get("error"):
            raise LLMError(f"{url} reported an error: {json.dumps(event['error'])[:300]}")
        for ch in event.get("choices") or []:
            delta = ch.get("delta") or {}
            text = delta.get("content") or ""
            parts.append(text)
            seen += len(text) + len(delta.get("reasoning_content") or delta.get("reasoning") or "")
            finish = ch.get("finish_reason") or finish
            for tc in delta.get("tool_calls") or []:  # streamed in pieces, joined by index
                c = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                c["id"] = tc.get("id") or c["id"]
                fn = tc.get("function") or {}
                c["name"] += fn.get("name") or ""
                c["arguments"] += fn.get("arguments") or ""
        if time.monotonic() - last > 30:
            log(f"  still writing ({seen:,} characters so far, reasoning included)")
            last = time.monotonic()
    return "".join(parts), finish, [calls[i] for i in sorted(calls)]


def _is_timeout(e):
    return isinstance(e, (TimeoutError, socket.timeout)) or isinstance(getattr(e, "reason", None), (TimeoutError, socket.timeout))


def chat(cfg, messages, opener=OPEN, sleep=time.sleep, log=_stderr):
    """Send messages, return the reply text (see complete)."""
    content = complete(cfg, messages, opener=opener, sleep=sleep, log=log)["content"]
    if not content or not content.strip():
        raise LLMError(f"{_url(cfg, '/chat/completions')} sent an empty reply (model {cfg['model']}). "
                       "Try a larger max_tokens or another model.")
    return content


def complete(cfg, messages, tools=None, opener=OPEN, sleep=time.sleep, log=_stderr):
    """Send messages (and tool definitions), return {"content", "tool_calls"}. The reply is streamed, so `timeout`
    is the longest silence allowed, not the length of the whole answer. Retries 429, 5xx and refused connections
    twice; never retries a timeout (the server may still be working on the first request, and a retry would queue
    a second one)."""
    if not cfg.get("model"):
        raise LLMError("set [llm] model in config.toml (the model name your server or provider uses)", 2)
    url = _url(cfg, "/chat/completions")
    body = {"model": cfg["model"], "messages": messages, "max_tokens": int(cfg.get("max_tokens") or 4000), "stream": True}
    if cfg.get("temperature") is not None:
        body["temperature"] = cfg["temperature"]
    if tools:
        body["tools"] = tools
    timeout = cfg.get("timeout") or 300
    for attempt in range(RETRIES + 1):
        try:
            with opener(_request(url, cfg, body), timeout=timeout) as r:
                content, finish, calls = _read(r, url, log)
            break
        except urllib.error.HTTPError as e:  # before URLError: HTTPError is a subclass of it
            detail = e.read().decode("utf-8", "replace")[:300]
            if (e.code == 429 or e.code >= 500) and attempt < RETRIES:
                sleep(_wait(e, attempt))
                continue
            hint = (" (check the API key and api_key_env)" if e.code in (401, 403) else
                    f" (a redirect to {e.headers.get('Location')}: put the final URL in base_url)" if 300 <= e.code < 400
                    else "")
            raise LLMError(f"{url} returned HTTP {e.code}{hint}: {detail}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as e:
            if _is_timeout(e):
                raise LLMError(f"no reply from {url} for {timeout} s. A slow model may need a larger [llm] timeout; "
                               "check the server is still running.")
            if attempt < RETRIES:
                sleep(_wait(e, attempt))
                continue
            raise LLMError(f"cannot reach {url}: {getattr(e, 'reason', e)}. Is the server running and base_url right?")
    if finish == "length":  # cut off: it can still hold all three headings, so check here
        raise LLMError(f"the reply was cut off at max_tokens ({body['max_tokens']}): raise [llm] max_tokens")
    return {"content": content or "", "tool_calls": calls}


def models(cfg, opener=OPEN):
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
