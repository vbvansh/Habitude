"""Builds the default LLM Habitude uses for recording and repair.

Any browser-use chat model works with Habitude; pass your own if you prefer.
This module only builds the default: OpenCode Go with deepseek-v4.1-flash.
"""

import os
import uuid
from dataclasses import dataclass

from browser_use.llm.base import BaseChatModel
from browser_use.llm.openai.chat import ChatOpenAI
from dotenv import load_dotenv
from openai import AsyncOpenAI

from habitude import __version__

OPENCODE_GO_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash"

# OpenCode Go asks clients to name themselves and send a stable session id,
# so it can route requests and reuse cached prompts.
SESSION_ID = str(uuid.uuid4())


@dataclass
class JsonModeChatOpenAI(ChatOpenAI):
    """ChatOpenAI that asks for plain JSON mode when the schema is in the prompt.

    Some providers reject strict JSON schemas, so the schema goes in the system
    prompt instead. Without any JSON mode, though, models sometimes answer in their
    own tool-call syntax (DeepSeek's "DSML"), which can't be parsed. Plain JSON
    mode (`{"type": "json_object"}`) rules that out.
    """

    def get_client(self) -> AsyncOpenAI:
        client = super().get_client()
        create = client.chat.completions.create

        async def create_with_json_mode(**kwargs):
            messages = kwargs.get("messages") or []
            schema_in_prompt = (
                messages and messages[0].get("role") == "system" and "<json_schema>" in str(messages[0].get("content"))
            )
            if schema_in_prompt and "response_format" not in kwargs:
                kwargs["response_format"] = {"type": "json_object"}
            return await create(**kwargs)

        client.chat.completions.create = create_with_json_mode
        return client


def default_llm(model: str | None = None) -> BaseChatModel:
    """Return the default chat model, configured from environment variables / .env."""
    load_dotenv()
    api_key = os.getenv("OPENCODE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENCODE_API_KEY is not set. Add it to your .env file, "
            "or pass your own browser-use chat model to Habitude."
        )

    return JsonModeChatOpenAI(
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
