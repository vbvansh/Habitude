"""Check which LLM API keys in .env are working.

Usage:
    python scripts/check_keys.py            # check every key that is filled in
    python scripts/check_keys.py opencode   # check just one provider

Keys are read from .env and never printed.
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

from dotenv import load_dotenv

USER_AGENT = "habitude-keycheck/0.1"

# What common HTTP status codes mean for an API key.
STATUS_MEANING = {
    200: "OK - working",
    400: "Bad request - key may be fine, but the request was rejected",
    401: "Unauthorized - key is wrong, expired, or revoked",
    402: "Payment required - no active subscription or no credits left",
    403: "Forbidden - key exists but is not allowed to do this",
    404: "Not found - wrong address or model name",
    429: "Too many requests - rate limit or quota used up",
}


def call(url, headers, body=None):
    """Send one web request. Returns (status_code, response_headers, parsed_body)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", USER_AGENT)
    if data:
        req.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        req.add_header(name, value)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, resp_headers, raw = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:  # the server answered, but with an error
        status, resp_headers, raw = err.code, dict(err.headers), err.read()

    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = raw.decode(errors="replace")[:300]
    return status, resp_headers, parsed


def limit_headers(headers):
    """Pick out response headers that talk about limits or quota."""
    words = ("limit", "remaining", "reset", "quota")
    return {k: v for k, v in headers.items() if any(w in k.lower() for w in words)}


def check_opencode(key):
    base = "https://opencode.ai/zen/go/v1"
    model = os.getenv("OPENCODE_GO_MODEL") or "deepseek-v4-flash"
    print(f"  model: {model}")

    # The model list is public (no key needed), so we can catch a wrong model ID early.
    status, _, body = call(f"{base}/models", {})
    if status == 200:
        ids = [m["id"] for m in body["data"]]
        if model not in ids:
            print(f"  '{model}' is not a valid model ID. Use one of these in OPENCODE_GO_MODEL:")
            print(f"  {', '.join(ids)}")
            return 404, {}, "unknown model ID"
    status, headers, body = call(
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {key}", "x-opencode-session": str(uuid.uuid4())},
        {"model": model, "messages": [{"role": "user", "content": "Reply with just: OK"}], "max_tokens": 300},
    )
    if status == 200:
        reply = body["choices"][0]["message"].get("content")
        print(f"  reply: {reply!r}" if reply else "  reply: (empty - model spent its tokens thinking)")
    return status, headers, body


def check_gemini(key):
    # Listing models is free and does not use any quota.
    return call("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key})


def check_groq(key):
    return call("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})


def check_openrouter(key):
    # This endpoint reports the key's own usage and limits.
    status, headers, body = call("https://openrouter.ai/api/v1/key", {"Authorization": f"Bearer {key}"})
    if status == 200:
        print(f"  key info: {body.get('data')}")
    return status, headers, body


def check_anthropic(key):
    return call("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"})


def check_openai(key):
    return call("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})


def check_ollama(host):
    status, headers, body = call(f"{host.rstrip('/')}/api/tags", {})
    if status == 200:
        names = [m["name"] for m in body.get("models", [])]
        print(f"  local models: {names or 'none downloaded yet'}")
    return status, headers, body


# name -> (environment variable, check function)
PROVIDERS = {
    "opencode": ("OPENCODE_API_KEY", check_opencode),
    "gemini": ("GOOGLE_API_KEY", check_gemini),
    "groq": ("GROQ_API_KEY", check_groq),
    "openrouter": ("OPENROUTER_API_KEY", check_openrouter),
    "anthropic": ("ANTHROPIC_API_KEY", check_anthropic),
    "openai": ("OPENAI_API_KEY", check_openai),
    "ollama": ("OLLAMA_HOST", check_ollama),
}


def main():
    load_dotenv()
    wanted = sys.argv[1:] or list(PROVIDERS)

    for name in wanted:
        if name not in PROVIDERS:
            print(f"Unknown provider '{name}'. Choose from: {', '.join(PROVIDERS)}")
            continue
        env_var, check = PROVIDERS[name]
        value = os.getenv(env_var, "").strip()

        print(f"\n[{name}]")
        if not value:
            print(f"  skipped - {env_var} is empty in .env")
            continue

        try:
            status, headers, body = check(value)
        except urllib.error.URLError as err:
            print(f"  could not connect: {err.reason}")
            continue

        print(f"  status: {status} - {STATUS_MEANING.get(status, 'see message below')}")
        if status != 200:
            print(f"  message: {body}")
        for k, v in limit_headers(headers).items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
