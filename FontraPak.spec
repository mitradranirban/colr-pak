# -*- mode: python ; coding: utf-8 -*-
import sys
from importlib.metadata import PackageNotFoundError
from PyInstaller.utils.hooks import collect_all, copy_metadata
from fontra import __version__ as fontraVersion
COLR_PAK_VERSION = "0.1.2"

def buildWindowsVersionResource():
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringTable,
        StringStruct,
        VarFileInfo,
        VarStruct,
    )

    y, m, patch, *extra = fontraVersion.split(".", maxsplit=3)
    y, m, patch = [int(v) for v in (y, m, patch)]

    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(y, m, patch, 0),
            prodvers=(y, m, patch, 0),
            mask=0x3F,
            flags=0x0,
            OS=0x4,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Fontra.xyz"),
                            StringStruct("FileDescription", "Colr Pak"),
                            StringStruct("FileVersion", fontraVersion),
                            StringStruct("InternalName", "Colr Pak"),
                            StringStruct(
                                "LegalCopyright", "© Google LLC, Just van Rossum"
                            ),
                            StringStruct("OriginalFilename", "Colr Pak.exe"),
                            StringStruct("ProductName", "Colr Pak"),
                            StringStruct("ProductVersion", COLR_PAK_VERSION),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


datas = []
binaries = []
hiddenimports = [
    "paintcompiler",
    "fontra.__main__",
    "fontra.backends.fontra",
    "fontra.backends.opentype",
    "fontra.backends.workflow",
    "fontra.core.colrv1builder",
    "fontra.core.threading",
    "fontra.workflow.actions.colr",
    "fontra.workflow.command",
    "fontra_compile",
    "fontra_compile.__main__",
    "fontra_compile.compile_fontc_action",
    "fontra_compile.compile_varc_action",
    "fontra_glyphs",
    "fontra_glyphs._version",
    "fontra_glyphs.backend",
    "fontra_rcjk",
    "fontra_rcjk.backend_fs",
    "fontra_rcjk.backend_mysql",
    "fontra_rcjk.client",
    "fontra_rcjk.client_async",
    "fontra_rcjk.projectmanager",
    "cffsubr.__main__",
    "openstep_plist.__main__",
    "openstep_plist._test",
    "openstep_plist.util",
    "glyphsLib.data",
]
modules_to_collect_all = [
    "fontra",
    "fontra_compile",
    "fontra_glyphs",
    "fontra_rcjk",
    "cffsubr",
    "openstep_plist",
    "glyphsLib.data",
    "paintcompiler",
]
for module_name in modules_to_collect_all:
    tmp_ret = collect_all(module_name)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]
    try:
        datas += copy_metadata(module_name)
    except PackageNotFoundError:
        print("no metadata for", module_name)


block_cipher = None


a = Analysis(
    ["FontraPakMain.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Colr Pak",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch="universal2",
        codesign_identity=None,
        entitlements_file=None,
        icon="icon/ColrIcon.ico",
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="Colr Pak",
    )
    app = BUNDLE(
        coll,
        name="Colr Pak.app",
        icon="icon/ColrIcon.icns",
        bundle_identifier="xyz.fontra.colr-pak",
        version="0.1.0",
        info_plist={
            "CFBundleDocumentTypes": [
                dict(
                    CFBundleTypeExtensions=[
                        "ttf",
                        "otf",
                        "woff",
                        "woff2",
                        "ttx",
                        "designspace",
                        "ufo",
                        "glyphs",
                        "glyphspackage",
                        "fontra",
                        "rcjk",
                    ],
                    CFBundleTypeRole="Editor",
                ),
            ],
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="Colr Pak" if sys.platform == "win32" else "colrpak",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="icon/ColrIcon.ico",
        version=buildWindowsVersionResource() if sys.platform == "win32" else None,
    )
