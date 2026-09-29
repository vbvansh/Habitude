"""Builds the default LLM Habitude uses for recording and repair.

Any browser-use chat model works with Habitude; pass your own if you prefer.
This module only builds the default: OpenCode Go with deepseek-v4.1-flash.
"""

import os
import uuid

from browser_use.llm.base import BaseChatModel
from browser_use.llm.openai.chat import ChatOpenAI
from dotenv import load_dotenv

from habitude import __version__

OPENCODE_GO_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash"

# OpenCode Go asks clients to name themselves and send a stable session id,
# so it can route requests and reuse cached prompts.
SESSION_ID = str(uuid.uuid4())


def default_llm(model: str | None = None) -> BaseChatModel:
    """Return the default chat model, configured from environment variables / .env."""
    load_dotenv()
    api_key = os.getenv("OPENCODE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENCODE_API_KEY is not set. Add it to your .env file, "
            "or pass your own browser-use chat model to Habitude."
        )

    return ChatOpenAI(
        model=model or os.getenv("OPENCODE_GO_MODEL") or DEFAULT_MODEL,
        base_url=OPENCODE_GO_URL,
        api_key=api_key,
        # OpenCode Go's deepseek route rejects some JSON schemas sent as
        # `response_format` (HTTP 400) and returns runs of blank lines for others.
        # Describing the schema in the system prompt instead works reliably.
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
        default_headers={
            "User-Agent": f"habitude/{__version__}",
            "x-opencode-session": SESSION_ID,
        },
    )
