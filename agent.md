# agent.md — Battalion Level Editor (AI agent guide)

> Comprehensive orientation for an AI coding agent working in this repo.
> Built from a full read-through of the codebase (~47.5k lines, ~100 Python files).
> Companions: `ARCHITECTURE.md` (deep-dive on how the editor works) and
> `GRAPHICS_OVERHAUL_PLAN.md` (the day/night port plan — **its "no code written yet"
> note is STALE**, see "Current branch state" below).

---

## 0. Non-negotiable working rules (user-mandated)

1. **Only touch code that needs to be touched — nothing else.** Before any change,
   state the exact footprint (which files, which functions) and keep to it. Prefer one
   new file over edits scattered across existing ones. No drive-by refactors, no
   reformatting, no "while I'm here" cleanups, no fixing unrelated dead code unless
   asked. If a feature's footprint starts growing beyond what was agreed, stop and say so.
2. **Commit AND push after every completed feature or fix.** Each feature/fix gets
   its own commit with a clear message as soon as it works, then push to origin.
   Exception: the branch `personal_do_not_push_only_commit` is NEVER pushed (its
   pushRemote points at a nonexistent remote as a safety latch).
3. **No Claude/AI attribution in anything GitHub-bound.** Commit messages carry no
   Co-Authored-By trailers or AI mentions; commits use the user's git identity only.

---

## 1. What this is

A **PyQt6 + PyOpenGL desktop level editor for Battalion Wars 1 (GameCube) and
Battalion Wars 2 (Wii)**. It loads the games' level files (XML object data + `.res`
resource archive + binary terrain + compiled Lua), renders the level in an OpenGL
viewport, lets you edit every object through a reflective property editor, and saves
back to game-ready files. It can also hook a **running Dolphin emulator** and
live-edit object positions in game memory.

Forked from RenolY2's **MKDD Track Editor** — a lot of Pikmin/MKDD-era dead code
survives (see §12). Version string: `__version__` in `bw_editor.py` (currently 2.4.0.0).

**One codebase, two games.** BW1 vs BW2 is detected at load time (unknown field name
→ BW2) and handled by `hasattr` probing + per-game data tables, **not** subclasses.
Any change touching game data must be considered for BOTH games.

## 2. Running / environment

- **Run:** `python bw_editor.py [optional_level.xml]`. No `main()`; bootstrap is in the
  `if __name__ == "__main__"` block. The module `os.chdir`s to its own folder at import,
  so all resource paths are relative to repo root.
- **Deps** (`requirements.txt`): `PyQt6`, `PyOpenGL`, `numpy`, `Pillow`, `pyPEG2`.
  Optional: `lupa` (Lua simulator), Java (bundled JRE in `lib/lua/` for unluac).
  Python 3.9+. A `venv/` exists in the repo (gitignored).
- **Config:** `editor_config.ini` via `configuration.py`. `[editor]` keys include
  `dark_mode`, `wasdscrolling_speed`, `3d_background`, `regenerate_pf2`,
  `recompile_lua`, day/night keys `daynight_*`, plus `[recent_files]`,
  `[View Filter Toggles]`. Edited in-app via `widgets/editor_preferences.py`.
- **Logging:** stdout/stderr are teed to `editor_log.txt`.
- **Build:** `setup.py` (cx_Freeze). `mkdd_editor.spec` is a stale PyInstaller leftover — ignore.
- **Windows-only bits:** Dolphin memory hook (ctypes windll), `luac5.0.2.exe`, `os.startfile`.

## 3. Current branch state (as of 2026-07-21)

- Branch: **`day-and-night-cycle`** (off `master`; upstream remote = RenolY2).
- **The graphics overhaul (day/night/shadows/sky) IS IMPLEMENTED and sitting
  uncommitted** in the working tree: ~740 inserted lines across `bw_widgets.py`,
  `lib/graphics.py`, `lib/shader.py`, `lib/render/model_renderingv2.py`,
  `lib/bw/model_rendering.py`, `widgets/menu/menubar.py`, plus new files
  `lib/environment.py`, `lib/render/{celestial,god_rays,night_sky,shadow_map,sky_dome,volumetric_rays}.py`
  and asset `resources/skybox/night_sky.glb`. `ARCHITECTURE.md`, `GRAPHICS_OVERHAUL_PLAN.md`,
  and this file are untracked.
- Systems were ported from the Avatar Level Editor
  (`Desktop/......DEV/Avatar_Level_Editor/canvas/`).

## 4. Big-picture architecture

```
LevelEditor(QMainWindow)  bw_editor.py   ← god-object / service locator
 ├─ LevelDataTreeView      widgets/tree_view.py      (categorized object tree)
 ├─ BolMapViewer           bw_widgets.py             (the ONE QOpenGLWidget viewport)
 │    └─ Graphics          lib/graphics.py           (scene assembly, instanced draws)
 ├─ PikminSideWidget       widgets/side_widget.py    (right panel: add/del/clone/edit)
 ├─ EditorMenuBar          widgets/menu/menubar.py   (File/Filter/Misc/Environment/Dolphin/Lua/Plugins)
 ├─ EditorFileMenu         widgets/menu/file_menu.py (level LOAD + SAVE logic lives HERE)
 ├─ PluginHandler          widgets/menu/plugin.py    (plugin discovery + event bus)
 ├─ LuaWorkbench           lib/lua/luaworkshop.py    (decompile/edit/recompile mission Lua)
 ├─ Game (Dolphin hook)    lib/game_visualizer.py + lib/memorylib.py
 └─ level_file / preload_file = BattalionLevelFile   lib/BattalionXMLLib.py  ← THE data model
```

Everything holds an `editor` back-reference and reaches state through it:
`editor.level_file`, `editor.preload_file`, `editor.level_view`, `editor.pik_control`,
`editor.leveldatatreeview`, `editor.lua_workbench`, `editor.dolphin`,
`editor.file_menu.resource_archive`, `editor.plugin_handler`.

UI layout (`setup_ui`): horizontal `QSplitter` — [tree + `UnitViewer` mini model
preview] | viewport | plugin side tabs | main side tab. Not dock widgets.

## 5. The data model (`lib/BattalionXMLLib.py`) — the keystone

- A "level" = a small **manifest XML** (root `<levelfiles>`, parsed by
  `BattalionFilePaths` ~line 406) pointing at: object XML (`*_Level.xml`), preload XML
  (`*_Level_preload.xml`), resource archive (`.res`), terrain, strings, pathfinding.
  **BW2 wraps these in gzip (`.gz`); BW1 does not.** Optional per-file `padding`
  attributes keep file sizes stable so Dolphin savestates stay valid.
- **`BattalionObject`** (~540): schema-less wrapper around its lxml node
  (`self._node` is source of truth). Every child field becomes a **plain Python
  attribute** (`obj.mHealth`, `obj.mBase`, `obj.Mat`) via `update_object_from_xml`.
  `obj.fields()` yields `(tag, name, type, elements)` — this tuple drives the entire
  reflective edit UI. No per-type subclasses (`lib/xmltypes/bw1.py` is type-hint stubs only).
- **`BattalionLevelFile`** (~286): `objects` (id→obj), `objects_with_positions`
  (spatial subset the renderer iterates), `_categories` (type index). Two instances
  per level: `level_file` + `preload_file`.
- **Pointers are two-phase.** Fields of tag `Pointer`/`Resource` parse into
  `PointerPlaceholder`s; `resolve_pointers(other)` (both directions across
  level↔preload) replaces them with live object refs and builds the reverse-reference
  graph (`_referenced_by`, via `add_reference`). Never treat `obj.mBase` as an object
  before resolution. Null pointer = id `"0"`.
- **Types** convert via `lib/bw_types.py` `convert_from`/`convert_to`
  (`sFloat`, `sInt8..sUInt32`, `eBoolean` ↔ `eTrue`/`eFalse`, `cFxString8/16`,
  `sVector4`/`sU8Color`, `sVectorXZ`, `sMatrix4x4` → `BWMatrix`). `floatformat`
  reproduces the game's exact rounding for huge floats.
- **`BWMatrix`**: flat 16 float32, **column-major**; translation at indices 12/13/14;
  `[13]` = height (game space is Y-up). `decompose`/`recompose` for the gizmo/matrix editor.
  (Note: `decompose` still has stray `print("A"/"B"/"C")` debug lines.)
- **Add:** `create_object` from `resources/basetemplates/BW1|BW2/<Class>.xml` →
  `choose_unique_id` (bumps by +7) → `level.add_object_new`. **Clone:** round-trips
  through `tostring`/`create_from_text`. **Delete:** `obj.delete()` then
  `level.delete_objects([...])` — nulls all references and rebuilds the XML root.
- **Save order matters:** `sort_nodes()` orders `<Object>` nodes by `TYPEORDER`
  (resources before users) or the game won't load.
- `updatemodelname()` (~716) is a big per-type dispatch that derives `_modelname`
  (which 3D model to draw) and `_iconoffset` (billboard icon) — call it after edits
  that change a model reference.

## 6. Load / save pipeline (`widgets/menu/file_menu.py`)

**Load** (`button_load_level` ~262): `editor.reset()` → parse manifest → load both
`BattalionLevelFile`s → cross `resolve_pointers` → `BattalionArchive.from_file` (the
`.res`, via `lib/lua/bwarchivelib`) → `LuaWorkbench(levelpath+"_lua")` unpacks+decompiles
scripts → read water height from `cLevelSettings.mpRenderParams.mWaterHeight` →
`level_view.reloadModels/reloadTerrain` → `editor.setup_level_file`. Plugin events
`before_load`/`after_load` fire around it.

**Save** (`button_save_level`, Ctrl+S, ~416): plugin `before_save` (plugins flush
edits here!) → `update_xml()` on every object → optional PF2 pathfinding regen
(`regenerate_pf2` config; `PF2` class draws boundary/ford/nogo images from zones) →
optional Lua recompile + repack into `.res` (`recompile_lua`) → `sort_nodes` → write
XML/preload/res with gzip (BW2) and **space padding** — exceeding
`objectfilepadding`/`preloadpadding`/`respadding` raises an error (savestate safety).

**"Save As" is broken legacy MKDD code** (`_button_save_level_as` references
nonexistent attrs); the menu entry is commented out. Only plain Save works.

## 7. Rendering (`bw_widgets.py` + `lib/graphics.py` + `lib/render/`)

- **One GL widget:** `BolMapViewer(QOpenGLWidget)` (~317). A 2 ms `QTimer` runs
  `render_loop` (camera movement, day/night tick) and calls `update()` only when a
  frame was invalidated by `do_redraw()` — GPU idles when nothing changes.
  `do_redraw(force=…, forceselected=…, forcelight=…)` sets dirty flags.
- **Axis convention (the #1 bug source):** game world is Y-up; GL render space is
  **Z-up**. Geometry is emitted swapped `(x, z, y)`; shaders bake a constant swap
  matrix `mtx`; legacy model code also does `glScalef(-1,1,1)`. World spans ~±2048;
  3D far plane = 4000.
- **Cameras:** topdown = `glOrtho` + `offset_x/offset_z` + `zoom_factor`;
  3D = `gluPerspective(75°)` + spherical camera (`camera_horiz/vertical/height`).
  `MODE_TOPDOWN`/`MODE_3D` on `self.mode`.
- **Two renderer generations coexist:**
  - **v1** `lib/model_rendering.py` + `lib/bw/model_rendering.py` display lists /
    fixed-function: terrain tiles, grid, minimap, gizmo, collision viewer, `UnitViewer`.
  - **v2** `lib/render/model_renderingv2.py` VAO/VBO + GLSL + `glDrawArraysInstanced`:
    `ModelV2` (type-colored cubes), `Billboard` (icon atlas), `BWModelV2` (game
    models, interleaved pos+uv+normal, per-instance matrix attribs 2–5), `LineDrawing`,
    `WireframeModel`. **This is the main object path** — `Graphics.render_scene`
    (~388) rebuilds instance buffers only when dirty.
- Each positionable object renders as: colored **cube** (always), **3D model** (if
  `_modelname`), and/or **2D icon** (if `_iconoffset`); plus zone wireframes and
  waypoint lines. Colors from `lib/color_coding.json`.
- **Picking = color-ID rendering.** Clicks queue into a `SelectionQueue`, resolved
  inside `paintGL`: gizmo parts first (id in blue channel), then objects
  (`0x10000100 + (i<<12)`), decoded with `glReadPixels`. **Depends on white
  (0xFFFFFF) clear color as the "no-hit" sentinel — changing clear colors breaks
  selection.** Topdown 1-px clicks use an analytic distance test with hit-cycling.
- **Terrain:** `.out` sectioned file (tags byte-reversed: `RRET`/`KNHC`/`PAMC`/`LTAM`),
  64×64 chunk grid asserted; `BWTerrainV2` (`lib/bw_terrain.py`) builds tile meshes,
  a numpy heightmap (`check_height`, used for object snapping), and an AABB tree for
  ray picking. Rendered immediate-mode via display lists with the one hand-written
  shader (`lib/shader.py`).
- On-screen text (FPS, "LIVE EDIT") = Qt QLabel overlays, not GL text.
  `opengltext.py` actually holds the collision drawer, not text.

## 8. Day/night graphics overhaul (`lib/environment.py` + `lib/render/`)

The recently ported subsystem (from the Avatar editor). **Design contract: with the
cycle disabled, all uniforms are neutral (ambient=1, sun=fill=0, shadow off) and
rendering is pixel-identical to the old flat look.** Every effect self-guards: GL
failure sets `_failed` and silently disables — the viewport must never blank.

- **`Environment`** (`lib/environment.py`): `enabled`, `shadows_enabled`,
  `godrays_enabled`, `playing`, `time_of_day` (0=midnight, 0.25=sunrise, 0.5=noon,
  0.75=sunset), `CYCLE_SECONDS=120`. `update()` derives `light_dir_gl` (z-up; moon at
  night), premultiplied `sun/fill/ambient/sky/water` colors, `day/night_factor`,
  `shadow_strength`. Persists to config as `daynight_*`.
- **UI:** `EnvironmentMenu` in `widgets/menu/menubar.py` — F4 toggle cycle, F7
  shadows, sun-rays toggle, play/pause, `QTimeEdit` + `FineTimeSlider` (0–1439 min),
  presets. Syncs both ways with the `Environment` on `level_view.environment`.
- **Frame order in `paintGL`:** shadow-cast pass (terrain + instanced depth into
  `ShadowMap`, static light box `half_size=2200` centered at origin — one-frame lag
  handled by a forced extra redraw) → `SkyDome` (analytic gradient hemisphere,
  display list, radius 3450) → `NightSky` (Milky Way GLB dome, additive, radius 3500,
  own minimal GLB parser, `resources/skybox/night_sky.glb`) → sun/moon flares
  (`celestial.py`, additive discs at 3400) → terrain w/ lighting uniforms → scene w/
  lighting uniforms → water → god rays → volumetric rays.
- **Lighting model** (in `BWModelV2` frag + terrain shader):
  `lit = ambient + fill*max(N·up,0) + sun*max(N·L,0)*sun_shadow()`;
  `sun_shadow()` = 3×3 hardware-PCF against a 4096² `sampler2DShadow`, slope/receiver-
  specific bias (`shadow_bias("terrain"|model)`), texel-snapped light box.
- **Shadow sampler units:** models bind the shadow map on **unit 1**, terrain on
  **unit 3** — mixing sampler types on one unit is a draw error on strict drivers.
- **`GodRays`** = screen-space radial blur (512² occlusion FBO, sun must be on/near
  screen; terrain occluders use a dedicated black shader because fixed-function black
  is corrupted by attribute aliasing on NVIDIA). **`VolumetricRays`** = shadow-map
  ray-march (24 steps, works from any angle, needs that frame's shadow pass).
- Sky/celestial/night-sky push `GL_COLOR_BUFFER_BIT` so additive blend state doesn't
  leak into water/icons.
- Distances are tuned to the 4000 far plane — don't exceed it.
- Model normals: BW int8 `VNRM` (÷127) or float `VNBT`; normals are rotated by the
  node transform's rotation part when flattening (`make_textured_model`). "Lighting
  wrong on rotated models" = axis-swap/normal-rotation bug class; test by rotating a unit.

## 9. Game asset formats (`lib/bw/`, `lib/lua/bwarchivelib.py`)

- **`.res` archive:** flat stream of `[4-byte reversed tag][uint32 LE size][body]`,
  recursively nested. Tags read back-to-front: `LDOM`=MODL, `RXET`=TEXR, `DNOS`=SOND,
  `PRCS`=SCRP (compiled Lua), `MINA`=ANIM, `FEQT`=TQEF (tequila effects, plain text).
  Live reader used by the editor: `lib/lua/bwarchivelib.BattalionArchive`
  (legacy `lib/bw/bw_archive.py` is superseded). Section write order enforced by
  `ORDERLIST`. Padding hack: fake `FEQT` effect named `__PADDING__`.
- **BW1 vs BW2 discrimination:** texture table `FTBX`(BW1) vs `FTBG`(BW2); texture
  entries `TXET` (LE, 0x54 header, reversed fmt tags, `A8R8G8B8`) vs `DXTG` (BE, 0x70
  header, `8B8G8R8A`); model GX section `XBST`(BW1) vs `XBS2`(BW2); materials 0x48
  (BW1, 2 tex slots) vs 0xA4 (BW2, 4 tex slots). Texture name limits: BW1 ≤16 chars,
  BW2 ≤31 — asserted on write.
- **Textures:** GameCube GX block formats (CMPR/DXT1, I4/I8, IA4/IA8, RGB565,
  RGB5A3, RGBA32, C4/C8 palettes; palettes always RGB5A3). Codec:
  `lib/bw/texlib/texture_utils.py`; container: `lib/bw/bwtex.py`. Decoded to PIL,
  **PNG-cached in `texture_cache/`**, uploaded with mips disabled (`ignoremips=True`).
  Hardcoded hack: `c1sncave`/`c1snstalactite` forced opaque (mission 5.2 bug).
- **Models:** GX display-list bytecode interpreted via `lib/bw/gx.py` vertex
  descriptors into tri strips; node hierarchy + `TCNC` concat table; int16 positions
  scaled by `VSCL`; UVs ÷ 2^11. Nodes named `*NODRAW*/*COLLIDE*` are skipped. Entry
  point: `lib/bw/bwmodelrender.py::BWModelHandler.from_archive` → builds both a
  legacy display-list model and a `BWModelV2`. LODs are parsed (`SCNT`) but never
  selected at render time.
- **⚠ Shared lineage with `io_scene_bw`** (the sibling Blender add-on in BW_STUFF):
  `gx.py`, `read_binary.py`, `vectors.py` are byte-identical siblings; format fixes
  should flow both ways manually — there is no shared library.

## 10. Editing UI

- **Live property editor = `NewEditWindow`** (`widgets/edit_window.py`, ~2100 lines),
  an MDI subwindow generated reflectively from `object.fields()`. Widget-per-type
  dispatch in `FieldEdit.add_field` (~1201): `EnumBox`/`BooleanEnumBox` (tables in
  `edit_window_enums.py`, keyed `"BW1"`/`"BW2"`), `IntegerInput`, `DecimalInput`
  (**click-drag to scrub**, Shift = fine), `Vector4Edit` (+color swatch),
  `MatrixEdit` (decompose→Position/Scale/Angle), `StringEdit`, `FlagBox`
  (checkbox-per-bit; unknown bits prompt keep-or-strip), `ReferenceEdit` (searchable
  combo filtered by the `SUBSETS` type-compat map + Edit/Set-to-Selected/Clone
  buttons). **Edits mutate the Python attribute immediately** (no apply step) →
  `changed` → redraw + tree refresh + unsaved flag.
- Per-field tooltips from `objecthelp/*.doc` (format: `>GAME` header then
  `-FieldName` blocks; hot-reloaded on mtime); per-object overview help from
  `objecthelp/*.txt`.
- **Selection** syncs tree ↔ viewport ↔ panels through one signal, `select_update`.
  Selection state lives on `level_view`: `.selected`, `.selected_positions` (BWMatrix
  list the gizmo mutates).
- **Controls** (`editor_controls.py`): pluggable `ClickAction`/`ClickDragAction`
  classes per mouse button, separate topdown vs 3D tables in `UserControl`. Gizmo
  (`gizmo.py`, meshes from `resources/gizmo.obj` + `gizmo_collision.obj`) emits
  `move_points`/`rotate_current`; handled in `bw_editor.py`. WASD/QE camera, Shift
  speedup, Ctrl+1/Ctrl+2 topdown/3D, Ctrl+F find, Ctrl+A add, Ctrl+E edit, Ctrl+S save.
- **Undo/redo (Ctrl+Z/Y) covers ONLY transforms** (position/rotation snapshots),
  not add/delete/property edits. Disabled while Dolphin live-view is active.
- **Add objects:** built-in plugin `builtin_plugins/add_object_window.py` —
  "Add Existing Object" (base templates from `resources/basetemplates/`, spawn on
  terrain click, Shift = place multiple, ESC cancels, consecutive waypoints
  auto-link) and "Import External Object" (bundles from `battalion_objects/<game>/`).
- **Search** (Ctrl+F, `widgets/search_widget.py`): three modes — structured query
  (`lib/searchquery.py`, pyPEG2 grammar: `self.mBase.mArmy = eNavy & self.mHealth > 100`,
  operators `= != < <= > >= contains excludes & |`, list fields fan out, autocomplete
  from `fieldnames*.txt`/`values*.txt`), raw XML text search, and Lua grep.
- **Visibility filtering:** `widgets/filter_view.py` `FilterViewMenu` — per-type 2D/3D
  toggles + faction/selected filter rules, persisted to config.

## 11. Cross-cutting systems

### Plugins (`widgets/menu/plugin.py`)
- A plugin = `plugins/plugin*.py` exposing a class literally named `Plugin` with
  `.name` and `.actions` (list of `(label, func[, shortcut])`, each called as
  `func(editor)`; `actions` must exist even if empty).
- **Duck-typed event bus:** `execute_event(name, *args)` calls the same-named method
  on any plugin that has it; exceptions swallowed (console traceback only). Events:
  `load`, `plugin_init`, `before_load`/`after_load`, `before_save`, `select_update`,
  `render_post(viewer)`, `terrain_click_2d/3d`, `topdown_click`, `world_click`,
  `raycast_3d`, `key_press/release`, `delete_press`, `cancel_mode`,
  `on_dolphin_hook/unhook`, `world_click_select_start/continue/box`.
  (`render_post2`/`render_post_` seen in scenery_render are NOT registered — dead.)
- Optional `setup_widget(editor, widget)` adds a side-panel tab; `unload()` for
  cleanup before hot reload. **Hot reload** polls file mtimes — but NOT submodule
  dirs (`sfx_editor/`, `strings_editor/`…), which is why plugins `reload()` their
  submodules in `unload`.
- Shipped plugins: object export/import (with full dependency graph of models/
  textures/effects/anims/sounds/scripts), texture export/import (header encoded in
  the PNG **filename**: `<name>.<FMT>.<u2>...<u7>.png`), PFD/PF2 pathfinding editor,
  Lua tools/simulator/global-var viewer, misc tools (savestates, clean invalid
  resources), padding manager, scenery cluster renderer (reimplements the game's RNG
  to reproduce placement), SFX editor (**separate tkinter process**, talks via temp
  file, changes only land on level save), strings editor (`.str` UTF-16-LE), GUI
  visualizer.

### Lua (`lib/lua/`)
Missions are Lua, stored as **compiled Lua 5.0.2 bytecode** in `PRCS` sections.
`LuaWorkbench` workdir = `<levelpath>_lua`: unpack → decompile with `unluac.jar`
(bundled JRE; some known-bad decompiles are patched by SHA-1 from
`lua_decomp_fixes/`) → edit plain `.lua` externally → on save, recompile changed
files (mtime-tracked in `file_changes.json`) with `luac5.0.2.exe` and repack.
`EntityInitialise.lua` maps object IDs ↔ script names via `RegisterReflectionId`
lines and is always recompiled. `LuaSimulator` (`lupa`) runs level scripts in-editor
with the whole BW API stubbed (`bw1_functions.py`/`bw2_functions.py`), coroutine per
(script, owner), `SetReturn` to fake return values.

### Dolphin live integration (`lib/memorylib.py` + `lib/game_visualizer.py`)
Windows-only. Finds Dolphin's PID, opens its emulated RAM as shared memory
(`dolphin-emu.<pid>`), translates GC (`0x8000_0000+`) / Wii MEM2 (`0x9000_0000+`)
addresses. `Game.initialize` reads the game ID and picks **hardcoded per-region
object-list addresses** (BW1/BW2, US/PAL/JP). Reimplements the game's ID hash lookup
to map editor objects → live addresses; ~10 Hz loop reads matrices at `addr+0x30`
(`+8` more for zones) into `mtxoverride` (Live View) and writes selected objects'
matrices back (Live Edit) after sanity-checking the memory looks like a rotation
matrix. Lua global-var viewer walks the game's live Lua state via `luastructs.py`.
Heap debug window supports only `G8WE`/`RBWE` (US builds).

## 12. Dead code / traps — do not trust these

- `widgets/data_editor.py` — entire MKDD typed-editor system; `choose_data_editor`
  always returns `None`.
- "Save As"/"Save Copy As" in `file_menu.py` — broken MKDD leftovers, menu entries
  commented out.
- `bw_read_xml.py` (old parser), `py_obj.py`'s `PikminCollision` (undefined
  `read_int`), most unit classes in v1 `lib/model_rendering.py`, `default_path.cfg`,
  `mkdd_editor.spec`, `pikmin-tools.git.iml`.
- References to `libbol`, `mkdd_widgets`, `self.pikmin_gen_view` in `bw_editor.py` /
  `editor_widgets.py` would NameError if reached (e.g. `action_change_object_heights`).
- `side_widget.py` legacy raw-XML edit path uses `self.edit_windows` which is never
  initialized — latent AttributeError.
- `model_rendering.py` (lib root) uses `selectioncolor` whose definition is commented
  out — latent NameError on legacy selected-render paths.
- `Transform.__init__` in `lib/bw/model_rendering.py` has ~26 dead quaternion
  permutation lines; the real mapping is the last one (`x,y,z,w = d,c,b,a`).
- **Import side effects:** `xml_search.py` runs hardcoded `D:\` paths at import;
  `lib/compress.py` runs a CLI at import; `lib/luastructs.py` prints at import.
  Never import these casually.

## 13. Conventions & rules of thumb for changes

1. **BW1/BW2 parity:** any format/data change must handle and be tested on both
   games (per-game tables, endianness, header sizes, field spellings).
2. **Axis swap discipline:** game (x, y=height, z) vs GL z-up `(x, z, y)`; watch for
   `-z` flips and the `glScalef(-1,1,1)` mirror in legacy paths. The classic bug is
   lighting/geometry wrong only on rotated objects.
3. **Don't break picking:** the selection pass assumes white clear color and its own
   colorid shader variants — keep new render passes out of the selection path and
   restore GL state (blend, depth mask, texture units) after custom passes.
4. **Graphics overhaul contract:** disabled day/night must stay pixel-identical to
   the old renderer; effects must degrade silently, never blank the viewport.
5. **Respect save padding** and node ordering (`sort_nodes`).
6. **Prefer a plugin** (`plugins/plugin_*.py`) for new features — hot-reloadable,
   event-driven, no core edits.
7. Repo must run with **cwd = repo root** (chdir at import relies on it; all
   resource paths relative).
8. After changing a model/base reference on an object, call `updatemodelname()` and
   `do_redraw(force=True)`.
9. Field edits go through `bw_types.convert_from/convert_to` — keep serialization
   byte-faithful (the game and savestate padding care).

## 14. Quick map — "where do I change X?"

| Task | Files |
|---|---|
| Startup / main window / shortcuts | `bw_editor.py` |
| Object model, load/save, pointers | `lib/BattalionXMLLib.py`, `lib/bw_types.py`, `widgets/menu/file_menu.py` |
| Viewport, paintGL, picking, camera | `bw_widgets.py` |
| Scene assembly / instanced draws | `lib/graphics.py`, `lib/render/model_renderingv2.py` |
| Day/night, shadows, sky, rays | `lib/environment.py`, `lib/render/*`, `lib/shader.py`, `EnvironmentMenu` in `widgets/menu/menubar.py` |
| Terrain | `lib/bw_terrain.py`, `render_terrain_immediate` in `bw_widgets.py`, `lib/shader.py` |
| Property editor / enums / flags | `widgets/edit_window.py`, `widgets/edit_window_enums.py` |
| Tree / side panel / filters / search | `widgets/tree_view.py`, `widgets/side_widget.py`, `widgets/filter_view.py`, `widgets/search_widget.py`, `lib/searchquery.py` |
| Mouse / gizmo | `editor_controls.py`, `gizmo.py` |
| `.res` archive / models / textures | `lib/lua/bwarchivelib.py`, `lib/bw/` (`bwmodelrender.py`, `model_rendering.py`, `gx.py`, `bwtex.py`, `texlib/`) |
| Lua | `lib/lua/luaworkshop.py`, `lib/lua/lua_simulator.py`, plugins `plugin_lua_*` |
| Dolphin live edit | `lib/memorylib.py`, `lib/game_visualizer.py`, Dolphin menu in `menubar.py` |
| Add objects | `builtin_plugins/add_object_window.py`, `resources/basetemplates/` |
| New feature | new `plugins/plugin_*.py` (see `plugins/plugin_example.py`, API in §11) |
