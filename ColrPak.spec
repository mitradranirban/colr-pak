
import sys
from importlib.metadata import PackageNotFoundError
from PyInstaller.utils.hooks import collect_all, copy_metadata
# ---------------------------------------------------------------------------
# Fix: Pre-import fontTools circular dependency chain before PyInstaller
# analysis begins. otConverters depends on otTables being initialized first;
# importing them here in the correct order prevents the "partially initialized
# module" error that causes PyInstaller to silently drop fontra_compile.builder.
# ---------------------------------------------------------------------------
import fontTools.ttLib.tables.otTables
import fontTools.ttLib.tables.otConverters

# Update before each release
COLR_PAK_VERSION = "0.4.4"
# UPDATE whenever merging from upstream fontra (see: https://github.com/fontra/fontra/releases)
FONTRA_UPSTREAM_VERSION = "2026.4.1"


def _ver_tuple(version_str):
    """Parse a version string into a 4-integer tuple for Windows VERSIONINFO."""
    parts = version_str.split(".", maxsplit=3)
    y, m, patch = [int(v) for v in parts[:3]]
    return (y, m, patch, 0)


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

    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_ver_tuple(FONTRA_UPSTREAM_VERSION),  # engine/runtime version
            prodvers=_ver_tuple(COLR_PAK_VERSION),         # your product release version
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
                            StringStruct("CompanyName", "Atipra.in"),
                            StringStruct("FileDescription", "Colr Pak"),
                            StringStruct("FileVersion", FONTRA_UPSTREAM_VERSION),
                            StringStruct("InternalName", "Colr Pak"),
                            StringStruct(
                                "LegalCopyright", "© Google LLC, Just van Rossum, ColrPak project"
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
    # --- fontra core ---
    "fontra.__main__",
    "fontra.backends.fontra",
    "fontra.backends.opentype",
    "fontra.backends.workflow",
    "fontra.core.colrv1builder",
    "fontra.core.threading",
    "fontra.workflow.actions.colr",
    "fontra.workflow.command",

    # --- fontra_compile (builder was previously missing entirely) ---
    "fontra_compile",
    "fontra_compile.__main__",
    "fontra_compile.builder",                   # fix: was not listed before
    "fontra_compile.compile_fontc_action",
    "fontra_compile.compile_varc_action",
    "fontra_compile.compile_fontmake_action",

    # --- fontra_glyphs ---
    "fontra_glyphs",
    "fontra_glyphs._version",
    "fontra_glyphs.backend",

    # --- fontra_rcjk ---
    "fontra_rcjk",
    "fontra_rcjk.backend_fs",
    "fontra_rcjk.backend_mysql",
    "fontra_rcjk.client",
    "fontra_rcjk.client_async",
    "fontra_rcjk.projectmanager",

    # --- other packages ---
    "paintcompiler",
    "cffsubr.__main__",
    "openstep_plist.__main__",
    "openstep_plist._test",
    "openstep_plist.util",
    "glyphsLib.data",

    # --- fontTools: explicit hidden imports to survive circular import issue ---
    # otTables must appear before otConverters to mirror the pre-import order above
    "fontTools.ttLib",
    "fontTools.ttLib.ttFont",
    "fontTools.ttLib.sfnt",
    "fontTools.ttLib.woff2",
    "fontTools.ttLib.ttCollection",
    "fontTools.ttLib.tables",
    "fontTools.ttLib.tables.DefaultTable",
    "fontTools.ttLib.tables.otBase",
    "fontTools.ttLib.tables.otTables",          # must be before otConverters
    "fontTools.ttLib.tables.otConverters",      # fix: circular import culprit
    "fontTools.ttLib.tables._c_m_a_p",
    "fontTools.ttLib.tables._k_e_r_n",
    "fontTools.feaLib.builder",
    "fontTools.varLib",
    "fontTools.varLib.instancer",
    "fontTools.varLib.featureVars",
    "fontTools.varLib.cff",
    "fontTools.colorLib.unbuilder",
    "fontTools.fontBuilder",
    "fontTools.otlLib.optimize",
    "fontTools.otlLib.optimize.gpos",
]

# ---------------------------------------------------------------------------
# modules_to_collect_all — fontTools and its dependents must come first so
# the full module graph is resolved before fontra_compile is analysed.
# ---------------------------------------------------------------------------
modules_to_collect_all = [
    "fontTools",        # fix: must be first — resolves dynamic imports for all below
    "fontmake",         # fix: added — imported by fontra_compile.builder
    "ufo2ft",           # fix: added — imported by fontra_compile.builder
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
    ["ColrPakMain.py"],
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
        bundle_identifier="in.atipra.colr-pak",
        version="COLR_PAK_VERSION",
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
