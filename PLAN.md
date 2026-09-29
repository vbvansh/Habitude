# Habitude: Build Plan

This file is our map. We work top to bottom, tick boxes as we go, and don't start
anything that isn't on it.

## North star (locked 2026-09-30)

> Developers who use AI agents to operate computers (websites first, desktop apps next)
> for repeated tasks pay for the agent to re-think the same steps on every run. It's slow,
> costs tokens every time, takes a different path each run, and when it says "done" there's
> no proof it succeeded. Turning runs into scripts saves money but creates new problems:
> scripts break when the app or site changes, and existing replay tools either fail silently
> or need manual fixing.

**Pitch:** A JIT compiler for computer-use agents.
**Four promises:** Cheap · Fast · Self-repairing · Honest (see README).
**Not in scope:** a new agent · QA testing tool · mobile · CAPTCHA/anti-bot workarounds · paid cloud.

## Rules

1. **The problem is locked.** New ideas go to the **Parking lot** at the bottom, never into
   the current day. We look at the parking lot only after v0.2 ships.
2. **One item at a time**, top to bottom, from the current day's list.
3. **Every item follows the same loop:**
   1. Explain the goal in plain words.
   2. Build the smallest version that works.
   3. Run it and see it work.
   4. Explain what was built, simply.
   5. Answer questions.
   6. Commit with a one-line message.
   7. Tick the box here.
4. **Behind schedule? Cut, don't extend.** Use the cut order below. Never push the deadline
   by adding scope.
5. **Decisions are final** once they're in the Decisions log, unless a test proves one wrong.
6. **End of every day:** update this file, commit, `git push`.

## Definition of done

**v0.1 is done when:**
- [ ] `pip install habitude` works in a fresh virtual environment.
- [ ] A developer can record → replay → see a receipt in about 10 lines of code.
- [ ] A broken step is repaired and the change is shown as a readable diff.
- [ ] HabitudeBench reports real numbers for all four promises (good or bad, honestly).
- [ ] The README quickstart works when copied and pasted.

**v0.2 is done when:**
- [ ] A task in a Windows app (e.g. Notepad or File Explorer) can be recorded from a human,
      replayed with no LLM, and repaired after a UI change.
- [ ] The desktop part of HabitudeBench reports numbers for all four promises.

**Cut order if we fall behind** (first cut first): MCP export → landing-page polish →
risky-action guard → REAL tasks (keep MiniWoB++). **Never cut** checks/receipts, repair,
or the benchmark; the problem statement depends on them.

---

## v0.1: Browser (Wed Sep 30 → Sun Oct 4, 2026)

### Day 1 · Wed Sep 30: Foundations
- [x] Lock the problem; rewrite README; write this plan
- [x] Package skeleton: `habitude/` folder, `pyproject.toml`, editable install
- [x] `habitude/llm.py`: one place that builds the LLM (OpenCode Go, deepseek-v4.1-flash)
- [x] Check that MiniWoB++ and REAL install alongside browser-use without version clashes
- [x] Prove Playwright and browser-use can control the **same** browser
- [x] Watch browser-use do one MiniWoB++ task; save its raw history to study

### Day 2 · Thu Oct 1: Record + Compile
- [ ] Trace format (platform-neutral): Workflow → Steps → Target fingerprints
- [ ] Recorder: browser-use adapter → trace file (JSON)
- [ ] Secret masking: passwords become placeholders
- [ ] Compiler: trace → readable Python workflow file with parameters
- [ ] Parameter detection (from the task text and typed values)
- [ ] Tests on saved traces (no LLM needed)

### Day 3 · Fri Oct 2: Replay + Repair + Checks
- [ ] Driver interface + web driver (Playwright)
- [ ] Fallback ladder: stored locators → fuzzy re-find → LLM repairs one step → full agent
- [ ] Repairs saved as a diff with the reason
- [ ] Generated checks after key steps + run receipt
- [ ] Risky-action guard (basic)
- [ ] Cost meter

### Day 4 · Sat Oct 3: Benchmark + Tools
- [ ] HabitudeBench runner: MiniWoB++ subset + REAL subset
- [ ] Change injector: rename text, change CSS classes, move elements, add a popup
- [ ] Run: plain browser-use every time vs. Habitude; save results
- [ ] Command-line tool: `habitude record / replay / repairs / bench`
- [ ] MCP export *(stretch)*

### Day 5 · Sun Oct 4: Ship
- [ ] Tests pass; `ruff` clean
- [ ] README: real numbers, demo GIF, quickstart
- [ ] LICENSE (MIT), CHANGELOG
- [ ] Landing page (GitHub Pages)
- [ ] Publish v0.1.0 to PyPI; GitHub release
- [ ] Draft launch posts

### Launch · Tue Oct 6
- [ ] Show HN, r/LocalLLaMA, r/Python, X, LinkedIn (US morning)

---

## v0.2: Windows desktop (Wed Oct 7 → target Sun Oct 11, confirmed at the Day 6 checkpoint)

### Day 6 · Wed Oct 7: Driver spike + checkpoint
- [ ] Read the UI tree of Notepad, File Explorer and Calculator with `uiautomation` / `pywinauto`
- [ ] Choose the library; **checkpoint:** confirm or move the v0.2 date

### Day 7 · Thu Oct 8: Human recorder
- [ ] Capture mouse/keyboard + the element under the cursor → same trace format

### Day 8 · Fri Oct 9: Desktop replay + checks
- [ ] Windows driver plugged into the fallback ladder
- [ ] Desktop checks: window title, control value, file contents

### Day 9 · Sat Oct 10: Desktop benchmark
- [ ] Tasks on Notepad, Paint, File Explorer, LibreOffice
- [ ] Changes: window resize, dark mode, display scaling, moved toolbar

### Day 10 · Sun Oct 11: Ship v0.2
- [ ] Docs, v0.2.0 release, launch post #2

---

## Decisions log

| Date | Decision |
|---|---|
| 2026-09-28 | Name: **Habitude** |
| 2026-09-29 | Development LLM: OpenCode Go **deepseek-v4.1-flash** for the whole project |
| 2026-09-30 | Benchmarks: **MiniWoB++** + **REAL** + our change injection. OSWorld rejected (desktop VM, too heavy); WebArena deferred |
| 2026-09-30 | Architecture: script compiler first, per-site skills later; runs on a fallback ladder |
| 2026-09-30 | Platform-neutral core + one driver per platform; web in v0.1, Windows in v0.2 |
| 2026-09-30 | Problem statement and four promises locked |
| 2026-09-30 | No BrowserGym (pins Playwright 1.44) and no agisdk (pulls in Ray). Our own small runners: MiniWoB++ HTML files + JS reward vars; REAL hosted sites + `/config`, `/finish` JSON + jmespath checks |
| 2026-09-30 | OpenCode Go + deepseek: send the JSON schema in the system prompt, not as `response_format` (strict mode gives HTTP 400 on some schemas and blank-line output on others) |

## Parking lot (ideas for after v0.2)

- Cross-task skills library (memory that carries over between tasks on the same site)
- API fast-path: replay the site's hidden data requests directly
- Adapters for Playwright MCP, Stagehand, Claude computer use, Windows-Use / UFO
- Human recording for web
- macOS / Linux desktop drivers
- Hosted playground website
- WebArena runs (needs cloud credits)
