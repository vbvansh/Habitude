from pathlib import Path

from habitude.recorders.browser_use import trace_from_history

FIXTURES = Path(__file__).parent / "fixtures"
TASK = 'Enter "Jerald" into the text field and press Submit.'


def _element(tag, attrs, name=None):
    return {"node_name": tag, "attributes": attrs, "ax_name": name, "x_path": f"html/body/{tag.lower()}"}


def _item(url, actions, elements, results):
    return {
        "model_output": {"action": actions},
        "state": {"url": url, "title": "t", "interacted_element": elements},
        "result": results,
    }


def test_saved_browser_use_run_becomes_trace():
    trace = trace_from_history(FIXTURES / "browser_use_enter_text.json", task=TASK)

    assert [s.action for s in trace.steps] == ["type", "click"]
    typed, clicked = trace.steps
    assert typed.value == "Jerald"
    assert typed.target.role == "textbox" and typed.target.attrs["id"] == "tt"
    assert clicked.target.role == "button" and clicked.target.name == "Submit"
    assert trace.agent_success is True
    assert trace.stats.llm_calls == 2
    assert trace.start_url.endswith("/miniwob/enter-text.html")


def test_look_only_and_unexecuted_actions_are_skipped():
    history = {
        "history": [
            _item(
                "https://x.test",
                [{"find_text": {"text": "hi"}}, {"click": {"index": 1}}, {"click": {"index": 2}}],
                [None, _element("BUTTON", {}, "A"), _element("BUTTON", {}, "B")],
                [{"extracted_content": "found"}, {"error": "element gone"}],  # third action never ran
            )
        ]
    }
    trace = trace_from_history(history, task="t")

    assert len(trace.steps) == 1
    assert trace.steps[0].ok is False
    assert trace.steps[0].target.name == "A"


def test_declared_secrets_are_masked_everywhere():
    history = {
        "history": [
            _item(
                "https://x.test/login",
                [{"input": {"index": 1, "text": "<secret>password</secret>"}}],
                [_element("INPUT", {"type": "password", "value": "hunter2"})],
                [{"extracted_content": "Typed hunter2"}],
            )
        ]
    }
    trace = trace_from_history(history, task="log in", sensitive_data={"password": "hunter2"})

    assert "hunter2" not in trace.model_dump_json()
    assert trace.steps[0].value == "{{secret:password}}"
    assert trace.secrets == ["password"]


def test_undeclared_password_is_masked_automatically():
    history = {
        "history": [
            _item(
                "https://x.test/login",
                [{"input": {"index": 1, "text": "s3cret!"}}],
                [_element("INPUT", {"type": "password"})],
                [{"extracted_content": "Typed 's3cret!'"}],
            )
        ]
    }
    trace = trace_from_history(history, task="log in")

    assert "s3cret!" not in trace.model_dump_json()
    assert trace.steps[0].value == "{{secret:password}}"


def test_clicked_text_and_rich_text_editors_are_recognised():
    history = {
        "history": [
            _item(
                "https://mail.test",
                [{"click": {"index": 1}}, {"input": {"index": 2, "text": "Hello"}}],
                [_element("DIV", {"class": "x"}), _element("DIV", {"contenteditable": "true"})],
                [{"extracted_content": 'Clicked div "Compose"'}, {"extracted_content": "Typed 'Hello'"}],
            )
        ]
    }
    click, typed = trace_from_history(history, task="t").steps

    assert click.target.text == "Compose"
    assert click.target.describe() == 'div "Compose"'
    assert typed.target.role == "textbox"
