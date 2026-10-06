"""Capture deck slides (2x, light theme) as video assets: uvx --with playwright python media/video/scripts/capture.py

Captures only from the published, anonymized example decks in docs/examples/ (built with `build --anonymize`), so no
person's name can end up in the video or the README GIF.
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[3]
DECKS = ROOT / "docs" / "examples"
OUT = Path(__file__).resolve().parents[1] / "public" / "slides"
SHOTS = {  # deck -> {slide number: asset name}
    "trl.html": {2: "trl-summary", 3: "trl-scorecard", 14: "trl-p1"},
}


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):  # keep only what the video uses
        old.unlink()
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        for deck, shots in SHOTS.items():
            pg = await b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2, color_scheme="light")
            for n, name in shots.items():
                await pg.goto((DECKS / deck).as_uri() + f"#{n}")
                await pg.reload()  # hash-only navigation does not re-run the deck's start-slide logic
                await pg.add_style_tag(content="#nav,#tip{display:none!important}")
                await pg.wait_for_timeout(500)
                await pg.locator(".slide.active").screenshot(path=str(OUT / f"{name}.png"))
            await pg.close()
        await b.close()
    print(sorted(x.name for x in OUT.glob("*.png")))

asyncio.run(main())
