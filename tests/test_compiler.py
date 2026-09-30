import ast
from pathlib import Path

from habitude.compiler import compile_to_dir, compile_trace
from habitude.recorders.browser_use import trace_from_history
from habitude.trace import Step, Target, Trace

FIXTURES = Path(__file__).parent / "fixtures"


def _workflow_args(source: str) -> dict[str, str]:
    """Keyword-only parameter names of `workflow()` and their default values."""
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef))
    return {a.arg: ast.literal_eval(d) for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults)}


def test_recorded_run_compiles_to_parameterised_workflow():
    trace = trace_from_history(
        FIXTURES / "browser_use_enter_text.json", task='Enter "Jerald" into the text field and press Submit.'
    )
    compiled = compile_trace(trace)

    assert _workflow_args(compiled.source) == {"text": "Jerald"}
    assert compiled.task_template == 'Enter "{text}" into the text field and press Submit.'
    assert "await run.type(" in compiled.source and "        text,\n" in compiled.source
    assert 'name="Submit"' in compiled.source


def test_secrets_failed_and_unsupported_steps():
    trace = Trace(
        task="Log in",
        source="test",
        secrets=["password"],
        steps=[
            Step(index=1, action="type", value="{{secret:password}}", target=Target(role="textbox")),
            Step(index=2, action="click", target=Target(role="button", name="Go"), ok=False, note="timeout"),
            Step(index=3, action="unsupported", note="browser-use action 'evaluate'"),
        ],
    )
    source = compile_trace(trace).source

    assert 'run.secret("password")' in source
    assert "# skipped: this step failed while recording (timeout)" in source
    assert "# not replayable yet: browser-use action 'evaluate'" in source
    assert 'SECRETS = ["password"]' in source


def test_compile_to_dir_writes_trace_and_workflow(tmp_path):
    trace = Trace(task="Open it", source="test", steps=[Step(index=1, action="navigate", value="https://x.test")])
    compile_to_dir(trace, tmp_path / "open-it")

    assert Trace.load(tmp_path / "open-it" / "trace.json") == trace
    assert 'await run.goto("https://x.test")' in (tmp_path / "open-it" / "workflow.py").read_text()
