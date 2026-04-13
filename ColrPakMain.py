import asyncio
import io
import json
import logging
import multiprocessing
import os
import pathlib
import secrets
import signal
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
from fontra.core.server import FontraServer, findFreeTCPPort
from fontra.core.urlfragment import dumpURLFragment
from fontra.filesystem.projectmanager import FileSystemProjectManager
from fontTools.ttLib.woff2 import compress as woff2Compress
from PyQt6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QSettings,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QWidget,
)

# Update before each release
COLR_PAK_VERSION = "0.4.2"
# UPDATE whenever merge from upstream fontra
FONTRA_UPSTREAM_VERSION = "2026.4.1"

commonCSS = """
border-radius: 20px;
border-style: dashed;
font-size: 18px;
padding: 16px;
"""

neutralCSS = (
    """
background: linear-gradient(135deg, rgba(173, 216, 255, 0.8), rgba(221, 160, 221, 0.8));
border: 5px solid #87CEEB;
"""
    + commonCSS
)

droppingCSS = (
    """
background: linear-gradient(135deg, rgba(255, 255, 255, 0.4), rgba(144, 238, 144, 0.4));
border: 5px solid #32CD32;
"""
    + commonCSS
)

mainText = """
<span style="font-size: 40px;
             color: #4169E1;
             font-weight: bold;
             text-shadow: 2px 2px 4px rgba(135, 206, 235, 0.5);">
Drop font files here
</span>
<br><br>
<span style="color: #FF4500;
             font-weight: bold;
             font-size: 20px;">
Font files are not uploaded but processed locally
</span>
<br><br>
<span style="color: #0097A7;
             font-size: 16px;
             line-height: 1.4;">
COLR Pak is an unofficial fork of Fontra font editor for COLR fonts<br>
It reads and writes .ufo, .designspace for COLR V0 format fonts<br>
and .fontra format for color v1 fonts. It has partial support for reading<br>
and writing .glyphs and .glyphspackage files (without colr data).<br>
Additionally, it can extract color layers and palettes from .ttf file.<br>
Colr fonts can be exported as .otf (v0 only), .ttf and .woff2.
</span>
"""

fileTypes = [
    # name, extension
    ("Fontra", "fontra"),
    ("Designspace", "designspace"),
    ("Unified Font Object", "ufo"),
]

fileTypesMapping = {
    f"{name} (*.{extension})": f".{extension}" for name, extension in fileTypes
}

exportFileTypes = [
    # name, extension
    ("TrueType", "ttf"),
    ("OpenType", "otf"),
    ("Webfont", "woff2"),
] + fileTypes

exportFileTypesMapping = {
    f"{name} (*.{extension})": f".{extension}" for name, extension in exportFileTypes
}

exportExtensionMapping = {v: k for k, v in exportFileTypesMapping.items()}

latestReleasePageURL = "https://github.com/mitradranirban/colr-pak/releases/latest"


def migrateSettings():
    old = QSettings("xyz.fontra", "ColrPak")
    new = QSettings("in.atipra", "ColrPak")

    # Only migrate if old settings exist and new ones don't
    if old.allKeys() and not new.allKeys():
        for key in old.allKeys():
            new.setValue(key, old.value(key))
        old.clear()


migrateSettings()


applicationSettings = QSettings("in.atipra", "ColrPak")


class FontraApplication(QApplication):
    def __init__(self, argv, port):
        self.port = port
        super().__init__(argv)

    def event(self, event):
        """Handle macOS FileOpen events."""
        if event.type() == QEvent.Type.FileOpen:
            openFile(event.file(), self.port)
        else:
            return super().event(event)

        return True


def getFontPath(path, fileType, mapping):
    extension = mapping[fileType]
    if not path.endswith(extension):
        path += extension

    return path


class FontraMainWidget(QMainWindow):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.openProjects = set()
        self.settings = applicationSettings

        self.setWindowTitle("Colr Pak")
        self.resize(720, 480)

        self.resize(applicationSettings.value("size", QSize(720, 480)))
        self.move(applicationSettings.value("pos", QPoint(50, 50)))

        self.setAcceptDrops(True)

        self.label = QLabel(mainText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(neutralCSS)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.label.setWordWrap(True)

        # Helpful: https://www.pythontutorial.net/pyqt/pyqt-qgridlayout/
        layout = QGridLayout()

        button = QPushButton("&New Font...", self)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.clicked.connect(self.newFont)

        buttonDocs = QPushButton("&Documentation", self)
        buttonDocs.setToolTip("Open documentation website")
        buttonDocs.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        buttonDocs.clicked.connect(
            lambda: webbrowser.open("https://fonts.atipra.in/colrpak.html")
        )

        layout.addWidget(button, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(buttonDocs, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.label, 1, 0, 1, 2)

        self.sampleTextBox = QPlainTextEdit(
            applicationSettings.value("editorSampleText", ""), self
        )
        self.sampleTextBox.setFixedHeight(50)
        self.sampleTextBox.setPlaceholderText(
            "Enter some text to launch into the editor view,\n"
            + "or leave empty to launch into the font overview"
        )

        self.sampleTextBox.textChanged.connect(
            lambda: applicationSettings.setValue(
                "editorSampleText", self.sampleTextBox.toPlainText()
            )
        )
        layout.addWidget(QLabel("Sample text:"), 2, 0)
        layout.addWidget(self.sampleTextBox, 3, 0, 1, 2)

        layout.addWidget(
            QLabel(
                f"Colr Pak {COLR_PAK_VERSION} (based on fontra {FONTRA_UPSTREAM_VERSION})"
            ),
            4,
            0,
        )

        if sys.platform in {"darwin", "win32", "linux"}:
            self.downloadButton = QPushButton("Download latest Colr Pak", self)
            self.downloadButton.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            self.downloadButton.clicked.connect(self.goToLatestDownload)
            layout.addWidget(
                self.downloadButton, 4, 1, alignment=Qt.AlignmentFlag.AlignRight
            )
            if "test-startup" not in sys.argv:
                self.checkForUpdate(1500)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.show()

    def closeEvent(self, event):
        if self.openProjects:
            response = showMessageDialog(
                "There are still open fonts, are you sure you want to quit?",
                "Quitting Colr Pak will cause open browser tabs to stop working.",
                buttons=QMessageBox.StandardButton.Close
                | QMessageBox.StandardButton.Cancel,
                defaultButton=QMessageBox.StandardButton.Cancel,
            )
            if response == QMessageBox.StandardButton.Cancel:
                event.ignore()

        applicationSettings.setValue("size", self.size())
        applicationSettings.setValue("pos", self.pos())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.label.setStyleSheet(droppingCSS)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.label.setStyleSheet("background-color: lightgray;")
        self.label.setStyleSheet(neutralCSS)

    def dropEvent(self, event):
        self.label.setStyleSheet(neutralCSS)
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for path in files:
            openFile(path, self.port)
        event.acceptProposedAction()

    @property
    def activeFolder(self):
        activeFolder = self.settings.value("activeFolder", os.path.expanduser("~"))
        if not os.path.isdir(activeFolder):
            activeFolder = os.path.expanduser("~")
        return activeFolder

    def newFont(self):
        fontPath, fileType = QFileDialog.getSaveFileName(
            self,
            "New Font...",
            os.path.join(self.activeFolder, "Untitled"),
            ";;".join(fileTypesMapping),
        )

        if not fontPath:
            # User cancelled
            return

        fontPath = getFontPath(fontPath, fileType, fileTypesMapping)

        self.settings.setValue("activeFolder", os.path.dirname(fontPath))

        # Create a new empty project on disk
        try:
            asyncio.run(createNewFont(fontPath))
        except Exception as e:
            showMessageDialog("The new font could not be saved", repr(e))
            return

        if os.path.exists(fontPath):
            openFile(fontPath, self.port)

    def messageFromServer(self, item):
        action, arguments = item
        handler = getattr(self, action, None)
        if handler is not None:
            handler(*arguments)
        else:
            print("unknown server action:", action)

    def exportAs(self, path, options):
        sourcePath = pathlib.Path(path)
        fileExtension = options["format"]

        wFlags = self.windowFlags()
        self.setWindowFlags(wFlags | Qt.WindowType.WindowStaysOnTopHint)
        self.show()
        self.setWindowFlags(wFlags)
        self.show()

        destPath, fileType = QFileDialog.getSaveFileName(
            self,
            "Export font...",
            os.path.join(self.activeFolder, sourcePath.stem),
            exportExtensionMapping["." + fileExtension],
        )

        if not destPath:
            # User cancelled
            return

        destPath = getFontPath(destPath, fileType, exportFileTypesMapping)

        self.settings.setValue("activeFolder", os.path.dirname(destPath))

        destPath = pathlib.Path(destPath)

        if sourcePath == destPath:
            showMessageDialog(
                "Cannot export font",
                "The destination file cannot be the same as the source file",
            )
            return

        self.doExportAs(sourcePath, destPath, fileExtension)

    def doExportAs(self, sourcePath, destPath, fileExtension):
        logFilePath = tempfile.NamedTemporaryFile(delete=False).name
        sourceExt = sourcePath.suffix.lower()

        # .fontra sources cannot export to OTF — COLRv1 requires TTF (glyf) outlines.
        # CFF2 is incompatible with COLR/CPAL tables per the OpenType spec.
        if sourceExt == ".fontra" and fileExtension == "otf":
            QMessageBox.warning(
                self,
                "Export Not Supported",
                "Cannot export .fontra sources as OTF.\n\n"
                "COLRv1 fonts require TrueType (glyf) outlines, which are "
                "incompatible with the CFF2 format used by OTF.\n\n"
                "Please export as TTF or WOFF2 instead.",
            )
            return

        isfontrattfotf = sourceExt == ".fontra" and fileExtension in (
            "ttf",
            "woff2",
        )

        if isfontrattfotf:
            exportProcess = multiprocessing.Process(
                target=exportFontToPathCompile,
                args=(sourcePath, destPath, logFilePath),
            )
            progressText = "Compiling with fontra-compile (COLR included)"
        else:
            exportProcess = multiprocessing.Process(
                target=exportFontToPath,
                args=(sourcePath, destPath, fileExtension, logFilePath),
            )
            progressText = f"Exporting via workflow {fileExtension}"

        cancelled = False

        def cancelExport():
            nonlocal cancelled
            cancelled = True
            try:
                os.kill(exportProcess.pid, signal.SIGINT)
            except (ProcessLookupError, OSError):
                pass

        progressDialog = QProgressDialog(progressText, "Cancel", 0, 0)
        progressCancelButton = QPushButton("Cancel")
        progressCancelButton.clicked.connect(cancelExport)
        progressDialog.setCancelButton(progressCancelButton)
        progressDialog.setWindowTitle(f"Export as {fileExtension}")
        progressDialog.show()
        exportProcess.start()

        def exportFinished():
            if cancelled:
                return
            progressDialog.cancel()
            try:
                if exportProcess.exitcode:
                    with open(logFilePath, "r", encoding="utf-8") as f:
                        logData = f.read()
                    logLines = logData.splitlines()
                    infoText = logLines[-1] if logLines else "Unknown error"
                    showMessageDialog("Export failed", infoText, detailedText=logData)
                elif isfontrattfotf:
                    showMessageDialog(
                        "Success!",
                        "COLR/CPAL tables included.",
                        icon=QMessageBox.Icon.Information,
                    )
            finally:
                try:
                    os.unlink(logFilePath)
                except OSError:
                    pass

        def exportProcessJoin():
            exportProcess.join()
            callInMainThread(exportFinished)

        callInNewThread(exportProcessJoin)

    def projectOpened(self, projectIdentifier):
        self.openProjects.add(projectIdentifier)

    def projectClosed(self, projectIdentifier):
        self.openProjects.discard(projectIdentifier)

    def checkForUpdate(self, msDelay):
        QTimer.singleShot(msDelay, lambda: callInNewThread(self._checkForUpdate))

    def _checkForUpdate(self):
        if "dev" in COLR_PAK_VERSION:
            return

        print(f"Checking for update on {datetime.now()}")

        latestVersion, downloadURL = fetchLatestReleaseInfo()

        if downloadURL is not None and latestVersion != COLR_PAK_VERSION:
            callInMainThread(
                self.downloadButton.setText, "‼️ A new version is available ‼️"
            )
        else:
            # Try again in a bit more than a day
            hours = 24 + 4 * random()
            minutes = hours * 60
            seconds = minutes * 60
            msDelay = seconds * 1000
            callInMainThread(self.checkForUpdate, int(msDelay))

    def goToLatestDownload(self):
        _, downloadURL = fetchLatestReleaseInfo()

        if downloadURL is None:
            downloadURL = latestReleasePageURL

        webbrowser.open(downloadURL)


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


# Upstream-compatible generic export (all formats except fontra→ttf/otf via compile)
def exportFontToPath(sourcePath, destPath, fileExtension, logFilePath):
    logFile = open(logFilePath, "w")
    sys.stdout = sys.stderr = logFile
    try:
        asyncio.run(exportFontToPathAsync(sourcePath, destPath, fileExtension))
    finally:
        logFile.flush()


# Colr Pak addition: fontra-compile path for .fontra → .ttf/.otf with COLR tables


def exportFontToPathCompile(sourcePath, destPath, logFilePath):
    try:
        # Import the entry point function from the bundled module
        from fontra_compile.__main__ import main as compile_main

        # Buffers to mimic subprocess capture_output=True
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Save original state
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_argv = sys.argv
        original_cwd = os.getcwd()

        returncode = 0

        try:
            # Redirect stdout/stderr to our buffers
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

            # Mock the CLI arguments
            sys.argv = ["fontra-compile", str(sourcePath), str(destPath)]

            # Mimic cwd=sourcePath.parent
            os.chdir(sourcePath.parent)

            # Execute the packed compiler natively
            compile_main()

        except SystemExit as exit_exc:
            # Capture the return code if the compiler calls sys.exit()
            if exit_exc.code is not None:
                returncode = exit_exc.code if isinstance(exit_exc.code, int) else 1
        except Exception:
            # If the compiler crashes without sys.exit, log it and set RC 1
            traceback.print_exc()
            returncode = 1
        finally:
            # Restore the environment completely
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            sys.argv = original_argv
            os.chdir(original_cwd)

        # Write the log file exactly as the original subprocess did
        with open(logFilePath, "w", encoding="utf-8") as f:
            f.write(
                f"STDOUT\n{stdout_capture.getvalue()}\n"
                f"STDERR\n{stderr_capture.getvalue()}\n"
                f"RC {returncode}"
            )

        sys.exit(returncode)

    except Exception as e:
        # Catch any catastrophic setup failures
        with open(logFilePath, "w", encoding="utf-8") as f:
            f.write(f"Exception {e}\n{traceback.format_exc()}")
        sys.exit(1)


# exportFontToPathAsync modified to remove drop-unreachable-glyphs filter


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

        # For now, we drop discrete axes, and only export the default
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
    # Create a new empty project on disk
    destBackend = newFileSystemBackend(fontPath)
    await populateBackend(destBackend)
    await destBackend.aclose()


def openFile(path, port):
    path = pathlib.Path(path).resolve()
    assert path.is_absolute()
    parts = list(path.parts)
    if not path.drive:
        assert parts[0] == "/"
        del parts[0]
    path = "/".join(quote(part, safe="") for part in parts)

    sampleText = applicationSettings.value("editorSampleText", "")
    urlFragment = dumpURLFragment({"text": sampleText}) if sampleText else ""
    view = "editor" if sampleText else "fontoverview"

    webbrowser.open(f"http://localhost:{port}/{view}.html?project={path}{urlFragment}")


def showMessageDialog(
    message,
    infoText,
    detailedText=None,
    icon=QMessageBox.Icon.Warning,
    buttons=None,
    defaultButton=None,
):
    dialog = QMessageBox()
    if icon is not None:
        dialog.setIcon(icon)
    dialog.setText(message)
    dialog.setInformativeText(infoText)
    if detailedText is not None:
        dialog.setStyleSheet("QTextEdit { font-weight: regular; }")
        dialog.setDetailedText(detailedText)
    if buttons is not None:
        dialog.setStandardButtons(buttons)
    if defaultButton is not None:
        dialog.setDefaultButton(defaultButton)
        # FIXME: The following does *not* make "escape" equivalent to the default button
        dialog.setEscapeButton(defaultButton)

    return dialog.exec()


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


def runFontraServer(host, port, queue):
    logging.basicConfig(
        format="%(asctime)s %(name)-17s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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
    server.run(showLaunchBanner=False)


class CallInMainThreadScheduler(QObject):
    signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.signal.connect(self.receive)
        self.items = {}

    def receive(self, identifier):
        assert threading.current_thread() is threading.main_thread()
        function, args, kwargs = self.items.pop(identifier)
        function(*args, **kwargs)

    def schedule(self, function, args, kwargs):
        identifier = secrets.token_hex(4)
        self.items[identifier] = function, args, kwargs
        self.signal.emit(identifier)


_callInMainThreadScheduler = CallInMainThreadScheduler()


def callInMainThread(function, *args, **kwargs):
    _callInMainThreadScheduler.schedule(function, args, kwargs)


def callInNewThread(function, *args, **kwargs):
    thread = threading.Thread(target=function, args=args, kwargs=kwargs)
    thread.start()
    return thread


def queueGetter(queue, callback):
    while True:
        item = queue.get()
        if item is None:
            break

        callInMainThread(callback, item)


def main():
    queue = multiprocessing.Queue()
    host = "localhost"
    port = findFreeTCPPort(host=host)
    serverProcess = multiprocessing.Process(
        target=runFontraServer, args=(host, port, queue)
    )
    serverProcess.start()

    app = FontraApplication(sys.argv, port)

    def cleanup():
        queue.put(None)
        thread.join()
        process = psutil.Process(serverProcess.pid)
        for p in [process] + process.children(recursive=True):
            if sys.platform != "win32":
                p.send_signal(psutil.signal.SIGINT)
            else:
                p.terminate()

    app.aboutToQuit.connect(cleanup)

    mainWindow = FontraMainWidget(port)

    thread = callInNewThread(queueGetter, queue, mainWindow.messageFromServer)

    mainWindow.show()

    if "test-startup" in sys.argv:

        def delayedQuit():
            print("test-startup")
            app.quit()

        QTimer.singleShot(1500, delayedQuit)

    sys.exit(app.exec())


if __name__ == "__main__":
    # 1. Intercepts PyInstaller background workers
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass
    main()
