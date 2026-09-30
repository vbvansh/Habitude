"""Experiment: watch browser-use do one task, then record and compile it.

Playwright and browser-use share one browser: Playwright sets up and grades the
task, browser-use does it. The run is then turned into a trace and compiled into
workflows/<task>/workflow.py.

Usage:
    python scripts/watch_agent.py click-button              # a MiniWoB++ task, visible window
    python scripts/watch_agent.py real:gomail-3             # a REAL task
    python scripts/watch_agent.py enter-text --headless     # no window
"""

import argparse
import asyncio
import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import jmespath
from browser_use import Agent, Browser
from playwright.async_api import Page, async_playwright

from habitude.compiler import compile_to_dir
from habitude.llm import default_llm
from habitude.recorders.browser_use import trace_from_history

ROOT = Path(__file__).resolve().parent.parent
MINIWOB_HTML = ROOT / "third_party" / "miniwob-plusplus" / "miniwob" / "html"
REAL_TASKS_DIR = ROOT / "third_party" / "real-tasks"
REAL_TASK_URL = "https://raw.githubusercontent.com/agi-inc/REAL/main/src/agisdk/REAL/browsergym/webclones/tasks/{}.json"
RUNS_DIR = ROOT / "runs"
WORKFLOWS_DIR = ROOT / "workflows"
HTTP_PORT = 8765  # where we serve the MiniWoB++ pages
CDP_PORT = 9242  # the browser's remote-control port, shared by Playwright and browser-use


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # don't print a line for every file served
        pass


def serve_miniwob():
    """Serve the MiniWoB++ pages at http://127.0.0.1:8765 from a background thread."""
    handler = functools.partial(QuietHandler, directory=str(MINIWOB_HTML))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def start_chrome(executable: str, headless: bool) -> subprocess.Popen:
    """Start Chromium with its remote-control port open, so two programs can drive it."""
    args = [
        executable,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={tempfile.mkdtemp(prefix='habitude-')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1100,800",
        "about:blank",
    ]
    if headless:
        args.insert(1, "--headless=new")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_chrome(timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1)
            return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("Chromium did not open its remote-control port in time")


async def setup_miniwob(page: Page, task: str, seed: int):
    await page.goto(f"http://127.0.0.1:{HTTP_PORT}/miniwob/{task}.html")
    await page.evaluate(
        """seed => {
            Math.seedrandom(seed);
            core.EPISODE_MAX_TIME = 10 * 60 * 1000;  // 10 minutes: LLM agents are slow
            core.startEpisodeReal();
        }""",
        seed,
    )

    async def grade():
        reward = await page.evaluate("WOB_RAW_REWARD_GLOBAL")
        return bool(reward and reward > 0), f"MiniWoB reward {reward}"

    return await page.evaluate("core.getUtterance()"), grade


def load_real_task(task_id: str) -> dict:
    path = REAL_TASKS_DIR / f"{task_id}.json"
    if not path.exists():
        REAL_TASKS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(REAL_TASK_URL.format(task_id), timeout=30).read())
    return json.loads(path.read_text(encoding="utf-8"))


async def setup_real(page: Page, task_id: str):
    task = load_real_task(task_id)
    base = task["website"]["url"].rstrip("/")
    await page.goto(f"{base}/config?run_id=0&task_id={task_id}&latency=0")  # tell the site which task
    await page.goto(f"{base}/finish")
    await page.goto(base)

    async def grade():
        await page.goto(f"{base}/finish")  # the site's summary of everything that changed
        state = json.loads(await page.inner_text("pre"))
        checks = []
        for check in task["evals"]:
            if check["type"] != "jmespath":
                checks.append(f"  ? {check['type']} check (needs an LLM judge, skipped)")
                continue
            actual = jmespath.search(check["query"], state)
            passed = actual == check["expected_value"]
            label = check.get("description") or check["query"]
            checks.append(f"  {'✓' if passed else '✗'} {label}: got {actual!r}")
        graded = [c for c in checks if not c.startswith("  ?")]
        return bool(graded) and all(c.startswith("  ✓") for c in graded), "\n" + "\n".join(checks)

    return task["goal"], grade


async def main(task: str, seed: int, headless: bool, max_steps: int) -> None:
    server = serve_miniwob()
    cdp_url = f"http://127.0.0.1:{CDP_PORT}"
    name = task.removeprefix("real:")

    browser = Browser(cdp_url=cdp_url, keep_alive=True)

    async with async_playwright() as p:
        chrome = start_chrome(p.chromium.executable_path, headless)
        try:
            wait_for_chrome()

            # 1. Playwright connects and sets up the task.
            pw_browser = await p.chromium.connect_over_cdp(cdp_url)
            page = pw_browser.contexts[0].pages[0]
            if task.startswith("real:"):
                goal, grade = await setup_real(page, name)
            else:
                goal, grade = await setup_miniwob(page, task, seed)
            print(f"\nTask:  {task}\nGoal:  {goal}\n")

            # 2. browser-use connects to the same browser and does the task.
            agent = Agent(
                task=f"The web page is already open. Do this on it: {goal}",
                llm=default_llm(),
                browser=browser,
            )
            started = time.time()
            history = await agent.run(max_steps=max_steps)
            seconds = time.time() - started

            # 3. Playwright grades the result in the same browser.
            success, details = await grade()

            RUNS_DIR.mkdir(exist_ok=True)
            raw = RUNS_DIR / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            history.save_to_file(raw)

            # 4. Record and compile.
            trace = trace_from_history(history, task=goal)
            compiled = compile_to_dir(trace, WORKFLOWS_DIR / name)

            print("\n" + "=" * 60)
            print(f"Graded        : {'SUCCESS' if success else 'FAIL'} {details}")
            print(f"Agent says    : done={history.is_done()} success={history.is_successful()}")
            print(f"Steps / time  : {history.number_of_steps()} steps, {seconds:.1f}s")
            print(f"LLM tokens    : {trace.stats.tokens} total")
            print(f"Raw history   : {raw.relative_to(ROOT)}")
            print(f"Workflow      : {(WORKFLOWS_DIR / name).relative_to(ROOT)}/workflow.py")
            print(f"Parameters    : {[(p.name, p.example) for p in compiled.params]}")
            print("=" * 60 + "\n" + compiled.source)
        finally:
            # Disconnect browser-use on purpose first; otherwise it keeps trying to reconnect.
            await browser.stop()
            chrome.terminate()
            server.shutdown()


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")  # show output as it happens
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", nargs="?", default="click-button", help="MiniWoB++ task, or real:<task-id>")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-steps", type=int, default=25)
    args = parser.parse_args()
    asyncio.run(main(args.task, args.seed, args.headless, args.max_steps))
