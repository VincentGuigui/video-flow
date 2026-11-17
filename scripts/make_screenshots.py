#!/usr/bin/env python3
"""Retake the README screenshots (docs/images/) from a generated demo project.

    scripts/dev.sh screenshots [--out docs/images] [--work DIR] [--keep]
    scripts/dev.ps1 screenshots [...]

The demo is eight synthetic "cold brew tutorial" rushes (slides with a synthetic voice,
retakes of steps 1, 2 and 4) that are really imported and analysed: the transcripts,
summaries and stacking in the pictures come from the application. It therefore needs the
FFmpeg `flite` and `drawtext` filters, and the models of the analysis already downloaded
(Settings -> AI models). Playwright is fetched on the fly by `dev.sh screenshots`
(`uv run --with playwright`) and drives Chromium (`playwright install chromium` once, or
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` for an existing build). The frontend must be built
(`scripts/dev.sh build`).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from videoflow.media.caps import NO_WINDOW, locate_binaries  # noqa: E402
from videoflow.runtime import assets_dir  # noqa: E402

VIEWPORT = {"width": 1600, "height": 1100}
# name, slide title, take, gradient colours, what is said
RUSHES = [
    ("01-intro-take1", "Step 1 · Introduction", "1", "0x1f3b2d", "0x3f7a5a",
     "Hello and welcome. Today we will make, um, cold brew coffee. At home, I mean."),
    ("01-intro-take2", "Step 1 · Introduction", "2", "0x1f3b2d", "0x3f7a5a",
     "Hello and welcome. Today we will make cold brew coffee at home, with just two ingredients."),
    ("02-grind-take1", "Step 2 · Grind the beans", "1", "0x4a2c17", "0x9a6236",
     "First, grind one hundred grams of coffee beans. Use a fine setting."),
    ("02-grind-take2", "Step 2 · Grind the beans", "2", "0x4a2c17", "0x9a6236",
     "First, grind one hundred grams of coffee beans. Use a coarse setting, like breadcrumbs."),
    ("03-water", "Step 3 · Add cold water", "1", "0x17384a", "0x2f7ea0",
     "Add one litre of cold water and stir gently, then cover the jar."),
    ("04-wait-take1", "Step 4 · Let it steep", "1", "0x2c2350", "0x6352a8",
     "Leave it in the fridge for twelve to eighteen hours. Not more, or it gets bitter."),
    ("04-wait-take2", "Step 4 · Let it steep", "2", "0x2c2350", "0x6352a8",
     "Leave it in the fridge for twelve to eighteen hours. If you wait longer, it gets bitter."),
    ("05-serve", "Step 5 · Filter and serve", "1", "0x4a1730", "0xa03a6b",
     "Strain the coffee through a paper filter. Serve it over ice, with a little milk. Enjoy!"),
]  # fmt: skip


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, creationflags=NO_WINDOW)  # noqa: S603


def escape(text: str) -> str:
    return text.replace(":", "\\:").replace("'", "’")


def make_rushes(folder: Path) -> None:
    """The eight rushes: a gradient slide, a title, and a flite voice."""
    ffmpeg = str(locate_binaries().ffmpeg)
    ffprobe = str(locate_binaries().ffprobe)
    bold = (assets_dir() / "fonts" / "Inter-Bold.otf").as_posix().replace(":", "\\:")
    regular = (assets_dir() / "fonts" / "Inter-Regular.otf").as_posix().replace(":", "\\:")
    folder.mkdir(parents=True, exist_ok=True)
    for name, title, take, c0, c1, text in RUSHES:
        if (folder / f"{name}.mp4").is_file():
            continue
        wav = folder / f".{name}.wav"
        run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             f"flite=text='{escape(text)}':voice=slt",
             "-af", "apad=pad_dur=0.6,adelay=700|700,aresample=48000", str(wav)])  # fmt: skip
        duration = float(
            subprocess.run(  # noqa: S603
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                 str(wav)],
                capture_output=True, text=True, check=True, creationflags=NO_WINDOW,
            ).stdout
        )  # fmt: skip
        filters = (
            "drawbox=x=80:y=520:w=1760:h=6:color=white@0.35:t=fill,"
            f"drawtext=fontfile={bold}:text='{escape(title)}':fontcolor=white:fontsize=72:x=80:y=380,"
            f"drawtext=fontfile={regular}:text='Cold brew at home':fontcolor=white@0.75:"
            "fontsize=40:x=80:y=300,"
            f"drawtext=fontfile={bold}:text='TAKE {take}':fontcolor=white@0.9:fontsize=34:"
            "x=w-260:y=80,"
            f"drawtext=fontfile={regular}:text='%{{pts\\:hms}}':fontcolor=white@0.6:fontsize=30:"
            "x=w-260:y=h-110"
        )
        run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             f"gradients=s=1920x1080:r=30:c0={c0}:c1={c1}:x0=0:y0=0:x1=1920:y1=1080:"
             f"speed=0.004:d={duration}",
             "-i", str(wav), "-vf", filters, "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "20", "-pix_fmt", "yuv420p", "-g", "30", "-c:a", "aac", "-b:a", "128k",
             "-shortest", str(folder / f"{name}.mp4")])  # fmt: skip
        wav.unlink()
        print("rush", name)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class App:
    """The application served on a local port, with its own cache."""

    def __init__(self, project: Path, media: Path, cache: Path) -> None:
        self.port = free_port()
        self.log = (cache.parent / "serve.log").open("w", encoding="utf-8")
        # No update offer in the pictures, whatever GitHub answers.
        environment = {
            **os.environ,
            "VIDEOFLOW_CACHE_DIR": str(cache),
            "VIDEOFLOW_UPDATE_URL": (cache.parent / "no-release.json").as_uri(),
        }
        self.process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "videoflow", "serve", "--no-open-browser",
             "--port", str(self.port), "--media-root", str(media), "--project", str(project)],
            stdout=self.log, stderr=subprocess.STDOUT, env=environment, cwd=ROOT / "backend",
        )  # fmt: skip
        self.url = ""
        for _ in range(120):
            text = Path(self.log.name).read_text(encoding="utf-8")
            marker = f"http://127.0.0.1:{self.port}/?token="
            if marker in text:
                self.url = marker + text.split(marker)[1].split()[0]
                return
            if self.process.poll() is not None:
                raise SystemExit(f"The application did not start:\n{text}")
            time.sleep(0.5)
        raise SystemExit("The application did not start in time")

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()


def import_rushes(page, folder: Path) -> None:
    """Import and analyse every rush through the API, then wait for the previews."""
    for name, *_ in RUSHES:
        status = page.evaluate(
            """async (path) => (await fetch('/api/import-path', {method: 'POST',
              headers: {'content-type': 'application/json'},
              body: JSON.stringify({path, analyse: true})})).status""",
            str(folder / f"{name}.mp4"),
        )
        if status != 200:
            raise SystemExit(f"Import of {name} refused ({status})")
    for _ in range(900):
        jobs = page.evaluate("async () => await (await fetch('/api/jobs')).json()")
        jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", list(jobs.values()))
        if jobs and all(j["state"] not in ("queued", "running", "waiting-models") for j in jobs):
            failed = [j for j in jobs if j["state"] != "done"]
            if failed:
                raise SystemExit(
                    f"Imports failed: {[(j['filename'], j['state'], j.get('error')) for j in failed]}"
                )
            break
        time.sleep(2)
    else:
        raise SystemExit("The imports did not finish")
    for _ in range(300):
        states = page.evaluate("async () => await (await fetch('/api/previews')).json()")
        if all(s["state"] == "ready" for s in states.values()):
            return
        time.sleep(1)
    raise SystemExit("The previews did not finish")


def shrink(source: Path, target: Path, width: int, crop: tuple[int, int, int, int] | None) -> None:
    from PIL import Image

    image = Image.open(source).convert("RGB")
    if crop:
        image = image.crop(crop)
    width = min(width, image.width)
    image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    image.save(target, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "images")
    parser.add_argument("--work", type=Path, help="Folder for the demo files (default: temporary)")
    parser.add_argument("--keep", action="store_true", help="Keep the demo folder")
    args = parser.parse_args()
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("Build the interface first: scripts/dev.sh build")
    from playwright.sync_api import sync_playwright

    work = args.work or Path(tempfile.mkdtemp(prefix="videoflow-screenshots-"))
    media = work / "Cold-brew-rushes"
    raw = work / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    make_rushes(media)
    app = App(media / "Cold brew tutorial.video-flow", media, work / "cache")
    try:
        with sync_playwright() as playwright:
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            browser = playwright.chromium.launch(executable_path=executable or None)
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
            page.goto(app.url)
            page.wait_for_selector(".properties-dock")
            import_rushes(page, media)
            page.reload()
            page.wait_for_selector('[data-testid="clip-video"]')
            capture(page, raw)
            browser.close()
    finally:
        app.close()
    crops = {"compare": (360, 600, 2840, 1600), "export": (1029, 328, 2171, 1874),
             "settings": (699, 69, 2501, 2133)}  # fmt: skip
    for name in ("overview", "compare", "search", "finish", "export", "settings"):
        shrink(raw / f"{name}.png", args.out / f"{name}.png", 1200 if name in crops else 1600,
               crops.get(name))  # fmt: skip
        print("image", args.out / f"{name}.png")
    if not args.keep and not args.work:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def clip(page, name: str, kind: str = "video"):
    return page.locator(f'[data-testid="clip-{kind}"]').filter(has_text=name).first


def settle(page, ms: int = 800) -> None:
    page.wait_for_timeout(ms)


def capture(page, raw: Path) -> None:
    def shot(name: str) -> None:
        settle(page)
        page.screenshot(path=str(raw / f"{name}.png"))
        print("shot", name)

    def flow_to_bottom() -> None:
        page.evaluate(
            "() => { const f = document.querySelector('.flow-scroll'); if (f) f.scrollTop = f.scrollHeight; }"
        )

    def top_of_flow() -> None:
        page.evaluate(
            "() => { const f = document.querySelector('.flow-scroll'); if (f) f.scrollTop = 0; }"
        )

    # Compare the retakes and keep the second take of each step (key 2).
    for name in ("01-intro-take1", "02-grind-take1", "04-wait-take1"):
        clip(page, name).click()
        page.click("text=Compare takes")
        settle(page, 2500 if name == "01-intro-take1" else 800)
        if name == "01-intro-take1":
            shot("compare")
        page.keyboard.press("2")
        settle(page, 400)
        page.keyboard.press("Escape")
        settle(page, 400)
    page.keyboard.press("Home")

    # Overview: a picked take selected, with its transcript.
    clip(page, "02-grind-take2").click()
    page.click("text=Transcript")
    page.keyboard.press("Control+ArrowRight")  # ten seconds in: inside step 2
    flow_to_bottom()
    shot("overview")

    # Text search.
    page.keyboard.press("Escape")
    page.keyboard.press("Control+f")
    page.keyboard.type("bitter")
    settle(page, 500)
    page.keyboard.press("Enter")
    flow_to_bottom()
    shot("search")
    page.fill('[aria-label="Search what is said"]', "")
    page.keyboard.press("Escape")

    # Finishing: lower third, dissolves on every cut, a fade in.
    page.keyboard.press("Home")
    page.click("text=Lower third")
    settle(page, 800)
    page.locator('[aria-label="Title text"]').fill("Cold brew at home\nA recipe in five steps")
    page.locator('[aria-label="Title text"]').blur()
    settle(page, 1200)
    page.locator('[aria-label="Cut: add a transition"]').first.click()
    settle(page, 600)
    page.click("text=Apply cross dissolve to all cuts")
    settle(page, 800)
    page.keyboard.press("Home")
    for _ in range(2):
        page.keyboard.press("Shift+ArrowRight")
    clip(page, "01-intro-take2").click()
    page.click(".properties-dock >> text=Effects")
    page.click("text=Add effect")
    settle(page, 400)
    page.click("text=Fade in")
    settle(page, 600)
    top_of_flow()
    shot("finish")

    # Export and settings windows.
    page.click('button:has-text("Export")')
    settle(page, 800)
    shot("export")
    page.reload()  # closes the window
    page.wait_for_selector(".properties-dock")
    page.click('[aria-label="Settings"]')
    settle(page, 1500)
    shot("settings")


if __name__ == "__main__":
    raise SystemExit(main())
