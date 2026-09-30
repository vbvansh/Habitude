"""Recorder for browser-use agents: turns an agent's history into a Habitude trace."""

from __future__ import annotations

import json
import re
import time
from itertools import zip_longest
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from habitude.secrets import SecretMasker, flatten
from habitude.trace import Bounds, Stats, Step, Target, Trace

# browser-use actions that only *look* at the page or its own notes. Replaying
# them would change nothing, so they're left out of the trace.
_LOOK_ONLY = {"dropdown_options", "find_text", "search_page", "find_elements", "screenshot", "read_file"}

# browser-use reports clicks as `Clicked div "Compose"` or `Clicked div role=menuitem "Sent" ...`.
# The quoted part is the element's visible text, which the element data itself doesn't include.
_CLICKED_TEXT = re.compile(r'^Clicked \S+[^"\n]*"([^"\n]+)"')

_SEARCH_URLS = {
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "google": "https://www.google.com/search?q={}",
    "bing": "https://www.bing.com/search?q={}",
}

_INPUT_ROLES = {
    "checkbox": "checkbox",
    "radio": "radio",
    "submit": "button",
    "button": "button",
    "reset": "button",
    "image": "button",
    "range": "slider",
    "number": "spinbutton",
    "search": "searchbox",
}


async def record(agent, *, max_steps: int = 50) -> Trace:
    """Run a browser-use agent and return its trace."""
    started = time.time()
    history = await agent.run(max_steps=max_steps)
    trace = trace_from_history(history, task=agent.task, sensitive_data=agent.sensitive_data)
    trace.stats.seconds = round(time.time() - started, 2)
    return trace


def trace_from_history(
    history: Any, task: str, *, sensitive_data: dict | None = None, tokens: int | None = None
) -> Trace:
    """Build a trace from browser-use history: an AgentHistoryList, its dict, or a saved JSON file."""
    if isinstance(history, (str, Path)):
        data = json.loads(Path(history).read_text(encoding="utf-8"))
    elif isinstance(history, dict):
        data = history
    else:  # a live AgentHistoryList
        data = json.loads(json.dumps(history.model_dump(), default=str))
        usage = getattr(history, "usage", None)
        if tokens is None and usage is not None:
            tokens = usage.total_tokens

    items = data.get("history", [])
    masker = SecretMasker(flatten(sensitive_data))
    steps: list[Step] = []
    agent_success = final_result = None

    for item in items:
        state = item.get("state") or {}
        actions = (item.get("model_output") or {}).get("action") or []
        elements = state.get("interacted_element") or []
        results = item.get("result") or []

        for action, element, result in zip_longest(actions, elements, results):
            if not action:
                continue
            name, params = next(iter(action.items()))
            params = params or {}

            if name == "done":
                agent_success = params.get("success")
                final_result = params.get("text")
                continue
            if name in _LOOK_ONLY:
                continue
            if result is None:  # never ran: an earlier action in the same step failed
                continue

            step = _to_step(name, params, element)
            step.index = len(steps) + 1
            step.url = state.get("url")
            step.title = state.get("title")
            step.ok = not result.get("error")
            step.note = result.get("error") or result.get("extracted_content") or step.note
            step.raw = action
            if step.action == "click" and step.target and step.ok:
                clicked = _CLICKED_TEXT.match(step.note or "")
                if clicked and clicked.group(1) != step.target.name:
                    step.target.text = clicked.group(1)

            # A value typed into a password field is a secret, even if nobody said so.
            is_password = step.action == "type" and step.target and _is_password(step.target)
            if is_password and step.value and "<secret>" not in step.value:
                masker.add(step.value)
            steps.append(step)

    start_url = (items[0].get("state") or {}).get("url") if items else None
    trace = Trace(
        task=task,
        source="browser-use",
        start_url=None if not start_url or start_url == "about:blank" else start_url,
        steps=steps,
        agent_success=agent_success,
        final_result=final_result,
        stats=Stats(llm_calls=sum(1 for i in items if i.get("model_output")), tokens=tokens or 0),
    )
    if items:
        first, last = items[0].get("metadata") or {}, items[-1].get("metadata") or {}
        if first.get("step_start_time") and last.get("step_end_time"):
            trace.stats.seconds = round(last["step_end_time"] - first["step_start_time"], 2)

    # Mask last, over everything, so no secret can slip through any field.
    masked = Trace.model_validate(masker.mask_all(trace.model_dump(mode="json")))
    masked.secrets = masker.names
    return masked


def _to_step(name: str, params: dict, element: dict | None) -> Step:
    target = _to_target(element)
    match name:
        case "navigate":
            return Step(index=0, action="navigate", value=params.get("url"))
        case "search":
            template = _SEARCH_URLS.get(params.get("engine") or "duckduckgo", _SEARCH_URLS["duckduckgo"])
            return Step(index=0, action="navigate", value=template.format(quote_plus(params.get("query", ""))))
        case "go_back":
            return Step(index=0, action="back")
        case "wait":
            return Step(index=0, action="wait", amount=params.get("seconds", 3))
        case "click":
            if target is None and params.get("coordinate_x") is not None:
                x, y = params["coordinate_x"], params["coordinate_y"]
                target = Target(bounds=Bounds(x=x, y=y, width=0, height=0))
            return Step(index=0, action="click", target=target)
        case "input":
            return Step(index=0, action="type", target=target, value=params.get("text", ""))
        case "select_dropdown":
            return Step(index=0, action="select", target=target, value=params.get("text"))
        case "send_keys":
            return Step(index=0, action="press", value=params.get("keys"))
        case "scroll":
            return Step(
                index=0,
                action="scroll",
                target=target if params.get("index") else None,
                value="down" if params.get("down", True) else "up",
                amount=params.get("pages", 1.0),
            )
        case "upload_file":
            return Step(index=0, action="upload", target=target, value=params.get("path"))
        case "switch":
            return Step(index=0, action="switch_tab", value=params.get("tab_id"))
        case "close":
            return Step(index=0, action="close_tab", value=params.get("tab_id"))
        case "extract":
            return Step(index=0, action="extract", value=params.get("query"))
        case _:
            return Step(index=0, action="unsupported", target=target, note=f"browser-use action '{name}'")


def _to_target(element: dict | None) -> Target | None:
    if not element:
        return None
    tag = (element.get("node_name") or "").lower() or None
    attrs = {k: str(v) for k, v in (element.get("attributes") or {}).items() if k != "style"}
    bounds = element.get("bounds")
    return Target(
        role=_role(tag, attrs),
        name=(element.get("ax_name") or "").strip() or None,
        tag=tag,
        attrs=attrs,
        xpath=element.get("x_path"),
        bounds=Bounds(**{k: bounds[k] for k in ("x", "y", "width", "height")}) if bounds else None,
    )


def _role(tag: str | None, attrs: dict[str, str]) -> str | None:
    """The element's role, as a screen reader would name it."""
    if attrs.get("role"):
        return attrs["role"]
    if attrs.get("contenteditable", "").lower() in ("", "true", "plaintext-only") and "contenteditable" in attrs:
        return "textbox"  # a rich-text editor, e.g. an email body
    match tag:
        case "button":
            return "button"
        case "a":
            return "link" if "href" in attrs else None
        case "select":
            return "combobox"
        case "textarea":
            return "textbox"
        case "input":
            return _INPUT_ROLES.get(attrs.get("type", "text").lower(), "textbox")
        case "option":
            return "option"
        case "img":
            return "img"
    return None


def _is_password(target: Target) -> bool:
    return target.attrs.get("type", "").lower() == "password"
