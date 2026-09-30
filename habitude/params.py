"""Find the values in a trace that should change between runs (parameters).

Rules:
1. A typed or selected value that appears in the task text is a parameter.
2. A clicked element's label that matches a "quoted" phrase in the task is a parameter.
Everything else (e.g. the "Submit" button in "press Submit") stays fixed.
"""

from __future__ import annotations

import keyword
import re
from typing import Literal

from pydantic import BaseModel

from habitude.trace import Target, Trace

_QUOTED = re.compile(r'"([^"]+)"|“([^”]+)”')
_ROLE_NAMES = {"textbox": "text", "searchbox": "query", "combobox": "option", "spinbutton": "number"}
_RESERVED = {"run", "target", "self"}


class Param(BaseModel):
    name: str
    example: str  # the value used while recording; becomes the default
    field: Literal["value", "name"]  # typed/selected value, or the clicked element's label
    steps: list[int]  # which steps use it


def quoted_phrases(task: str) -> list[str]:
    return [a or b for a, b in _QUOTED.findall(task)]


def detect_params(trace: Trace) -> list[Param]:
    task_lower = trace.task.lower()
    quoted = {q.strip().lower() for q in quoted_phrases(trace.task)}
    params: list[Param] = []

    def add(value: str, field: str, step_index: int, target: Target | None, action: str) -> None:
        for p in params:
            if p.example == value and p.field == field:
                p.steps.append(step_index)
                return
        name = _unique(_suggest_name(target, field, action), {p.name for p in params})
        params.append(Param(name=name, example=value, field=field, steps=[step_index]))

    for step in trace.steps:
        if not step.ok:
            continue
        value = step.value or ""
        is_input = step.action in ("type", "select") and "{{secret:" not in value
        if is_input and len(value) >= 2 and value.lower() in task_lower:
            add(value, "value", step.index, step.target, step.action)
        if step.action in ("click", "select") and step.target:
            label = (step.target.name or step.target.text or "").strip()
            if label and label.lower() in quoted:
                add(label, "name", step.index, step.target, step.action)
    return params


def task_template(task: str, params: list[Param]) -> str:
    """The task with parameter values replaced by {names}, e.g. 'Enter "{text}"...'."""
    template = task.replace("{", "{{").replace("}", "}}")
    for p in sorted(params, key=lambda p: -len(p.example)):
        # (?<!\w) / (?!\w): whole words only, so "Ok" doesn't match inside "book".
        pattern = r"(?<!\w)" + re.escape(p.example) + r"(?!\w)"
        template = re.sub(pattern, "{" + p.name + "}", template, flags=re.IGNORECASE)
    return template


def _suggest_name(target: Target | None, field: str, action: str) -> str:
    if field == "name":  # the label of something clicked: name it after what it is
        return _identifier((target.role or target.tag) if target else None) or "label"
    if target:
        for candidate in (
            target.attrs.get("name"),
            target.attrs.get("aria-label"),
            target.attrs.get("placeholder"),
            target.name,
            target.attrs.get("id"),
        ):
            ident = _identifier(candidate)
            if ident and len(ident) >= 3:
                return ident
        if target.role in _ROLE_NAMES:
            return _ROLE_NAMES[target.role]
    return "option" if action == "select" else "text"


def _identifier(text: str | None) -> str | None:
    """'E-mail address' -> 'e_mail_address'."""
    if not text:
        return None
    ident = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()[:40].strip("_")
    if not ident:
        return None
    if ident[0].isdigit():
        ident = "p_" + ident
    return ident


def _unique(name: str, taken: set[str]) -> str:
    if keyword.iskeyword(name) or name in _RESERVED:
        name += "_value"
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name}_{n}", n + 1
    return candidate
