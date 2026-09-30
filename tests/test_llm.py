import pytest

from habitude.llm import DEFAULT_MODEL, OPENCODE_GO_URL, default_llm


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "")
    with pytest.raises(RuntimeError, match="OPENCODE_API_KEY"):
        default_llm()


def test_builds_opencode_model(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.delenv("OPENCODE_GO_MODEL", raising=False)
    monkeypatch.setattr("habitude.llm.load_dotenv", lambda: None)

    llm = default_llm()

    assert llm.model == DEFAULT_MODEL
    assert str(llm.base_url) == OPENCODE_GO_URL
    assert llm.default_headers["x-opencode-session"]


def test_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    assert default_llm(model="kimi-k3").model == "kimi-k3"


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)


async def test_json_mode_is_requested_only_when_schema_is_in_prompt(monkeypatch):
    from types import SimpleNamespace

    from browser_use.llm.openai.chat import ChatOpenAI

    from habitude.llm import JsonModeChatOpenAI

    completions = _FakeCompletions()
    monkeypatch.setattr(ChatOpenAI, "get_client", lambda self: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    client = JsonModeChatOpenAI(model="m", api_key="k").get_client()

    await client.chat.completions.create(messages=[{"role": "system", "content": "x <json_schema>{}</json_schema>"}])
    await client.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in completions.calls[1]
