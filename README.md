# Habitude

**Teach your AI agent a habit. Run it once with the LLM, then replay it without one.**

Habitude watches an AI browser agent do a task once, compiles what it did into a
plain, readable Playwright script, and replays that script on later runs with
**no LLM calls**. The LLM only comes back for the single step that breaks, and
when it fixes that step, the fix is saved as a reviewable change to the script.

> **Status: early development.** The design is set and the library is being built
> in the open. Items marked *planned* do not exist yet.

---

## The problem

AI browser agents (browser-use, Claude computer use, Stagehand, and others) treat
every run as the first time they have seen the website. For each click they look at
the page, think, act, and look again. That makes repeated tasks:

- **Slow.** A task that takes a script 5 seconds can take the agent minutes.
- **Expensive.** Every step costs LLM tokens, on every run.
- **Unpredictable.** The same task can be done differently each time.

Most business automation repeats the same few tasks: filling the same form,
downloading the same report, checking the same dashboard. Once an agent has worked
out the steps, it shouldn't need to think again.

## How Habitude works

```
  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
  │  RECORD  │ ──► │ COMPILE  │ ──► │  REPLAY  │ ──► │   HEAL   │
  │ agent    │     │ trace →  │     │ no LLM,  │     │ LLM for  │
  │ runs once│     │ script   │     │ fast     │     │ 1 step   │
  └──────────┘     └──────────┘     └──────────┘     └────┬─────┘
                                          ▲               │
                                          └── fix saved ──┘
```

1. **Record.** The agent does the task normally. Habitude logs every action: the page,
   the element, what was typed, and a snapshot of the page around it.
2. **Compile.** The log becomes a clean Playwright script. Values that change between
   runs (dates, file names, search terms) become **parameters**.
3. **Replay.** Later runs execute the script directly. No LLM is involved.
4. **Verify.** After important steps, Habitude checks that the step really worked, not
   just that it didn't crash.
5. **Heal.** If a step fails, the LLM is called for that step only. The fix is saved
   as a diff you can review, so the next run works without the LLM.

## What makes it different

Record-and-replay for agents already exists ([workflow-use](https://github.com/browser-use/workflow-use),
[Stagehand caching](https://docs.stagehand.dev/v3/best-practices/deterministic-agent),
[muscle-mem](https://github.com/pig-dot-dev/muscle-mem)). Habitude focuses on the parts
that are still unsolved:

| Focus | What it means |
|---|---|
| **Catching silent failures** | Checks are generated from the recording, such as "a file was downloaded" or "the confirmation text appeared", so a step that ran but did the wrong thing is caught. |
| **Real code output** | The output is a readable Playwright script you can open, edit, and commit to git, not a hidden cache. |
| **Heals as diffs** | Every self-heal produces a reviewable change with its reason: *"Button text changed from 'Export' to 'Download CSV'."* |
| **Robust element finding** | Each element is stored with several fingerprints (role, label, text, position, CSS), which are tried in order before the LLM is asked. |
| **Branches, not one straight path** | Optional steps (cookie banners, popups, empty results) are handled as conditions instead of breaking the run. |
| **Safety for risky actions** | Steps like *Pay*, *Delete*, or *Send* are flagged and only run after their target is verified. |
| **Memory** | Habitude remembers past runs, heals, and site quirks, so fixes learned on one workflow help others on the same site. |
| **Framework-agnostic** | Adapters record from different agents into one common trace format. |
| **Robustness benchmark** | A public benchmark that deliberately changes websites and measures how often each tool recovers. |

## Planned usage

> This is the target developer experience. The API may change while the project is
> being built.

```python
from habitude import Habitude

hb = Habitude()

# First run: the AI agent does the task and Habitude records it.
workflow = await hb.record(
    task="Log in to the demo shop and download the invoice for order 1042",
    start_url="http://localhost:8000",
)
workflow.save("workflows/download_invoice")

# Later runs: replay the compiled script with new parameters, with no LLM.
result = await hb.replay("workflows/download_invoice", params={"order_id": "1057"})
print(result.success, result.duration_s, result.llm_calls)   # True 3.8 0
```

```bash
habitude record "Download the invoice for order 1042" --url http://localhost:8000
habitude replay workflows/download_invoice --param order_id=1057
habitude heals workflows/download_invoice     # review what the LLM changed
```

## Roadmap

- [ ] **Phase 1: Record.** Capture browser-use runs in a common trace format.
- [ ] **Phase 2: Compile.** Turn a trace into a Playwright script, with parameter detection.
- [ ] **Phase 3: Replay.** Run scripts with a chain of element-finding strategies.
- [ ] **Phase 4: Heal.** Fix one failing step with an LLM, saved as a reviewable diff.
- [ ] **Phase 5: Verify.** Auto-generate post-step checks to catch silent failures.
- [ ] **Phase 6: Hard parts.** Branching steps, risky-action guards, multi-recording parameter detection.
- [ ] **Phase 7: Memory.** Store runs, heals, and per-site knowledge.
- [ ] **Phase 8: Benchmark.** Demo sites plus deliberate page changes, compared with other tools.
- [ ] **Phase 9: Library release.** Publish to PyPI (`pip install habitude`).
- [ ] **Phase 10: Web app.** Hosted dashboard to browse workflows, runs, heals, and benchmark results.

## Development setup

Requires **Python 3.11+** (developed on 3.12).

```bash
git clone https://github.com/<your-username>/habitude.git
cd habitude

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# Install dependencies and the browser
pip install -r requirements.txt
playwright install chromium

# Add your API key
copy .env.example .env          # Windows  (cp on macOS / Linux)
```

## Built with

- [browser-use](https://github.com/browser-use/browser-use): the AI agent we record
- [Playwright](https://playwright.dev/python/): the browser engine used for replay
- [Anthropic Claude](https://docs.anthropic.com/): the LLM used for recording and self-healing
- [Pydantic](https://docs.pydantic.dev/), [Typer](https://typer.tiangolo.com/), [Rich](https://rich.readthedocs.io/)

## License

MIT (to be added).
