"""Render a repo-pulse deck and report layout problems.

Usage: uvx --with playwright python check_deck.py <deck.html> [--out DIR]
Prints overflow warnings (the deck's own guard) and JS errors for desktop light/dark, checks the phone layout for
horizontal scroll, and saves one screenshot per slide (light) to DIR (default: a temp dir).
"""
import argparse
import asyncio
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright


async def run(deck: Path, out: Path) -> int:
    url = deck.resolve().as_uri()
    problems = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        for w, h, scheme, shots in [(1440, 900, "light", True), (1280, 720, "dark", False)]:
            page = await browser.new_page(viewport={"width": w, "height": h}, color_scheme=scheme)
            logs: list[str] = []
            page.on("console", lambda m: logs.append(m.text) if m.type in ("warning", "error") else None)
            page.on("pageerror", lambda e: logs.append(f"JS error: {e}"))
            await page.goto(url)
            await page.wait_for_timeout(400)
            n = await page.evaluate("document.querySelectorAll('.slide').length")
            if shots:
                for i in range(n):
                    await page.wait_for_timeout(300)
                    await page.screenshot(path=str(out / f"slide-{i + 1:02d}.png"))
                    await page.keyboard.press("ArrowRight")
            print(f"{w}x{h} {scheme}: {n} slides, {len(logs)} issue(s)")
            for line in logs:
                print("  ", line)
            problems += len(logs)
            await page.close()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        await page.goto(url)
        await page.wait_for_timeout(300)
        hscroll = await page.evaluate("document.documentElement.scrollWidth > innerWidth || "
                                      "[...document.querySelectorAll('.slide')].some(s => s.scrollWidth > s.clientWidth + 1)")
        print(f"phone 390px: {'HORIZONTAL OVERFLOW' if hscroll else 'ok'}")
        problems += int(hscroll)
        await browser.close()
    print(f"screenshots: {out}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="repo-pulse-check-"))
    out.mkdir(parents=True, exist_ok=True)
    raise SystemExit(1 if asyncio.run(run(Path(a.deck), out)) else 0)


if __name__ == "__main__":
    main()
