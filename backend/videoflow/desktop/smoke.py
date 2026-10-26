"""Exercise the real Qt WebEngine window with generated media, without a browser.

Run scripts/desktop_smoke.py with the backend Python, --media PATH --output DIRECTORY.
Creates a fresh disposable project and a screenshot/report under the output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from videoflow.desktop.host import Backend, EditorWindow
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def editor_clips(bundle: Bundle) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = (
        (bundle.project.model_extra or {}).get("editor", {}).get("clips", [])
    )
    return clips


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--features", action="store_true")
    args = parser.parse_args(argv)
    media, output = args.media.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = hashlib.sha256(media.read_bytes()).hexdigest()
    bundle = Bundle.create(
        output / f"smoke-{uuid.uuid4().hex[:8]}.videoflow",
        new_project("Desktop playback check"),
    )
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    app = QApplication(sys.argv[:1])
    backend = Backend(bundle, port, [bundle.path / "browser-only"])
    backend.start()
    window = EditorWindow(backend, "Desktop playback check")
    window.show()
    started = time.monotonic()
    phase = "loading"
    report: dict[str, Any] = {
        "platform": sys.platform,
        "media": str(media),
        "checks": [],
        "success": False,
    }
    pending = False
    timer = QTimer()
    timer.setInterval(200)
    failures: list[str] = []

    def finish(error: str | None = None) -> None:
        timer.stop()
        if error:
            failures.append(error)
            report["error"] = error
        report["elapsedSeconds"] = round(time.monotonic() - started, 2)
        window.grab().save(str(output / "desktop.png"))
        window.close()
        report["backendStopped"] = not backend.thread.is_alive()
        report["sourceUnchanged"] = before == hashlib.sha256(media.read_bytes()).hexdigest()
        report["noOriginalCopies"] = not (bundle.path / "media").exists()
        report["success"] = (
            not failures
            and report["backendStopped"]
            and report["sourceUnchanged"]
            and report["noOriginalCopies"]
        )
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        app.quit()

    def js(source: str) -> None:
        window.page.runJavaScript(source)

    def result(raw: str | None) -> None:
        nonlocal phase, pending
        pending = False
        if not raw:
            # The first poll or a reload can arrive before the JS context exists.
            return
        try:
            state = json.loads(raw)
            if state.get("settingsOpen"):
                js("document.querySelector('[aria-label=\"Close settings\"]')?.click()")
                return
            if phase == "loading" and state["ready"]:
                js("document.querySelector('[aria-label=\"Close settings\"]')?.click()")
                report["codecs"] = state["codecs"]
                report["checks"].append("Trusted native bridge connected")
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(media))])
                enter = QDragEnterEvent(
                    QPoint(300, 350),
                    Qt.DropAction.CopyAction,
                    mime,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                QApplication.sendEvent(window.view, enter)
                drop = QDropEvent(
                    QPointF(300, 350),
                    Qt.DropAction.CopyAction,
                    mime,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                QApplication.sendEvent(window.view, drop)
                phase = "native-selection"
            elif phase == "native-selection" and state["importChoice"]:
                report["checks"].append("Native local-file drop delivered scoped selection")
                js(
                    "[...document.querySelectorAll('button')]"
                    ".find(b=>b.textContent.includes('Import only')).click();"
                )
                js(
                    "[...document.querySelectorAll('button.primary')]"
                    ".find(b=>b.textContent.includes('Import 1')).click();"
                )
                phase = "importing"
            elif phase == "importing" and state["importDone"]:
                report["checks"].append(
                    "Original imported outside browser roots without byte upload"
                )
                js(
                    "[...document.querySelectorAll('button')]"
                    ".find(b=>b.textContent.includes('Back to editor')).click();"
                )
                phase = "decoding"
            elif phase == "decoding" and state["videoReady"]:
                report["checks"].append("Qt WebEngine decoded the video preview")
                report["playback"] = state["video"]
                widget = window.view.focusProxy() or window.view
                widget.setFocus()
                QTest.keyClick(widget, Qt.Key.Key_Space)
                phase = "playing"
            elif (
                phase == "playing"
                and state["timecode"] != "00:00:00:00"
                and state["videoTime"] > 0.05
            ):
                widget = window.view.focusProxy() or window.view
                QTest.keyClick(widget, Qt.Key.Key_Space)
                report["checks"].append("Space played media and advanced the frame cursor")
                js(
                    "document.querySelector('[data-testid=clip-video]')"
                    ".dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));"
                )
                phase = "focused"
            elif phase == "focused" and state["focused"]:
                widget = window.view.focusProxy() or window.view
                QTest.keyClick(widget, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
                QTimer.singleShot(150, lambda: QTest.keyClick(widget, Qt.Key.Key_S))
                phase = "split"
            elif phase == "split" and state["videoClips"] == 2 and state["audioClips"] == 2:
                report["checks"].append("Focused edit and linked split produced two AV pairs")
                QTest.keyClick(
                    window.view.focusProxy() or window.view,
                    Qt.Key.Key_Z,
                    Qt.KeyboardModifier.ControlModifier,
                )
                phase = "undo"
            elif phase == "undo" and state["videoClips"] == 1 and state["audioClips"] == 1:
                report["checks"].append("Undo restored the linked clip pair")
                if args.features:
                    js(
                        "document.querySelector('[data-testid=clip-video]')"
                        ".dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));"
                    )
                    phase = "properties"
                else:
                    window.view.reload()
                    phase = "reloaded"
            elif phase == "properties" and state["focused"]:
                if not state["singleTimeline"] or not state["sourceRangeClosed"]:
                    raise ValueError("Timeline or properties layout regressed")
                js(
                    "const input=document.querySelector('[aria-label=\"Clip x\"]');"
                    "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'35');"
                    "input.dispatchEvent(new Event('input',{bubbles:true}));"
                )
                phase = "live-properties"
            elif phase == "live-properties" and state["previewX"] == "35px" and not state["saving"]:
                js("document.querySelector('.detach-action').click()")
                phase = "unlinked"
            elif phase == "unlinked" and state["linkOptions"] > 1 and not state["saving"]:
                js(
                    "const select=document.querySelector('[aria-label=\"Link clip\"]');"
                    "select.value=select.options[1].value;"
                    "select.dispatchEvent(new Event('change',{bubbles:true}));"
                )
                phase = "relinked"
            elif phase == "relinked" and state["chains"] == 1 and not state["linkOptions"]:
                report["checks"].append(
                    "One assembly axis, collapsed source range, live properties and AV relinking"
                )
                js(
                    "document.querySelector('[data-testid=clip-audio]')"
                    ".dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));"
                )
                phase = "audio-trim"
            elif phase == "audio-trim" and state["audioTrimHandles"] == 2 and not state["saving"]:
                js(
                    "const handle=document.querySelector('[aria-label=\"out audio trim\"]');"
                    "const bounds=handle.getBoundingClientRect();"
                    "handle.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,"
                    "clientX:bounds.x,clientY:bounds.y}));"
                    "window.dispatchEvent(new PointerEvent('pointermove',"
                    "{clientX:bounds.x-30,clientY:bounds.y}));"
                    "window.dispatchEvent(new PointerEvent('pointerup',"
                    "{clientX:bounds.x-30,clientY:bounds.y}));"
                )
                phase = "audio-trimmed"
            elif phase == "audio-trimmed" and any(c.get("heldRange") for c in editor_clips(bundle)):
                if any(c.get("kind") == "gap" for c in editor_clips(bundle)):
                    raise ValueError("Audio trim inserted a fake gap")
                report["checks"].append(
                    "Standard audio handles retain time without fake silence clips"
                )
                window.view.reload()
                phase = "reloaded"
            elif (
                phase == "reloaded"
                and state["ready"]
                and state["videoReady"]
                and state["videoClips"] == 1
            ):
                report["checks"].append("Reload preserved original references and edit")
                js("document.querySelector('[aria-label=\"Close settings\"]')?.click()")
                if args.features:
                    if not state["previewFits"]:
                        raise ValueError("Preview canvas overflows its available viewport")
                    js("document.querySelector('[aria-label=\"Zoom in interface\"]').click()")
                    phase = "interface-zoom"
                else:
                    finish()
            elif phase == "interface-zoom" and abs(window.view.zoomFactor() - 1.1) < 0.01:
                report["checks"].append("Status zoom changes Qt WebEngine zoom and preview fits")
                js(
                    "document.querySelector('[aria-label=\"Reset interface zoom\"]').click();"
                    "document.querySelector('.brand').click()"
                )
                phase = "home"
            elif phase == "home" and state["homeProjects"] > 0:
                report["checks"].append("Logo opens the project home screen")
                js(
                    "[...document.querySelectorAll('.home-page button')]"
                    ".find(b=>b.textContent==='Back to editor').click();"
                    "document.querySelector('[data-testid=clip-video]')"
                    ".dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));"
                )
                phase = "background"
            elif phase == "background" and state["focused"]:
                js(
                    "const s=document.querySelector('[aria-label=\"Clip background\"]');"
                    "s.value='blur';s.dispatchEvent(new Event('change',{bubbles:true}));"
                )
                phase = "blurred"
            elif phase == "blurred" and state["blurred"]:
                report["checks"].append("Focused video has a decoded blurred backdrop")
                js(
                    "[...document.querySelectorAll('.header-actions button')]"
                    ".find(b=>b.textContent.includes('Export')).click()"
                )
                phase = "export-panel"
            elif phase == "export-panel" and state["renderPanel"]:
                js(
                    "const s=document.querySelector('[aria-label=\"Render quality\"]');"
                    "s.value='draft';s.dispatchEvent(new Event('change',{bubbles:true}));"
                )
                QTimer.singleShot(
                    200,
                    lambda: js("document.querySelector('.render-panel .export-option').click()"),
                )
                phase = "rendered"
            elif phase == "rendered" and state["renderDone"]:
                report["checks"].append("Export produced a validated MP4 with blurred background")
                js(
                    "document.querySelector('[aria-label=\"Close export\"]').click();"
                    "document.querySelector('[aria-label=\"Save options\"]').click()"
                )
                phase = "save-menu"
            elif phase == "save-menu" and state["saveMenu"]:
                js("document.querySelector('.save-menu button').click()")
                phase = "save-copy"
            elif phase == "save-copy" and state["saveDialog"]:
                js("document.querySelector('[aria-label=\"Save as\"]').requestSubmit()")
                phase = "saved-copy"
            elif phase == "saved-copy" and state["copySaved"]:
                report["checks"].append("Save as created a new named project and retained media")
                finish()
        except Exception as exc:
            finish(str(exc))

    def poll() -> None:
        nonlocal pending
        if time.monotonic() - started > (120 if args.features else 60):
            finish(f"Timed out in phase: {phase}")
            return
        if pending:
            return
        pending = True
        window.page.runJavaScript(
            """JSON.stringify({
          settingsOpen:!!document.querySelector('[aria-label="Close settings"]'),
          saving:!!document.querySelector('.save-status.saving'),
          ready: !!window.videoFlowDesktop && !!document.querySelector('.flow-panel'),
          codecs: {mp4:document.createElement('video').canPlayType(
                        'video/mp4; codecs="avc1.42E01E"'),
                   webm:document.createElement('video').canPlayType('video/webm; codecs="vp9"')},
          importChoice:!!document.querySelector('.analysis-option'),
          importDone:document.body.innerText.includes('Import complete'),
          videoReady:!!document.querySelector('video')&&document.querySelector('video').readyState>=2,
          videoTime:document.querySelector('video')?.currentTime||0,
          video:{width:document.querySelector('video')?.videoWidth,
                 height:document.querySelector('video')?.videoHeight},
          timecode:document.querySelector('[data-testid=timecode]')?.textContent,
          focused:!!document.querySelector('.exit-focus'),
          videoClips:document.querySelectorAll('[data-testid=clip-video]').length,
          audioClips:document.querySelectorAll('[data-testid=clip-audio]').length,
          previewFits:(()=>{const v=document.querySelector('.viewport')?.getBoundingClientRect();
            const p=document.querySelector('.preview-body')?.getBoundingClientRect();
            return !!v&&!!p&&v.height<=p.height+1&&v.width<=p.width+1;})(),
          singleTimeline:!document.querySelector(
            '.flow-ruler,.flow-playhead,.flow-panel .zoom-controls')
            &&!!document.querySelector('.transport-heading .zoom-controls'),
          sourceRangeClosed:!!document.querySelector('.source-range:not([open])'),
          previewX:document.querySelector('.output-canvas video')?.style.left,
          linkOptions:document.querySelector('[aria-label="Link clip"]')?.options.length||0,
          chains:document.querySelectorAll('.chain-button').length,
          audioTrimHandles:document.querySelectorAll('.audio-trim-handle').length,
          homeProjects:document.querySelectorAll('.home-page article').length,
          blurred:[...document.querySelectorAll('video')].some(v=>
            v.style.filter.includes('blur')&&v.readyState>=2),
          renderPanel:!!document.querySelector('.render-panel'),
          renderDone:!!document.querySelector('.render-panel .output-result p'),
          saveMenu:!!document.querySelector('.save-menu'),
          saveDialog:!!document.querySelector('[aria-label="Save as"]'),
          copySaved:!document.querySelector('[aria-label="Save as"]')&&
            document.body.innerText.includes('All changes saved')&&
            !!document.querySelector('[data-testid=clip-video]')
        })""",
            result,
        )

    timer.timeout.connect(poll)
    timer.start()
    app.exec()
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
