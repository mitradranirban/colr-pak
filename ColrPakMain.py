import asyncio
import configparser
import io
import json
import logging
import multiprocessing
import os
import pathlib
import secrets
import socket
import sys
import tempfile
import threading
import traceback
import webbrowser
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from random import random
from urllib.parse import quote
from urllib.request import urlopen

import psutil
from fontra.backends import getFileSystemBackend, newFileSystemBackend
from fontra.backends.copy import copyFont
from fontra.backends.populate import populateBackend
from fontra.core.classes import DiscreteFontAxis
from fontra.core.server import FontraServer
from fontra.core.urlfragment import dumpURLFragment
from fontra.filesystem.projectmanager import FileSystemProjectManager
from fontTools.ttLib.woff2 import compress as woff2Compress
from platformdirs import user_config_dir
from webview.dom import DOMEventHandler

# ---------------------------------------------------------------------------
# Version — update before each release
# ---------------------------------------------------------------------------
COLR_PAK_VERSION = "0.4.4"
FONTRA_UPSTREAM_VERSION = "2026.4.1"
latestReleasePageURL = "https://github.com/mitradranirban/colr-pak/releases/latest"

# Force target="_blank" and window.open to open inside the app!

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
_config_path = pathlib.Path(user_config_dir("ColrPak", "in.atipra")) / "settings.ini"
_config_path.parent.mkdir(parents=True, exist_ok=True)
applicationSettings = configparser.ConfigParser()
applicationSettings.read(_config_path)
if "colrpak" not in applicationSettings:
    applicationSettings["colrpak"] = {}


def saveSetting(key, value):
    applicationSettings["colrpak"][key] = str(value)
    with open(_config_path, "w") as f:
        applicationSettings.write(f)


def getSetting(key, default=""):
    return applicationSettings["colrpak"].get(key, default)


# ---------------------------------------------------------------------------
# Port reservation — bind N sockets simultaneously for distinct free ports
# ---------------------------------------------------------------------------
def reservePorts(n, host="localhost"):
    sockets = []
    ports = []
    try:
        for _ in range(n):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, 0))
            sockets.append(s)
            ports.append(s.getsockname()[1])
    finally:
        for s in sockets:
            s.close()
    return ports


# ---------------------------------------------------------------------------
# File types
# ---------------------------------------------------------------------------
fileTypes = [
    ("Fontra", "fontra"),
    ("Designspace", "designspace"),
    ("Unified Font Object", "ufo"),
]
fileTypesMapping = {
    f"{name} (*.{extension})": f".{extension}" for name, extension in fileTypes
}
exportFileTypes = [
    ("TrueType", "ttf"),
    ("OpenType", "otf"),
    ("Webfont", "woff2"),
] + fileTypes
exportFileTypesMapping = {
    f"{name} (*.{extension})": f".{extension}" for name, extension in exportFileTypes
}
exportExtensionMapping = {v: k for k, v in exportFileTypesMapping.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def getFontPath(path, fileType, mapping):
    extension = mapping[fileType]
    if not path.endswith(extension):
        path += extension
    return path


def openFile(path, port):
    import webview

    path = pathlib.Path(path).resolve()
    assert path.is_absolute()
    parts = list(path.parts)
    if not path.drive:
        assert parts[0] == "/"
        del parts[0]

    # NO leading slash — matches original fontra-pak behavior!
    path_str = "/".join(quote(part, safe="") for part in parts)

    sampleText = getSetting("editorSampleText", "")
    urlFragment = dumpURLFragment({"text": sampleText}) if sampleText else ""
    view = "editor" if sampleText else "fontoverview"
    url = f"http://localhost:{port}/{view}.html?project={path_str}{urlFragment}"

    screen = webview.screens[0] if webview.screens else None
    if screen:
        width = max(1000, min(1280, int(screen.width * 0.9)))
        height = max(700, min(900, int(screen.height * 0.88)))
        x = screen.x + max(0, (screen.width - width) // 2)
        y = screen.y + max(0, (screen.height - height) // 2)
    else:
        width, height, x, y = 1200, 820, None, None

    webview.create_window(
        f"ColrPak — {pathlib.Path(path).name}",
        url,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=(900, 650),
    )


# ---------------------------------------------------------------------------
# Export / project listener dataclasses
# ---------------------------------------------------------------------------
@dataclass
class FontraPakExportManager:
    appQueue: multiprocessing.Queue

    def getSupportedExportFormats(self):
        return [typ for (_name, typ) in exportFileTypes]

    async def exportAs(self, projectIdentifier, options):
        self.appQueue.put(("exportAs", (projectIdentifier, options)))


@dataclass
class ProjectOpenListener:
    appQueue: multiprocessing.Queue

    def projectOpened(self, projectIdentifier: str) -> None:
        self.appQueue.put(("projectOpened", (projectIdentifier,)))

    def projectClosed(self, projectIdentifier: str) -> None:
        self.appQueue.put(("projectClosed", (projectIdentifier,)))


# ---------------------------------------------------------------------------
# Fontra server — runs in a subprocess; NO pywebview import here.
# Port is pre-allocated by parent via reservePorts() to avoid races.
# Signals readiness via queue before blocking on server.run().
# ---------------------------------------------------------------------------
def runFontraServer(host, port, queue):
    logging.basicConfig(
        format="%(asctime)s %(name)-17s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Must be None — exactly as in the original PyQt6 version!
    projectManager = FileSystemProjectManager(
        None,
        exportManager=FontraPakExportManager(queue),
        projectOpenListener=ProjectOpenListener(queue),
    )

    server = FontraServer(
        host=host,
        httpPort=port,
        projectManager=projectManager,
        versionToken=secrets.token_hex(4),
    )
    server.setup()
    queue.put(("server_ready", ()))
    server.run(showLaunchBanner=False)


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------
def exportFontToPath(sourcePath, destPath, fileExtension, logFilePath):
    logFile = open(logFilePath, "w")
    sys.stdout = sys.stderr = logFile
    try:
        asyncio.run(exportFontToPathAsync(sourcePath, destPath, fileExtension))
    finally:
        logFile.flush()


def exportFontToPathCompile(sourcePath, destPath, logFilePath):
    try:
        from fontra_compile.__main__ import main as compile_main

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_argv = sys.argv
        original_cwd = os.getcwd()
        returncode = 0
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            sys.argv = ["fontra-compile", str(sourcePath), str(destPath)]
            os.chdir(sourcePath.parent)
            compile_main()
        except SystemExit as exit_exc:
            if exit_exc.code is not None:
                returncode = exit_exc.code if isinstance(exit_exc.code, int) else 1
        except Exception:
            traceback.print_exc()
            returncode = 1
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            sys.argv = original_argv
            os.chdir(original_cwd)

        with open(logFilePath, "w", encoding="utf-8") as f:
            f.write(
                f"STDOUT\n{stdout_capture.getvalue()}\n"
                f"STDERR\n{stderr_capture.getvalue()}\n"
                f"RC {returncode}"
            )
        sys.exit(returncode)
    except Exception as e:
        with open(logFilePath, "w", encoding="utf-8") as f:
            f.write(f"Exception {e}\n{traceback.format_exc()}")
        sys.exit(1)


async def exportFontToPathAsync(sourcePath, destPath, fileExtension):
    sourcePath = pathlib.Path(sourcePath)
    destPath = pathlib.Path(destPath)
    if fileExtension == "woff2":
        with tempfile.TemporaryDirectory() as tmpDir:
            tmpTtfPath = pathlib.Path(tmpDir) / (destPath.stem + ".ttf")
            await exportFontToPathAsync(sourcePath, tmpTtfPath, "ttf")
            woff2Compress(str(tmpTtfPath), str(destPath))
        return
    sourceBackend = getFileSystemBackend(sourcePath)
    if fileExtension in {"ttf", "otf"}:
        from fontra.workflow.workflow import Workflow

        continueOnError = False
        axes = await sourceBackend.getAxes()
        discreteAxisNames = [
            axis.name for axis in axes.axes if isinstance(axis, DiscreteFontAxis)
        ]
        dropDiscreteAxes = (
            [dict(filter="subset-axes", dropAxisNames=discreteAxisNames)]
            if discreteAxisNames
            else []
        )
        config = dict(
            steps=dropDiscreteAxes
            + [
                dict(filter="decompose-composites", onlyVariableComposites=True),
                dict(filter="propagate-anchors"),
                dict(
                    output="compile-fontmake",
                    destination=destPath.name,
                    options={"verbose": "DEBUG", "overlaps-backend": "pathops"},
                ),
            ]
        )
        workflow = Workflow(config=config, parentDir=sourcePath.parent)
        async with workflow.endPoints(sourceBackend) as endPoints:
            assert endPoints.endPoint is not None
            for output in endPoints.outputs:
                await output.process(destPath.parent, continueOnError=continueOnError)
    else:
        destBackend = newFileSystemBackend(destPath)
        async with aclosing(sourceBackend), aclosing(destBackend):
            await copyFont(sourceBackend, destBackend)


async def createNewFont(fontPath):
    destBackend = newFileSystemBackend(fontPath)
    await populateBackend(destBackend)
    await destBackend.aclose()


# ---------------------------------------------------------------------------
# Update helpers
# ---------------------------------------------------------------------------
def fetchLatestReleaseInfo() -> tuple[str, str | None]:
    try:
        return _fetchLatestReleaseInfo()
    except Exception:
        print("Failed to fetch release info")
        traceback.print_exc()
    return "0.0.0", None


def _fetchLatestReleaseInfo() -> tuple[str, str | None]:
    url = "https://api.github.com/repos/mitradranirban/colr-pak/releases/latest"
    response = urlopen(url)
    latestRelease = json.loads(response.read().decode("utf-8"))
    latestVersion = latestRelease["tag_name"]
    assetNamePart = None
    match sys.platform:
        case "darwin":
            assetNamePart = "MacOS"
        case "win32":
            assetNamePart = "Windows"
    if assetNamePart is None:
        return latestVersion, None
    [assetInfo] = [
        asset for asset in latestRelease["assets"] if assetNamePart in asset["name"]
    ]
    return latestVersion, assetInfo["browser_download_url"]


# ---------------------------------------------------------------------------
# Queue handler thread — receives messages from the server subprocess
# ---------------------------------------------------------------------------
def queueHandler(queue, window, openProjects):
    while True:
        item = queue.get()
        if item is None:
            break
        action, arguments = item
        if action == "server_ready":
            pass  # already handled in main()
        elif action == "exportAs":
            _projectIdentifier, _options = arguments
            window.evaluate_js("window.colrpak && window.colrpak.showExportDialog()")
        elif action == "projectOpened":
            openProjects.add(arguments[0])
        elif action == "projectClosed":
            openProjects.discard(arguments[0])


# ---------------------------------------------------------------------------
# pywebview API — exposed to JS as window.pywebview.api.*
# ---------------------------------------------------------------------------
class ColrPakAPI:
    """All methods callable from the frontend via window.pywebview.api.*"""

    def __init__(self, port, queue):
        self._port = port
        self._queue = queue
        self._window = None

    def _set_window(self, window):
        self._window = window

    # -- Font opening ---------------------------------------------------------

    def new_font(self):
        def _run():
            from webview import FileDialog

            result = self._window.create_file_dialog(
                FileDialog.SAVE,
                save_filename="Untitled",
                file_types=(
                    "Fontra (*.fontra)",
                    "Designspace (*.designspace)",
                    "Unified Font Object (*.ufo)",
                ),
            )
            if result:
                font_path = result if isinstance(result, str) else result[0]
                if not any(
                    font_path.endswith(ext)
                    for ext in [".fontra", ".designspace", ".ufo"]
                ):
                    font_path += ".fontra"
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(createNewFont(font_path))
                    loop.close()
                    openFile(font_path, self._port)
                except Exception as e:
                    self._window.evaluate_js(
                        f"alert('The new font could not be saved:\\n{e}')"
                    )

        threading.Thread(target=_run, daemon=True).start()

    def open_font_path(self, path):
        """Called from drag-and-drop in the launcher HTML."""
        openFile(path, self._port)

    def open_internal_link(self, url):
        """Called from injected JS to safely open Fontra links in a new window."""
        import webview

        if url.startswith("/") or url.startswith("#") or url.startswith("editor.html"):
            url = f"http://localhost:{self._port}/{url.lstrip('/')}"

        webview.create_window(
            "ColrPak Editor", url, width=1280, height=900, min_size=(900, 650)
        )

    # -- Settings -------------------------------------------------------------

    def get_sample_text(self):
        return getSetting("editorSampleText", "")

    def set_sample_text(self, text):
        saveSetting("editorSampleText", text)

    def get_active_folder(self):
        folder = getSetting("activeFolder", os.path.expanduser("~"))
        if not os.path.isdir(folder):
            folder = os.path.expanduser("~")
        return folder

    def set_active_folder(self, folder):
        saveSetting("activeFolder", folder)

    # -- Info -----------------------------------------------------------------

    def get_version(self):
        return {"colrpak": COLR_PAK_VERSION, "fontra": FONTRA_UPSTREAM_VERSION}

    def check_for_update(self):
        try:
            latestVersion, downloadURL = _fetchLatestReleaseInfo()
            return {"version": latestVersion, "url": downloadURL}
        except Exception:
            return {"version": None, "url": None}

    def go_to_latest_download(self):
        _, downloadURL = fetchLatestReleaseInfo()
        webbrowser.open(downloadURL or latestReleasePageURL)

    def open_docs(self):
        webbrowser.open("https://fonts.atipra.in/colrpak.html")


# ---------------------------------------------------------------------------
# Main — pywebview imported HERE only, never at module level.
# Subprocesses (spawn mode) re-import this module and must NOT init GUI.
# ---------------------------------------------------------------------------


def main():
    import webview

    host = "localhost"
    queue = multiprocessing.Queue()

    [fontra_port] = reservePorts(1, host)
    serverProcess = multiprocessing.Process(
        target=runFontraServer, args=(host, fontra_port, queue)
    )
    serverProcess.start()

    print("[ColrPak] Waiting for Fontra server to start…")
    pending = []
    while True:
        item = queue.get()
        action, arguments = item
        if action == "server_ready":
            print(f"[ColrPak] Fontra server ready on port {fontra_port}")
            break
        pending.append(item)
    for item in pending:
        queue.put(item)

    openProjects = set()
    api = ColrPakAPI(fontra_port, queue)
    storage_path = str(
        pathlib.Path(user_config_dir("ColrPak", "in.atipra")) / "webview-data"
    )

    window = webview.create_window(
        "ColrPak",
        html=_launcherHTML(),
        js_api=api,
        width=720,
        height=480,
        min_size=(600, 400),
        resizable=True,
    )
    api._set_window(window)

    threading.Thread(
        target=queueHandler,
        args=(queue, window, openProjects),
        daemon=True,
    ).start()

    def on_closed():
        queue.put(None)
        try:
            process = psutil.Process(serverProcess.pid)
            for p in [process, *process.children(recursive=True)]:
                try:
                    if sys.platform != "win32":
                        p.send_signal(psutil.signal.SIGINT)
                    else:
                        p.terminate()
                except (psutil.NoSuchProcess, ProcessLookupError):
                    pass
        except psutil.NoSuchProcess:
            pass

    window.events.closed += on_closed

    # --- THE NATIVE PYWEBVIEW 6 DRAG AND DROP HANDLERS ---
    def on_drag(e):
        pass  # Required to prevent browser default behavior

    def on_drop(e):
        # pywebview 6 securely injects the real absolute path here
        files = e.get("dataTransfer", {}).get("files", [])
        for file in files:
            full_path = file.get("pywebviewFullPath")
            if full_path:
                api.open_font_path(full_path)

    # This MUST be called directly by webview.start() to hook the DOM safely
    def bind_events(win):
        # Update check can go here
        threading.Timer(1.5, _checkForUpdate, args=(win,)).start()

        # --- JS INJECTION TO INTERCEPT FONTRA'S window.open ---
        def inject_window_open_override():
            js_code = """
            (function() {
                const _origOpen = window.open;
                window.open = function(url, target, features) {
                    // Intercept Fontra's internal URL calls
                    let isInternal = url && (
                        url.includes('localhost') ||
                        url.includes('127.0.0.1') ||
                        url.startsWith('editor.html') ||
                        url.startsWith('/') ||
                        url.startsWith('#')
                    );

                    if (isInternal) {
                        window.pywebview.api.open_internal_link(url);
                        return null; // Stop the browser from opening Chrome
                    }
                    // Let external links go to the system browser
                    return _origOpen.call(window, url, target, features);
                };

                // Also intercept standard <a> tag clicks with target="_blank"
                document.addEventListener('click', function(e) {
                    let a = e.target.closest('a');
                    if (a && a.getAttribute('target') === '_blank') {
                        let href = a.getAttribute('href');
                        let isInternal = href && (
                            href.includes('localhost') ||
                            href.includes('127.0.0.1') ||
                            href.startsWith('editor.html') ||
                            href.startsWith('/') ||
                            href.startsWith('#')
                        );

                        if (isInternal) {
                            e.preventDefault();
                            e.stopPropagation();
                            window.pywebview.api.open_internal_link(href);
                        }
                    }
                }, true);
            })();
            """
            try:
                win.evaluate_js(js_code)
            except Exception as e:
                print(f"Failed to inject window.open override: {e}")

        # Inject the script as soon as the DOM is loaded
        win.events.loaded += inject_window_open_override

        try:
            # Bind globally to the document
            doc_events = win.dom.document.events
            doc_events.dragenter += DOMEventHandler(on_drag, True, True)
            doc_events.dragstart += DOMEventHandler(on_drag, True, True)
            doc_events.dragover += DOMEventHandler(on_drag, True, True, debounce=500)
            doc_events.drop += DOMEventHandler(on_drop, True, True)
        except Exception as err:
            print(f"Failed to bind pywebview native drop events: {err}")

    # Pass 'bind_events' as the first argument, and 'window' as the second
    webview.start(
        bind_events,
        window,
        debug="--debug" in sys.argv,
        gui="qt",
        private_mode=False,
        storage_path=storage_path,
    )


# ---------------------------------------------------------------------------
# Launcher HTML
# ---------------------------------------------------------------------------
def _launcherHTML():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ColrPak</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, sans-serif;
    background: #f0f4f8;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .toolbar {
    display: flex;
    gap: 8px;
    padding: 10px 14px;
    background: #fff;
    border-bottom: 1px solid #dde3ea;
    align-items: center;
  }
  .toolbar button {
    padding: 6px 14px;
    border: 1px solid #c0cad6;
    border-radius: 6px;
    background: #f7f9fc;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.15s;
  }
  .toolbar button:hover { background: #e8edf3; }
  .toolbar .spacer { flex: 1; }
  .toolbar .version { font-size: 11px; color: #8a96a3; }
  .drop-zone {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin: 16px;
    border: 3px dashed #87CEEB;
    border-radius: 20px;
    background: linear-gradient(135deg, rgba(173,216,255,0.5), rgba(221,160,221,0.5));
    transition: background 0.2s, border-color 0.2s;
    padding: 24px;
    text-align: center;
  }
  .drop-zone.over {
    background: linear-gradient(135deg, rgba(255,255,255,0.4), rgba(144,238,144,0.4));
    border-color: #32CD32;
  }
  .drop-icon { font-size: 48px; margin-bottom: 12px; }
  .drop-title { font-size: 28px; font-weight: bold; color: #4169E1; margin-bottom: 8px; }
  .drop-sub { font-size: 13px; color: #c0392b; font-weight: bold; margin-bottom: 12px; }
  .drop-desc { font-size: 13px; color: #2c7873; line-height: 1.6; max-width: 480px; }
  .sample-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    background: #fff;
    border-top: 1px solid #dde3ea;
    font-size: 13px;
  }
  .sample-row label { color: #555; white-space: nowrap; }
  .sample-row input {
    flex: 1;
    padding: 5px 10px;
    border: 1px solid #c0cad6;
    border-radius: 6px;
    font-size: 13px;
  }
  #update-btn {
    display: none;
    padding: 5px 12px;
    background: #e74c3c;
    color: #fff;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-weight: bold;
  }
</style>
</head>
<body>
<div class="toolbar">
  <button id="btn-new-font">&#43; New Font&hellip;</button>
  <button id="btn-docs">Documentation</button>
  <span class="spacer"></span>
  <button id="update-btn">Update Colr</button>
  <span class="version">ColrPak __COLRPAK_VERSION__ , based on fontra __FONTRA_VERSION__</span>
</div>

<div class="drop-zone" id="dropZone">
  <div class="drop-icon">🎨</div>
  <div class="drop-title">Drop font files here</div>
  <div class="drop-sub">Font files are not uploaded but processed locally</div>
  <div class="drop-desc">
    COLR Pak is an unofficial fork of Fontra font editor for COLR fonts.<br>
    Reads &amp; writes .ufo, .designspace (COLR V0) and .fontra (COLRv1).<br>
    Partial support for .glyphs/.glyphspackage. Exports .otf (v0), .ttf, .woff2.
  </div>
</div>

<div class="sample-row">
  <label>Sample text:</label>
  <input type="text" id="sampleText"
    placeholder="Enter text to open in editor view, or leave empty for font overview">
</div>

<script>
function setupBridge() {
  document.getElementById('btn-new-font').onclick  = () => pywebview.api.new_font();
  document.getElementById('btn-docs').onclick      = () => pywebview.api.open_docs();
  document.getElementById('update-btn').onclick    = () => pywebview.api.go_to_latest_download();

  pywebview.api.get_sample_text().then(t => {
    document.getElementById('sampleText').value = t;
  });

  document.getElementById('sampleText').addEventListener('input', e => {
    pywebview.api.set_sample_text(e.target.value);
  });

  setTimeout(() => {
    pywebview.api.check_for_update().then(r => {
      if (r && r.version && r.url) {
        const btn = document.getElementById('update-btn');
        btn.textContent = '!! New version ' + r.version + ' available';
        btn.style.display = 'inline-block';
      }
    });
  }, 2000);
}

if (window.pywebview) {
  setupBridge();
} else {
  window.addEventListener('pywebviewready', setupBridge);
}
</script>
</body>
</html>"""
    html = html.replace("__COLRPAK_VERSION__", COLR_PAK_VERSION)
    html = html.replace("__FONTRA_VERSION__", FONTRA_UPSTREAM_VERSION)
    return html


# ---------------------------------------------------------------------------
# Background update check
# ---------------------------------------------------------------------------
def _checkForUpdate(window):
    if "dev" in COLR_PAK_VERSION:
        return
    print(f"Checking for update on {datetime.now()}")
    latestVersion, downloadURL = fetchLatestReleaseInfo()
    if downloadURL and latestVersion != COLR_PAK_VERSION:
        window.evaluate_js(
            f"""
            var btn = document.getElementById('update-btn');
            if (btn) {{
                btn.textContent = '!! New version {latestVersion} available';
                btn.style.display = 'inline-block';
            }}
            """
        )
    else:
        delay = (24 + 4 * random()) * 3600
        threading.Timer(delay, _checkForUpdate, args=(window,)).start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass
    main()
