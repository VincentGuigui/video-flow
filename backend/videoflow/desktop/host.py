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

from PySide6.QtCore import QEvent, QFile, QIODevice, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from videoflow.desktop import startup
from videoflow.media.ingest import MEDIA_EXTENSIONS
from videoflow.project.store import Bundle
from videoflow.runtime import assets_dir

LOG = logging.getLogger(__name__)


STARTUP_TIMEOUT = 30
"""Seconds the window waits for the local backend before reporting a failure."""


class Backend:
    """An owned server thread; its lifespan closes imports and their child processes.

    The thread imports and builds the API itself, so the window can open and Qt WebEngine
    can start while it does (docs/reference/desktop-runtime.md).
    """

    def __init__(
        self, bundle: Bundle, port: int, roots: list[Path] | None, project_open: bool = True
    ) -> None:
        self.bundle, self.port, self.roots, self.project_open = bundle, port, roots, project_open
        self.token, self.secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{port}"
        self.server: Any = None
        self.stopping = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="video-flow-backend", daemon=True)

    def _build(self) -> Any:
        import uvicorn

        from videoflow.api.app import create_app

        app = create_app(
            self.bundle,
            token=self.token,
            port=self.port,
            media_roots=self.roots,
            desktop_secret=self.secret,
            project_open=self.project_open,
        )
        return uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
                timeout_graceful_shutdown=3,
                timeout_keep_alive=1,
            )
        )

    @property
    def ready(self) -> bool:
        return self.server is not None and bool(self.server.started)

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.server = self._build()
            startup.mark("backend code")
            if self.stopping:
                return
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
        """Start the backend thread; `ready` tells when it serves."""
        self.thread.start()

    def wait(self, timeout: float = STARTUP_TIMEOUT) -> None:
        """Block until the backend serves (scripts and checks; the window does not block)."""
        deadline = time.monotonic() + timeout
        while not self.ready:
            if self.error is not None or not self.thread.is_alive():
                raise RuntimeError(f"Local backend could not start: {self.error}")
            if time.monotonic() > deadline:
                self.close()
                raise RuntimeError("Timed out starting the local backend")
            time.sleep(0.01)

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

    def folder(self, path: Path, purpose: str) -> dict[str, Any]:
        """A single-use handle for a natively selected working or project folder."""
        request = urllib.request.Request(
            self.origin + "/api/desktop/folder",
            data=json.dumps({"path": str(path), "purpose": purpose}).encode(),
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
        self.stopping = True
        if self.server is not None:
            self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(10)
        if self.thread.is_alive() and self.server is not None:
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
    folderSelected = Signal(str)
    failed = Signal(str)

    def __init__(self, window: QMainWindow, view: QWebEngineView, backend: Backend) -> None:
        super().__init__(window)
        self.window, self.view, self.backend = window, view, backend

    def trusted(self) -> bool:
        return trusted_url(self.view.url(), self.backend.origin)

    @Slot()
    def ready(self) -> None:
        """The editor shows its first data: the end of the startup timeline."""
        if self.trusted():
            startup.mark("editor")
            startup.report()

    @Slot()
    def quit(self) -> None:
        """Close the app so the downloaded update can replace it
        (docs/features/getting-started/updates.md)."""
        if self.trusted():
            self.window.close()

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
    def pickFolder(self, purpose: str) -> None:
        """A working folder for a new project, or an existing `.video-flow` project folder."""
        if not self.trusted() or purpose not in ("workdir", "project"):
            return
        title = (
            "Choose the working folder (with your media)"
            if purpose == "workdir"
            else "Open a Video-Flow project folder (.video-flow)"
        )
        path = QFileDialog.getExistingDirectory(self.window, title)
        if not path:
            return
        try:
            self.folderSelected.emit(json.dumps(self.backend.folder(Path(path), purpose)))
        except urllib.error.HTTPError as exc:
            detail = json.loads(exc.read() or b"{}").get("detail", str(exc))
            self.failed.emit(str(detail))
        except (OSError, ValueError) as exc:
            self.failed.emit(f"Could not use {path}: {exc}")

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
    """Native file drops on the web view.

    It watches the view and the widgets Qt WebEngine adds inside it (drops land on its
    render widget), never the whole application: an application-wide Python event filter
    crashes Qt WebEngine on Linux.
    """

    def __init__(self, view: QWebEngineView, bridge: NativeBridge) -> None:
        super().__init__(view)
        self.view, self.bridge = view, bridge
        self._watch(view)

    def _watch(self, widget: QWidget) -> None:
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ChildAdded:
            child = event.child()  # type: ignore[attr-defined]
            if isinstance(child, QWidget):
                self._watch(child)
            return False
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
    def _title(self, title: str) -> None:
        if title:
            self.setWindowTitle(title)

    def __init__(self, backend: Backend, title: str) -> None:
        super().__init__()
        self.backend = backend
        self.setWindowTitle(f"{title} — Video-Flow")
        self.setWindowIcon(app_icon())
        self.resize(1440, 980)
        self.setMinimumSize(850, 720)
        self.view = QWebEngineView(self)
        self.view.setAcceptDrops(True)
        # No browser menu (reload, copy address, inspect): the page shows its own menus.
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.page = LocalPage(backend.origin, self.view)
        self.view.setPage(self.page)
        # The page title names the open project (Save as, home page, project switches).
        self.view.titleChanged.connect(self._title)
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
  window.videoFlowDesktop = {pickFiles: () => host.pickFiles(), ready: () => host.ready(),
    setZoom: factor => host.setZoom(factor),
    relink: id => host.relink(id), saveRenderedVideo: id => host.saveRenderedVideo(id),
    pickFolder: purpose => host.pickFolder(purpose), quit: () => host.quit()};
  host.folderSelected.connect(value => window.dispatchEvent(
    new CustomEvent('videoflow-folder', {detail: JSON.parse(value)})));
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
        # A native loading screen shows while the backend starts and the page loads; the
        # web view replaces it once the page has loaded (no blank white page).
        self.loading = QLabel("Opening Video-Flow…")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading.setWordWrap(True)
        self.loading.setStyleSheet(
            "QLabel { background: #f7f8f3; color: #4f6b55; font-size: 15px; padding: 40px; }"
        )
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.loading)
        self.stack.addWidget(self.view)
        self.setCentralWidget(self.stack)
        self.view.loadFinished.connect(self._loaded)
        self.waited = time.monotonic()
        self.poll = QTimer(self)
        self.poll.setInterval(10)
        self.poll.timeout.connect(self._await_backend)
        self.poll.start()

    def _await_backend(self) -> None:
        backend = self.backend
        if backend.ready:
            self.poll.stop()
            startup.mark("backend")
            self.view.setUrl(QUrl(backend.origin + "/?token=" + backend.token))
        elif backend.error is not None or (
            backend.thread.ident is not None and not backend.thread.is_alive()
        ):
            self.poll.stop()
            LOG.error("Local backend could not start: %s", backend.error)
            self.loading.setText(f"Video-Flow could not start its local service:\n{backend.error}")
        elif time.monotonic() - self.waited > STARTUP_TIMEOUT:
            self.poll.stop()
            LOG.error("Timed out starting the local backend")
            self.loading.setText("Video-Flow could not start its local service (timed out).")

    def _loaded(self, ok: bool) -> None:
        if self.stack.currentWidget() is self.view:
            return
        startup.mark("page")
        self.stack.setCurrentWidget(self.view)

    def closeEvent(self, event: Any) -> None:
        self.poll.stop()
        self.view.stop()
        self.channel.deregisterObject(self.bridge)
        self.backend.close()
        event.accept()


ICONS = assets_dir() / "icons"
APP_USER_MODEL_ID = "VideoFlow.Desktop"


def app_icon() -> QIcon:
    """The Video-Flow mark for the window and taskbar (assets/icons, see make_icons.py)."""
    icon = QIcon(str(ICONS / "video-flow.ico"))
    icon.addFile(str(ICONS / "video-flow.png"))
    return icon


def group_taskbar_entry() -> None:
    """Give the process its own Windows taskbar identity.

    Without it, a run from source groups under python.exe and shows Python's icon.
    """
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def run_desktop(
    bundle: Bundle,
    *,
    port: int = 0,
    roots: list[Path] | None = None,
    project_open: bool = True,
) -> int:
    if not port:
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
    group_taskbar_entry()
    # The backend thread imports and builds the API while Qt and its window start.
    backend = Backend(bundle, port, roots, project_open)
    backend.start()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Video-Flow")
    app.setOrganizationName("Video-Flow")
    QApplication.setWindowIcon(app_icon())
    app.aboutToQuit.connect(backend.close)
    try:
        window = EditorWindow(backend, bundle.project.name)
        window.show()
        startup.mark("window")
        return int(app.exec())
    finally:
        backend.close()
