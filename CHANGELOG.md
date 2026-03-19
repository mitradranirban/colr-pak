# Changelog

All notable changes to Colr Pak and its components are documented here.
Colr Pak is a fork of [Fontra Pak](https://github.com/fontra/fontra-pak),
built on [Fontra](https://github.com/fontra/fontra) and
[fontra-compile](https://github.com/fontra/fontra-compile).

---
## [v0.2.2] - 2026-03-19
**fontra_compile fix** : COLRv1 multi-source variation VarStore population

- Correct _merge_scalar to return proper {location: value} dicts for paintcompiler
- Build normalized VariationModel for paint merging (not glyph outline model)
- Key format ((tag, loc),) so dict(key) → {tag: loc} works correctly
- paintcompiler.make_var_scalar now receives absolute values at normalized locations
- Produces Format=5 PaintVarLinearGradient + populated VarStore.RegionCount=1
- pass userSpaceLocs to merge_paint_sources to fix VariationModel crash on fontTools ≥ 4.62.1

Exports working variable COLR TTF.

## [v0.2.1] — 2026-03-18
### Fixed

- **COLRv1 variable font compilation failure** — ModuleNotFoundError: No module named 'fontra_compile' at runtime caused by PyInstaller silently dropping fontra_compile.builder from the bundle
- **Root cause**  — fontTools.ttLib.tables.otConverters has a circular dependency on otTables; when PyInstaller imported otConverters in isolation during static analysis the partial initialisation failure caused the entire fontra_compile package to be excluded
- Fix 1 — Added pre-import of fontTools.ttLib.tables.otTables before otConverters at the top of FontraPak.spec to resolve the circular import before analysis begins
- Fix 2 — Added fontTools, fontmake, ufo2ft to modules_to_collect_all so the full module graph is resolved before fontra_compile is analysed
- Fix 3 — Added fontra_compile.builder and key fontTools.ttLib submodules explicitly to hiddenimports as a secondary safeguard

### Verified

COLRv1 variable font compiles and renders correctly with colour palette and variable axes intact

## [v0.2.0] - 2026-03-18

### Colr Pak (`mitradranirban/colr-pak`)

#### Features
- Add on-screen **Paint Tool** (`edit-tools-paint`) for interactive COLRv1 editing:
  - Drag-to-reposition handles for linear, radial, and sweep gradients
  - Click-to-cycle `paletteIndex` for `PaintSolid` layers
  - Dynamic cursor updates based on handle role under pointer
  - Visualization layer drawing handle circles, diamond badges, and dashed connector lines between gradient control points
- Rename app menu title from `Fontra Pak` to `Colr Pak` in `fontra-menus`
- Add separator between palette number and number of entries in the color palette panel

#### Bug Fixes
- Fix import path in `colr.py` — use absolute instead of relative imports

---

### Fontra (`mitradranirban/fontra`, branch `fontra-color-support`)

#### Features
- Rebased to upstream Fontra `2026.3.4`

#### Bug Fixes
- Restore `paletteIndex` in gradient `colorStops` — `_convertColorLine` was reading `stop.Color?.PaletteIndex` but raw fontTools stores `PaletteIndex` directly on the stop object; all gradient palette indexes were defaulting to 0
- Fix "add stop" button for COLRv1 gradients — fix method name references (`_setV1ArrayField`, `_writeV1Paint`) and correct `colorStops` nesting structure
- Fix TTF COLRv1 paint loading, panel detection, and rendering

---

### fontra-compile (`mitradranirban/fontra-compile` branch `fontra-color-support` )

#### Bug Fixes
- Fix `copyFont` stripping color palette data from temporary UFO before compiling through fontmake, which caused color variable fonts to export as monochrome
- Add function to prevent stripping of color palette data from `lib.plist` in variable font compilation

## [v0.1.3] - 2026-03-16

colr-pak 0.1.3
Bugfix: Removed `drop-unreachable-glyphs` from the export workflow and `drop-unused-sources-and-layers` from the fontmake compile action in fontra-compile — both filters were silently stripping color layer glyphs before fontmake could build the COLR/CPAL tables, resulting in monochrome output.
## [v0.1.2] - 2026-03-15

### Colr Pak (`mitradranirban/colr-pak`)

#### Bug Fixes
- Fix export of `.fontra` to `.ttf`/`.otf` via `fontra-compile` — resolves
  `TypeError: run_original() takes 0 positional arguments but 4 were given`
  crash when exporting from a loaded TTF font

#### Refactor
- Refactor `doExportAs` to use top-level `exportFontToPath` and new
  `exportFontToPathCompile` functions as multiprocessing targets, matching
  upstream Fontra Pak structure and preventing future breakage
- Add `COLR_PAK_VERSION` constant for single-point version management

---

### Fontra (`mitradranirban/fontra`, branch `fontra-color-support`)

#### Bug Fixes
- `fix(colrv1)`: Restore `paletteIndex` in gradient `colorStops` —
  `_convertColorLine` was reading `stop.Color?.PaletteIndex` but raw
  fontTools stores `PaletteIndex` directly on the stop object; all gradient
  palette indexes were defaulting to 0
- `fix(colrv1)`: Fix "add stop" button for COLRv1 gradients — fix method
  name references (`_setV1ArrayField`, `_writeV1Paint`) and correct
  `colorStops` nesting structure
- `fix(colrv1)`: TTF COLRv1 paint loading, panel detection and rendering —

- Remove accidental `.bak` file from bisect
- Rebased to current fontra `release/0.2.0`

---

### fontra-compile (`mitradranirban/fontra-compile`)

#### Features
- `feat`: Add COLRv1 compile support via `PythonBuilder` — reads paint data
  and palettes directly from `font-data.json`/glyph JSON; implements full
  `_dataToPaint()` covering solid, gradients, transforms, composite, with
  `varscalar()` for Fontra keyframe variation specs

#### Removals
- Remove deprecated `compile_colorv1_action.py` entry point — COLRv1
  compilation now handled entirely in `build.py`

---

## [v0.1.1] - 2026-03-12

### Colr Pak
- Remove deprecated `colorV1_export_helper` from fontra-compile integration
- Redirect `.fontra` files exclusively to `fontra-compile` for proper
  COLR and CPAL table compilation
- Rebase to fontra `2026.3.2`


#### Maintenance
- Add missing translations (i18n strings for new color UI)
- Add test font for COLRv1 testing
#### Fixes
 add `convertPaintGraph`/`convertColorLine` for fontTools raw format
  conversion; fix COLRv0 TTF panel detection
- `fix`: Add color palette support for UFO backend
---

## [v0.1.0] - 2026-03-10

- Initial release of Colr Pak — fork of Fontra Pak for COLR font editing
- Reads and writes `.ufo`/`.designspace` (COLRv0), `.fontra` (COLRv1)
- Partial support for `.glyphs`/`.glyphspackage` (without COLR data)
- Extracts color layers and palettes from `.ttf` files
- Linux support added (in addition to macOS and Windows)
- Homebrew Cask workflow with manual trigger support
- Cross-platform release packaging (macOS, Windows, Linux)
#### Features
- `feat(colrv1)`: Variable font support for `.fontra` sources + full paint
  graph fixes — add `getTagLocation()`, `getPaintGraph()`, `resolveVal()`;
  fix all 32 paint format handlers including composite modes, PaintGlyph,
  bezier curves
- `feat(color-layers)`: Add COLRv1 type-aware parameter UI with
  `PAINT_PARAM_SCHEMA`, paired field rendering, `_setV1PaintParam()` mutator
- `feat(color-palettes)`: Enhance palette panel — alpha slider, palette tab
  strip, usage badges, remove buttons, `PALETTES_KEY` export
- Add COLRv1 canvas renderer to visualization layer with proper clipping
- Add switchable paint type selector in Color Paint V1 panel
- Add `paintcompiler` base COLRv1 builder backend
- Add keyframe changes support for variable COLRv1 parameters
- Add color palette loading from OTFont
- Add Google test COLRv1 font and OpenType backend tests
- Color layer tab in frontend working
- Color font generation through `ufo2ft` working
