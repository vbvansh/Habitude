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
