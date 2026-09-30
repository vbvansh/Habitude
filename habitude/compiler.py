"""Compile a trace into a readable Python workflow file.

The output calls Habitude's runtime (`run.click(...)`, `run.type(...)`), and each
element is written as a `Target` with several fingerprints, so the runtime can
find it again, and repair it, when the page changes.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from jinja2 import Template
from pydantic import BaseModel

from habitude import __version__
from habitude.params import Param, detect_params, task_template
from habitude.secrets import placeholder
from habitude.trace import Step, Target, Trace, looks_generated

# Attributes that tend to stay the same when a site is redesigned. Classes,
# styles and random data-* attributes are left out: they change too often.
_STABLE_ATTRS = (
    "id", "name", "type", "placeholder", "aria-label", "title", "alt", "href", "for",
    "data-testid", "data-test", "data-qa", "data-cy",
)  # fmt: skip

_WIDTH = 100  # line length of the generated code

_FILE = Template('''\
"""{{ docstring }}

Compiled by Habitude {{ version }} from a {{ trace.source }} recording ({{ trace.recorded_at.date() }}).
The recording took {{ trace.stats.llm_calls }} LLM calls and {{ trace.stats.seconds }}s.

Edit freely. Each Target lists the fingerprints Habitude uses to find the
element again: role and name first, then attributes, then the xpath.
"""

from habitude import Run, Target

TASK = {{ lit(template) }}
START_URL = {{ lit(trace.start_url) if trace.start_url else "None" }}
{%- if trace.secrets %}
SECRETS = {{ trace.secrets | tojson }}  # read from HABITUDE_SECRET_<NAME> or passed to the run
{%- endif %}


async def workflow({{ signature }}) -> None:
{{ body | join("\\n\\n") }}
''')


class CompiledWorkflow(BaseModel):
    source: str
    params: list[Param]
    task_template: str


def compile_trace(trace: Trace) -> CompiledWorkflow:
    params = detect_params(trace)
    template = task_template(trace.task, params)
    by_step = {(i, p.field): p for p in params for i in p.steps}

    body = [_step_code(step, by_step) for step in trace.steps] or ["    pass"]
    args = ["run: Run"] + (["*"] + [f"{p.name}: str = {lit(p.example)}" for p in params] if params else [])
    signature = ", ".join(args)
    if len(f"async def workflow({signature}) -> None:") > _WIDTH:
        signature = "".join(f"\n    {a}," for a in args) + "\n"

    source = _FILE.render(
        docstring=template.replace('"""', "'''").replace("\\", "\\\\"),
        version=__version__,
        trace=trace,
        template=template,
        signature=signature,
        body=body,
        lit=lit,
    )
    ast.parse(source)  # a compiler bug must never write broken Python
    return CompiledWorkflow(source=source, params=params, task_template=template)


def compile_to_dir(trace: Trace, directory: str | Path) -> CompiledWorkflow:
    """Write trace.json and workflow.py into `directory`."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    compiled = compile_trace(trace)
    trace.save(directory / "trace.json")
    (directory / "workflow.py").write_text(compiled.source, encoding="utf-8")
    return compiled


def lit(value: str) -> str:
    """A Python string literal, e.g. 'Say "hi"' -> "Say \\"hi\\"". JSON strings are valid Python."""
    return json.dumps(value, ensure_ascii=False)


def _step_code(step: Step, by_step: dict[tuple[int, str], Param]) -> str:
    comment = f"    # {step.index}. {_describe(step)}"
    if not step.ok:
        return f"{comment}\n    # skipped: this step failed while recording ({_short(step.note)})"

    value_param = by_step.get((step.index, "value"))
    name_param = by_step.get((step.index, "name"))
    target = _target_code(step.target, name_param) if step.target else None
    value = value_param.name if value_param else _value_code(step.value)

    match step.action:
        case "navigate":
            call = _call("goto", [lit(step.value or "")])
        case "click":
            call = _call("click", [target])
        case "type":
            call = _call("type", [target, value])
        case "select":
            call = _call("select", [target, value])
        case "press":
            call = _call("press", [lit(step.value or "")])
        case "scroll":
            args = [lit(step.value or "down"), f"pages={step.amount or 1.0}"]
            call = _call("scroll", args + ([f"within={target}"] if target else []))
        case "back":
            call = _call("back", [])
        case "wait":
            call = _call("wait", [str(step.amount or 1)])
        case "switch_tab":
            call = _call("switch_tab", []) + "  # the newest tab"
        case "close_tab":
            call = _call("close_tab", [])
        case "upload":
            call = _call("upload", [target, value])
        case "extract":
            call = _call("extract", [lit(step.value or "")])
        case _:
            return f"{comment}\n    # not replayable yet: {_short(step.note)}"
    return f"{comment}\n{call}"


def _call(method: str, args: list[str]) -> str:
    """`await run.method(...)` on one line if it fits, otherwise one argument per line."""
    one_line = f"    await run.{method}({', '.join(args)})"
    if len(one_line) <= _WIDTH and "\n" not in one_line:
        return one_line
    inner = "".join(f"\n        {a}," for a in args)
    return f"    await run.{method}({inner}\n    )"


def _target_code(target: Target, name_param: Param | None) -> str:
    args: list[str] = []
    if target.role:
        args.append(f"role={lit(target.role)}")
    if name_param:
        args.append(f"name={name_param.name}")
    elif target.name:
        args.append(f"name={lit(target.name)}")
    if target.text and target.text != target.name:
        args.append(f"text={lit(target.text)}")
    if target.tag:
        args.append(f"tag={lit(target.tag)}")
    attrs = {
        k: target.attrs[k]
        for k in _STABLE_ATTRS
        if target.attrs.get(k) and not (k in ("id", "for") and looks_generated(target.attrs[k]))
    }
    if attrs:
        args.append("attrs={" + ", ".join(f"{lit(k)}: {lit(v)}" for k, v in attrs.items()) + "}")
    if target.xpath:
        args.append(f"xpath={lit(target.xpath)}")
    if not args and target.bounds:  # only a screen position is known
        b = target.bounds
        args.append(f'bounds={{"x": {b.x:g}, "y": {b.y:g}, "width": {b.width:g}, "height": {b.height:g}}}')

    one_line = f"Target({', '.join(args)})"
    if len(one_line) <= _WIDTH - 9:  # fits as an indented argument line
        return one_line
    inner = "".join(f"\n            {a}," for a in args)
    return f"Target({inner}\n        )"


def _value_code(value: str | None) -> str:
    if value is None:
        return '""'
    for_secret = value.removeprefix("{{secret:").removesuffix("}}")
    if value == placeholder(for_secret):
        return f"run.secret({lit(for_secret)})"
    return lit(value)


def _describe(step: Step) -> str:
    what = step.target.describe() if step.target else ""
    match step.action:
        case "navigate":
            return f"open {step.value}"
        case "type":
            return f"type into {what}"
        case "select":
            return f"choose an option in {what}"
        case "press":
            return f"press {step.value}"
        case "scroll":
            return f"scroll {step.value}"
        case _:
            return f"{step.action.replace('_', ' ')} {what}".strip()


def _short(text: str | None, limit: int = 70) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
