"""Keep secrets out of traces: every secret value becomes a {{secret:name}} placeholder."""

from __future__ import annotations

import re
from typing import Any

# browser-use shows secrets to the model as <secret>name</secret>.
_BROWSER_USE_TAG = re.compile(r"<secret>\s*([\w.-]+)\s*</secret>")


def placeholder(name: str) -> str:
    return "{{secret:" + name + "}}"


def flatten(sensitive_data: dict[str, Any] | None) -> dict[str, str]:
    """Turn browser-use's sensitive_data (optionally grouped by domain) into {name: value}."""
    flat: dict[str, str] = {}
    for key, value in (sensitive_data or {}).items():
        if isinstance(value, dict):  # {"https://*.example.com": {"password": "..."}}
            flat.update({k: str(v) for k, v in value.items()})
        else:
            flat[key] = str(value)
    return flat


class SecretMasker:
    def __init__(self, secrets: dict[str, str] | None = None):
        self.secrets: dict[str, str] = dict(secrets or {})

    @property
    def names(self) -> list[str]:
        return sorted(self.secrets)

    def add(self, value: str, preferred_name: str = "password") -> str:
        """Register a newly discovered secret value and return its placeholder name."""
        for name, known in self.secrets.items():
            if known == value:
                return name
        name, n = preferred_name, 2
        while name in self.secrets:
            name, n = f"{preferred_name}_{n}", n + 1
        self.secrets[name] = value
        return name

    def mask(self, text: str) -> str:
        text = _BROWSER_USE_TAG.sub(lambda m: placeholder(m.group(1)), text)
        # Longest values first, so a secret that contains another is replaced whole.
        for name, value in sorted(self.secrets.items(), key=lambda kv: -len(kv[1])):
            if value:
                text = text.replace(value, placeholder(name))
        return text

    def mask_all(self, obj: Any) -> Any:
        """Mask every string inside nested dicts/lists (e.g. a whole dumped trace)."""
        if isinstance(obj, str):
            return self.mask(obj)
        if isinstance(obj, dict):
            return {k: self.mask_all(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.mask_all(v) for v in obj]
        return obj
