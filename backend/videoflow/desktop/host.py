"""PySide6 window, restricted WebChannel and owned loopback-service lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QFile, QIODevice, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QWidget

from videoflow.api.app import create_app
from videoflow.media.ingest import MEDIA_EXTENSIONS
from videoflow.project.store import Bundle

LOG = logging.getLogger(__name__)


class Backend:
    """An owned server thread; its lifespan closes imports and their child processes."""

    def __init__(self, bundle: Bundle, port: int, roots: list[Path] | None) -> None:
        import uvicorn

        self.token, self.secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{port}"
        app = create_app(
            bundle, token=self.token, port=port, media_roots=roots, desktop_secret=self.secret
        )
        self.server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                timeout_graceful_shutdown=3,
                timeout_keep_alive=1,
            )
        )
        self.loop: asyncio.AbstractEventLoop | None = None
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="video-flow-backend", daemon=True)

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.server.serve())
        except BaseException as exc:
            self.error = exc
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.close()

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if self.error is not None or not self.thread.is_alive():
                raise RuntimeError(f"Local backend could not start: {self.error}")
            if time.monotonic() > deadline:
                self.close()
                raise RuntimeError("Timed out starting the local backend")
            time.sleep(0.03)

    def selection(self, paths: list[Path], asset_id: str | None = None) -> dict[str, Any]:
        body = json.dumps({"paths": [str(p) for p in paths], "assetId": asset_id}).encode()
        request = urllib.request.Request(
            self.origin + "/api/desktop/selection",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Cookie": f"videoflow={self.token}",
                "X-VideoFlow-Desktop": self.secret,
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result: dict[str, Any] = json.load(response)
            return result

    def save_render(self, identifier: str, path: str) -> None:
        request = urllib.request.Request(
            self.origin + "/api/desktop/render-save",
            data=json.dumps({"id": identifier, "path": path}).encode(),
            headers={
                "Content-Type": "application/json",
                "Cookie": f"videoflow={self.token}",
                "X-VideoFlow-Desktop": self.secret,
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()

    def close(self) -> None:
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(10)
        if self.thread.is_alive():
            self.server.force_exit = True
            if self.loop:

                def cancel() -> None:
                    for task in asyncio.all_tasks(self.loop):
                        task.cancel()

                self.loop.call_soon_threadsafe(cancel)
            self.thread.join(5)
        if self.thread.is_alive():
            LOG.error("Backend did not finish shutdown within 15 seconds")


def trusted_url(url: QUrl, origin: str) -> bool:
    expected = QUrl(origin)
    return (
        url.scheme() == expected.scheme()
        and url.host() == expected.host()
        and url.port() == expected.port()
        and not url.userInfo()
    )


class LocalPage(QWebEnginePage):
    def __init__(self, origin: str, parent: QObject) -> None:
        super().__init__(parent)
        self.origin = origin

    def acceptNavigationRequest(self, url: QUrl | str, nav_type: Any, is_main_frame: bool) -> bool:
        url = QUrl(url)
        if trusted_url(url, self.origin):
            return True
        if (
            is_main_frame
            and nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
            and url.scheme() in ("https", "http")
        ):
            QDesktopServices.openUrl(url)
        return False


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def __init__(self, origin: str, parent: QObject) -> None:
        super().__init__(parent)
        self.origin = origin

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl()
        if url.scheme() not in ("data", "blob", "qrc") and not trusted_url(url, self.origin):
            info.block(True)


class NativeBridge(QObject):
    filesSelected = Signal(str)
    failed = Signal(str)

    def __init__(self, window: QMainWindow, view: QWebEngineView, backend: Backend) -> None:
        super().__init__(window)
        self.window, self.view, self.backend = window, view, backend

    def trusted(self) -> bool:
        return trusted_url(self.view.url(), self.backend.origin)

    @Slot(float)
    def setZoom(self, factor: float) -> None:
        if self.trusted() and 0.5 <= factor <= 2.0:
            self.view.setZoomFactor(factor)

    @Slot(str)
    def saveRenderedVideo(self, identifier: str) -> None:
        if not self.trusted():
            return
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Save MP4 video", "video.mp4", "MP4 video (*.mp4)"
        )
        if path:
            try:
                self.backend.save_render(identifier, path)
            except (OSError, ValueError) as exc:
                self.failed.emit(str(exc))

    @Slot()
    def pickFiles(self) -> None:
        if not self.trusted():
            return
        extensions = " ".join(f"*{extension}" for extension in sorted(MEDIA_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self.window, "Import original media", "", f"Video and audio ({extensions})"
        )
        self.select([Path(path) for path in paths])

    @Slot(str)
    def relink(self, asset_id: str) -> None:
        if not self.trusted() or not asset_id or len(asset_id) > 200:
            return
        path, _ = QFileDialog.getOpenFileName(self.window, "Relink original media")
        if path:
            self.select([Path(path)], asset_id)

    def select(self, paths: list[Path], asset_id: str | None = None) -> None:
        if not paths or not self.trusted():
            return

        def grant() -> None:
            try:
                result = self.backend.selection(paths, asset_id)
                self.filesSelected.emit(json.dumps(result))
            except Exception as exc:
                self.failed.emit(f"Could not select media: {exc}")

        threading.Thread(target=grant, name="native-media-selection", daemon=True).start()


class DropFilter(QObject):
    def __init__(self, view: QWebEngineView, bridge: NativeBridge) -> None:
        super().__init__(view)
        self.view, self.bridge = view, bridge

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() not in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            return False
        if not isinstance(watched, QWidget) or not (
            watched == self.view or self.view.isAncestorOf(watched)
        ):
            return False
        mime = event.mimeData()  # type: ignore[attr-defined]
        if not mime.hasUrls() or not self.bridge.trusted():
            return False
        urls = mime.urls()
        if not urls or not all(url.isLocalFile() for url in urls):
            event.ignore()
            return True
        event.acceptProposedAction()  # type: ignore[attr-defined]
        if event.type() == QEvent.Type.Drop:
            self.bridge.select(
                [
                    Path(url.toLocalFile())
                    for url in urls
                    if Path(url.toLocalFile()).suffix.casefold() in MEDIA_EXTENSIONS
                ]
            )
        return True


class EditorWindow(QMainWindow):
    def __init__(self, backend: Backend, title: str) -> None:
        super().__init__()
        self.backend = backend
        self.setWindowTitle(f"{title} — Video-Flow")
        self.resize(1440, 980)
        self.setMinimumSize(850, 720)
        self.view = QWebEngineView(self)
        self.view.setAcceptDrops(True)
        self.page = LocalPage(backend.origin, self.view)
        self.view.setPage(self.page)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        self.interceptor = LocalRequests(backend.origin, self.page)
        self.page.profile().setUrlRequestInterceptor(self.interceptor)
        self.channel = QWebChannel(self.page)
        self.bridge = NativeBridge(self, self.view, backend)
        self.channel.registerObject("desktop", self.bridge)
        self.page.setWebChannel(self.channel)
        source = QFile(":/qtwebchannel/qwebchannel.js")
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Qt WebChannel script is missing from the Qt runtime")
        bootstrap = (
            bytes(source.readAll().data()).decode("utf-8")
            + """
window.__videoflowDesktop = true;
new QWebChannel(qt.webChannelTransport, function(channel) {
  const host = channel.objects.desktop;
  window.videoFlowDesktop = {pickFiles: () => host.pickFiles(),
    setZoom: factor => host.setZoom(factor),
    relink: id => host.relink(id), saveRenderedVideo: id => host.saveRenderedVideo(id)};
  host.filesSelected.connect(value => window.dispatchEvent(
    new CustomEvent('videoflow-selection', {detail: JSON.parse(value)})));
  host.failed.connect(message => window.dispatchEvent(
    new CustomEvent('videoflow-error', {detail: message})));
  window.dispatchEvent(new Event('videoflow-ready'));
});
"""
        )
        script = QWebEngineScript()
        script.setName("video-flow-native-bridge")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(bootstrap)
        self.page.scripts().insert(script)
        self.drop_filter = DropFilter(self.view, self.bridge)
        QApplication.instance().installEventFilter(self.drop_filter)  # type: ignore[union-attr]
        self.setCentralWidget(self.view)
        self.view.setUrl(QUrl(backend.origin + "/?token=" + backend.token))

    def closeEvent(self, event: Any) -> None:
        self.view.stop()
        self.channel.deregisterObject(self.bridge)
        self.backend.close()
        event.accept()


def run_desktop(bundle: Bundle, *, port: int = 0, roots: list[Path] | None = None) -> int:
    if not port:
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Video-Flow")
    app.setOrganizationName("Video-Flow")
    backend = Backend(bundle, port, roots)
    app.aboutToQuit.connect(backend.close)
    try:
        backend.start()
        window = EditorWindow(backend, bundle.project.name)
        window.show()
        return int(app.exec())
    finally:
        backend.close()
