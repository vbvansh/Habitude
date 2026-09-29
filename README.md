# Habitude

**A JIT compiler for computer-use agents.**
Run a task once with an AI agent. After that, it runs as verified, self-repairing code.

> **Status: in active development.** v0.1 (browser) is being built now; see [PLAN.md](PLAN.md).
> Everything below describes the target design. Items marked *v0.2* or *later* do not exist yet.

---

## The problem

Developers who use AI agents to operate computers (websites first, desktop apps next)
for repeated tasks pay for the agent to re-think the same steps on every run:

- **Slow.** Minutes for a task a script does in seconds.
- **Expensive.** Every step of every run costs LLM tokens.
- **Unpredictable.** The same task takes a different path each time.
- **Unverified.** When the agent says "done", there is no proof it actually succeeded.

Turning agent runs into scripts saves the tokens but creates new problems: scripts break
when the app or site changes, and existing replay tools either fail silently or need
someone to fix them by hand.

## The four promises

Habitude is built, and benchmarked, around four measurable promises:

| # | Promise | Measured as |
|---|---|---|
| 1 | **Cheap:** repeat runs make no LLM calls | LLM calls and cost per run |
| 2 | **Fast:** seconds, not minutes | Time per run |
| 3 | **Self-repairing:** when the site or app changes, only the broken step is fixed, and you see exactly what changed | Repair success rate and LLM calls per repair |
| 4 | **Honest:** every run ends with proof of success or a clear failure, never a silent wrong result | Wrong results caught vs. missed |

## How it works

JavaScript engines make code fast with a JIT (just-in-time) compiler: run slowly at first
while watching, compile what repeats into fast code guarded by checks, and fall back to
the slow path when a check fails. Habitude does the same for agents.

```
 first run                 compile                    every later run
┌───────────┐   trace   ┌───────────────┐        ┌──────────────────────────┐
│ AI agent  │ ────────► │ code + checks │ ─────► │ run code (no LLM)        │
│ does task │           │ + parameters  │        │ checks pass → receipt ✅ │
└───────────┘           └───────────────┘        │ step breaks → ladder ↓   │
                                                 └──────────────────────────┘
 fallback ladder, cheapest first:
   1. stored locators          → free
   2. fuzzy re-find            → free, no LLM
   3. LLM repairs that step    → 1 call, saved as a reviewable code change
   4. full agent               → last resort
```

1. **Record.** An AI agent does the task once. Habitude logs every action, the element
   it touched (with several fingerprints for finding it again), and the page before and after.
2. **Compile.** The recording becomes readable code. Values that change between runs
   (dates, IDs, file names) become **parameters**. Passwords become placeholders and are never saved.
3. **Replay.** Later runs execute the code directly. No LLM.
4. **Check.** After key steps, generated checks confirm the step really worked. Every run
   produces a **receipt**.
5. **Repair.** If a step breaks, Habitude climbs the fallback ladder. An LLM fix is saved
   as a code change with its reason, e.g. *"Button text changed from 'Export' to 'Download CSV'."*

## Architecture

One shared core, plus one small **driver** per platform:

```
┌──────────────────────── shared core ────────────────────────┐
│ trace format · compiler · fallback ladder · LLM repair      │
│ checks & receipts · repairs as code changes · secret masking │
│ cost meter · MCP export · HabitudeBench                      │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
      Web driver (Playwright)        Windows driver (UI Automation)
      v0.1                           v0.2
```

## Features

| Feature | Why it matters | Version |
|---|---|---|
| One-line wrapper around a browser-use agent | Try it without rewriting your project | v0.1 |
| Readable compiled code | Open it, edit it, commit it to git | v0.1 |
| Run receipts (proof of success) | Catch "the agent said done, but it wasn't" | v0.1 |
| Repairs as reviewable code changes | Trust what the bot changed | v0.1 |
| Secret masking | Recordings are safe to commit | v0.1 |
| Cost meter | See LLM calls, time, and money saved per run | v0.1 |
| Risky-action guard | *Pay*, *Delete*, *Send* only run after their checks pass | v0.1 |
| MCP export: a recorded workflow becomes a tool any AI assistant can call | Show it once, get a tool | v0.1 (stretch) |
| Windows desktop apps, recorded from a human or an agent | Automate software with no API | v0.2 |
| Skills shared across tasks on the same site or app | New tasks get cheaper too | later |
| More agent adapters (Playwright MCP, Stagehand, Claude computer use) | Use the agent you already have | later |

## Not in scope

- A new AI agent. Habitude makes existing agents cheaper and more reliable.
- A QA / end-to-end testing tool.
- Mobile apps.
- Getting around CAPTCHAs or anti-bot systems.
- A paid cloud service. Habitude runs on your machine.

## HabitudeBench

Most agent benchmarks ask *"can the agent do this task once?"* HabitudeBench asks
*"how cheaply and reliably can it do the task the 2nd to 100th time, including after the
site changes?"* It measures all four promises on:

- **[MiniWoB++](https://github.com/Farama-Foundation/miniwob-plusplus):** 100+ small web
  tasks with randomized values, for testing parameters.
- **[REAL](https://github.com/agi-inc/REAL):** deterministic replicas of real web apps,
  for realistic multi-page workflows.
- **Change injection:** renamed buttons, changed CSS classes, moved elements, surprise popups.

Results will be published here with v0.1.

## Planned usage

> Target API. It may change before v0.1.

```python
from browser_use import Agent
from habitude import Habitude

hb = Habitude()

# First run: the agent does the task; Habitude records and compiles it.
agent = Agent(task="Download the invoice for order 1042", llm=llm)
result = await hb.run(agent, workflow="download_invoice")

# Later runs: compiled code, new values, no LLM.
result = await hb.replay("download_invoice", params={"order_id": "1057"})
print(result.receipt)     # which checks passed
print(result.llm_calls)   # 0
```

```bash
habitude replay download_invoice --param order_id=1057
habitude repairs download_invoice      # review what the LLM changed
habitude bench                         # run HabitudeBench
```

## Roadmap

- **v0.1: browser** (target: Oct 4, 2026). Record, compile, replay, checks, repair,
  secret masking, cost meter, HabitudeBench, PyPI release.
- **v0.2: Windows desktop.** UI Automation driver, human recording, desktop checks and benchmark.
- **Later:** cross-task skills, more agent adapters, macOS/Linux desktop, API fast-path.

The day-by-day plan lives in [PLAN.md](PLAN.md).

## Development setup

Requires **Python 3.11+** (developed on 3.12).

```bash
git clone https://github.com/vbvansh/Habitude.git
cd Habitude

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
playwright install chromium

copy .env.example .env          # Windows  (cp on macOS / Linux), then add an LLM key
python scripts/check_keys.py    # check which keys work
```

## Built with

- [browser-use](https://github.com/browser-use/browser-use): the AI agent we record
- [Playwright](https://playwright.dev/python/): the browser engine used for replay
- Any LLM for recording and repair: OpenCode Go, Google Gemini (free tier), Groq,
  OpenRouter, local models through [Ollama](https://ollama.com/), Anthropic Claude, or OpenAI
- [Pydantic](https://docs.pydantic.dev/), [Typer](https://typer.tiangolo.com/), [Rich](https://rich.readthedocs.io/)

## License

MIT (license file added with v0.1).
