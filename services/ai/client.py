"""The one place Odin talks to an AI server.

Odin speaks the OpenAI-compatible API and nothing else: GET {base}/models for
the heartbeat, POST {base}/chat/completions for answers, with only the
standard fields (model, messages, temperature, max_tokens, response_format).
Ollama, llama.cpp's server, vLLM, LM Studio and the hosted providers all
answer it, so the server, its address and its software can change without a
line of Odin changing. Server tuning (threads, context size) belongs to the
server, never to a request.

Everything about the server is a policy (Settings → AI); the API key is
sealed like the Microsoft 365 secret. A server outside the private network is
refused unless an admin has allowed an external provider, so customer notes
cannot leave the building by a typo.
"""
import ipaddress
import json
import re
import socket
import time
from urllib.parse import urlsplit

import requests

KEY_SETTING = "ai.api_key"
LOCAL_SUFFIXES = (".lan", ".local", ".internal", ".home.arpa", ".localdomain")


class AIError(Exception):
    """A call that did not produce a usable answer. `reason` is written for
    the admin reading Settings → AI; `kind` is connect | auth | model |
    invalid | timeout | http."""

    def __init__(self, reason, kind="http"):
        super().__init__(reason)
        self.reason, self.kind = reason, kind


def config(db=None):
    """The server as configured now: base URL, model, key, timeout."""
    from db import get_db
    from policies import policy
    from services.sealed import unseal
    db = db or get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (KEY_SETTING,)).fetchone()
    return {"base_url": policy("ai_base_url", db), "model": policy("ai_model", db), "key": unseal(row[0]) if row else "",
            "timeout": policy("ai_timeout_s", db), "allow_external": policy("ai_allow_external", db)}


def is_local(url):
    """Does this address stay on the private network? Private, loopback and
    link-local IPs (also in the shorthand forms the HTTP library accepts,
    such as 134744072 for 8.8.8.8), and names whose every address is one.
    A name that does not resolve at all cannot be reached either: a
    single-label or .lan/.local-style name stays usable (the LAN's DNS may
    know it later), any other name is outside until it resolves privately.
    Checked again before every request, so a name later pointed outside is
    refused then."""
    # ponytail: resolved here and again by requests (a DNS rebinding window); pin the IP if that ever matters
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False
    try:
        return _private(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:   # 134744072, 0x8080808, 010.0.0.1, 10.1: the forms inet_aton (and so requests) reads as IPv4
        return _private(ipaddress.IPv4Address(socket.inet_aton(host)))
    except OSError:
        pass
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, None)}
    except OSError:
        return "." not in host or host.endswith(LOCAL_SUFFIXES)
    return bool(addrs) and all(_private(ipaddress.ip_address(a.split("%")[0])) for a in addrs)


def _private(ip):
    return ip.is_private or ip.is_loopback or ip.is_link_local


def address_problem(url, allow_external):
    """Why this base URL may not be used, or None."""
    if not url:
        return "No AI server address is set."
    if not allow_external and not is_local(url):
        return (f"{urlsplit(url).hostname} is outside the private network. Customer notes would leave the building: "
                "tick \"Allow an external AI provider\" first if that is intended.")
    return None


def _headers(cfg):
    h = {"Content-Type": "application/json"}
    if cfg.get("key"):
        h["Authorization"] = f"Bearer {cfg['key']}"
    return h


def _request(method, cfg, path, timeout, **kwargs):
    url = cfg["base_url"].rstrip("/") + path
    problem = address_problem(cfg["base_url"], cfg.get("allow_external"))
    if problem:
        raise AIError(problem, "connect")
    host = urlsplit(url).netloc
    try:
        resp = requests.request(method, url, headers=_headers(cfg), timeout=timeout, **kwargs)
    except requests.Timeout:
        raise AIError(f"{host} did not answer within {timeout} seconds", "timeout")
    except requests.RequestException:
        raise AIError(f"Cannot reach {host}: no server answering at that address", "connect")
    if resp.status_code in (401, 403):
        raise AIError("The server refused the API key", "auth")
    if resp.status_code == 404:
        raise AIError(f"{url} not found: the address must be the OpenAI-compatible base, usually ending in /v1", "http")
    if resp.status_code == 503:
        raise AIError("The server is busy (queue full); try again shortly", "timeout")
    if resp.status_code >= 400:
        raise AIError(f"The server answered HTTP {resp.status_code}: {resp.text[:160]}", "http")
    try:
        return resp.json()
    except ValueError:
        raise AIError(f"{url} did not answer with JSON: not an OpenAI-compatible server", "http")


def list_models(cfg, timeout=10):
    """[{id, created}] from GET {base}/models."""
    data = _request("GET", cfg, "/models", timeout)
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise AIError("No model list at /models: not an OpenAI-compatible server", "http")
    return [{"id": str(m.get("id")), "created": m.get("created")} for m in items if isinstance(m, dict) and m.get("id")]


def find_model(models, name):
    """The configured model in the server's list. Ollama lists "P24-AI:latest"
    for "P24-AI", so an untagged name also matches its :latest."""
    for m in models:
        if m["id"] == name or (":" not in name and m["id"] == f"{name}:latest"):
            return m
    return None


def fingerprint(model):
    """Changes whenever the model behind the name is rebuilt or replaced:
    its id and `created` stamp, both standard fields."""
    return f"{model['id']}@{model.get('created')}"


def _log_call(log, cfg, messages, seconds, data=None, error=None):
    """One row in ai_calls per request (the AI server's guide asks for it):
    never allowed to break the call it records."""
    try:
        from datetime import datetime
        from db import get_db
        usage = (data or {}).get("usage") or {}
        db = get_db()
        db.execute("INSERT INTO ai_calls (at, feature, job_id, project_id, username, model, input_chars, prompt_tokens, completion_tokens, seconds, ok, error) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (datetime.utcnow().replace(microsecond=0).isoformat(), log.get("feature"), log.get("job_id"), log.get("project_id"), log.get("user"),
                    (data or {}).get("model") or cfg["model"], sum(len(m["content"]) for m in messages), usage.get("prompt_tokens"),
                    usage.get("completion_tokens"), seconds, 0 if error else 1, error))
        db.commit()
    except Exception:  # noqa: BLE001
        pass


def chat(cfg, messages, schema, max_tokens=800, temperature=0.3, log=None):
    """One answer, parsed and checked against `schema`. Returns (data, meta)
    with meta = {model, seconds, usage}. Raises AIError. Every request is
    recorded in ai_calls, with `log` naming the feature, job, project and person."""
    body = {"model": cfg["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}}
    started = time.monotonic()
    try:
        data = _request("POST", cfg, "/chat/completions", cfg.get("timeout") or 300, json=body)
    except AIError as exc:
        _log_call(log or {}, cfg, messages, round(time.monotonic() - started, 1), error=exc.reason[:300])
        raise
    seconds = round(time.monotonic() - started, 1)
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        _log_call(log or {}, cfg, messages, seconds, data, "no message in the answer")
        raise AIError("The answer had no message: not an OpenAI-compatible reply", "invalid")
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())   # some servers fence JSON even when asked not to
    try:
        value = json.loads(content)
    except ValueError:
        _log_call(log or {}, cfg, messages, seconds, data, "answer was not JSON")
        raise AIError(f"The answer was not JSON: {content[:120]!r}", "invalid")
    problems = schema_problems(schema, value)
    if problems:
        _log_call(log or {}, cfg, messages, seconds, data, "answer did not match its form")
        raise AIError("The answer did not match its form: " + "; ".join(problems[:3]), "invalid")
    _log_call(log or {}, cfg, messages, seconds, data)
    return value, {"model": data.get("model") or cfg["model"], "seconds": seconds, "usage": data.get("usage") or {}}


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}


def schema_problems(schema, value, path="answer"):
    """The JSON-schema subset Odin's features use: type, properties,
    required, items, enum, minItems, maxItems, maxLength. Returns a list of
    problems, empty when the value fits.
    ponytail: a subset, not a full validator; add jsonschema if a feature needs more."""
    t = schema.get("type")
    if t:
        ok = isinstance(value, _TYPES[t]) and not (t in ("integer", "number") and isinstance(value, bool))
        if not ok:
            return [f"{path} should be {t}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path} should be one of {', '.join(map(str, schema['enum']))}"]
    out = []
    if t == "string" and "maxLength" in schema and len(value) > schema["maxLength"]:
        out.append(f"{path} is longer than {schema['maxLength']} characters")
    if t == "object":
        for key in schema.get("required", ()):
            if key not in value:
                out.append(f"{path}.{key} is missing")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                out += schema_problems(sub, value[key], f"{path}.{key}")
    if t == "array":
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path} needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path} has more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                out += schema_problems(schema["items"], item, f"{path}[{i}]")
    return out
