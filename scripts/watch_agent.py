"""Day 1 experiment: watch browser-use do one MiniWoB++ task.

It also proves that Playwright and browser-use can control the *same* browser:
Playwright starts the task and reads the score, browser-use does the task.

Usage:
    python scripts/watch_agent.py click-button              # opens a visible window
    python scripts/watch_agent.py click-button --headless   # no window
"""

import argparse
import asyncio
import functools
import http.server
import json
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from browser_use import Agent, Browser
from playwright.async_api import async_playwright

from habitude.llm import default_llm

ROOT = Path(__file__).resolve().parent.parent
MINIWOB_HTML = ROOT / "third_party" / "miniwob-plusplus" / "miniwob" / "html"
RUNS_DIR = ROOT / "runs"
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


async def main(task: str, seed: int, headless: bool, max_steps: int) -> None:
    server = serve_miniwob()
    cdp_url = f"http://127.0.0.1:{CDP_PORT}"

    async with async_playwright() as p:
        chrome = start_chrome(p.chromium.executable_path, headless)
        try:
            wait_for_chrome()

            # 1. Playwright connects and sets up the task.
            pw_browser = await p.chromium.connect_over_cdp(cdp_url)
            page = pw_browser.contexts[0].pages[0]
            await page.goto(f"http://127.0.0.1:{HTTP_PORT}/miniwob/{task}.html")
            await page.evaluate(
                """seed => {
                    Math.seedrandom(seed);
                    core.EPISODE_MAX_TIME = 10 * 60 * 1000;  // 10 minutes: LLM agents are slow
                    core.startEpisodeReal();
                }""",
                seed,
            )
            goal = await page.evaluate("core.getUtterance()")
            print(f"\nTask:  {task} (seed {seed})\nGoal:  {goal}\n")

            # 2. browser-use connects to the same browser and does the task.
            agent = Agent(
                task=f"The web page is already open. Do this on it: {goal}",
                llm=default_llm(),
                browser=Browser(cdp_url=cdp_url, keep_alive=True),
            )
            started = time.time()
            history = await agent.run(max_steps=max_steps)
            seconds = time.time() - started

            # 3. Playwright reads the score from the same page.
            done = await page.evaluate("WOB_DONE_GLOBAL")
            reward = await page.evaluate("WOB_RAW_REWARD_GLOBAL")
            reason = await page.evaluate("WOB_REWARD_REASON")

            RUNS_DIR.mkdir(exist_ok=True)
            out = RUNS_DIR / f"{task}-seed{seed}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            history.save_to_file(out)

            usage = history.usage
            print("\n" + "=" * 60)
            print(f"MiniWoB score : {reward} ({'SUCCESS' if reward and reward > 0 else 'FAIL'}; done={done}, {reason})")
            print(f"Agent says    : done={history.is_done()} success={history.is_successful()}")
            print(f"Steps / time  : {history.number_of_steps()} steps, {seconds:.1f}s")
            if usage:
                print(f"LLM tokens    : {usage.total_tokens} total")
            print(f"Actions       : {json.dumps(history.model_actions(), default=str)[:600]}")
            print(f"Saved history : {out.relative_to(ROOT)}")
        finally:
            chrome.terminate()
            server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", nargs="?", default="click-button", help="MiniWoB++ task name")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()
    asyncio.run(main(args.task, args.seed, args.headless, args.max_steps))
