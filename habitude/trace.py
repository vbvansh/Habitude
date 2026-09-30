"""The trace format: a platform-neutral record of one agent run.

A trace stores facts only (what was done, to which element, with what value).
Decisions such as parameters or locators are made later by the compiler.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# Every action Habitude understands. Recorders translate their own action
# names into these, so the compiler and runtime never see agent-specific names.
Action = Literal[
    "navigate",  # value = URL
    "click",
    "type",  # value = text
    "select",  # value = option text
    "press",  # value = key or shortcut, e.g. "Enter", "Control+a"
    "scroll",  # value = "down" / "up", amount = pages
    "back",
    "wait",  # amount = seconds
    "switch_tab",  # value = tab id
    "close_tab",  # value = tab id
    "upload",  # value = file path
    "extract",  # value = what to read from the page
    "unsupported",  # an agent action we can't replay yet; kept for transparency
]


# Ids that frameworks generate automatically (React ":r5:", "mui-1234", UUIDs, long
# hex strings). They change between page loads, so they can't identify an element.
_GENERATED_ID = re.compile(r"^:r\w*:$|^«r\w*»$|\d{3,}|^[0-9a-f]{8}-[0-9a-f]{4}-|^[0-9a-f]{16,}$", re.IGNORECASE)


def looks_generated(element_id: str) -> bool:
    return bool(_GENERATED_ID.search(element_id))


class Bounds(BaseModel):
    x: float
    y: float
    width: float
    height: float


class Target(BaseModel):
    """Everything known about one element: several independent ways to find it again."""

    role: str | None = None  # what it is: "button", "textbox", "link", ...
    name: str | None = None  # its accessible name / label: "Submit"
    text: str | None = None  # its visible text, when different from the name
    tag: str | None = None  # web: "button", "input"; desktop: control class name
    attrs: dict[str, str] = Field(default_factory=dict)  # id, name, type, placeholder, ...
    xpath: str | None = None  # its position in the page structure
    bounds: Bounds | None = None  # where it was on screen when recorded

    def describe(self) -> str:
        """A short human description, e.g. 'button "Submit"'."""
        kind = self.role or self.tag or "element"
        label = self.name or self.text or self.attrs.get("placeholder") or self.attrs.get("aria-label")
        if label:
            return f'{kind} "{label}"'
        if self.attrs.get("id") and not looks_generated(self.attrs["id"]):
            return f"{kind} #{self.attrs['id']}"
        if self.attrs.get("name"):
            return f"{kind} [name={self.attrs['name']}]"
        return kind


class Step(BaseModel):
    index: int  # 1-based position in the trace
    action: Action
    target: Target | None = None
    value: str | None = None
    amount: float | None = None
    url: str | None = None  # page the step started on
    title: str | None = None
    ok: bool = True  # False if the action failed while recording
    note: str | None = None  # what the agent reported, or why a step is unsupported
    raw: dict | None = None  # the original agent action, for debugging


class Stats(BaseModel):
    """What the recording cost; used by the cost meter to show savings."""

    llm_calls: int = 0
    tokens: int = 0
    seconds: float = 0.0


class Trace(BaseModel):
    format_version: int = 1
    task: str
    surface: Literal["web", "desktop"] = "web"
    source: str  # which recorder produced it, e.g. "browser-use"
    start_url: str | None = None
    steps: list[Step]
    secrets: list[str] = Field(default_factory=list)  # names of masked secrets (never values)
    agent_success: bool | None = None  # what the agent claimed at the end
    final_result: str | None = None
    stats: Stats = Field(default_factory=Stats)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Trace:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
