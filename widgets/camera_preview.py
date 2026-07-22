import os
import re
import math
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets
import PyQt6.QtOpenGLWidgets as QtOpenGLWidgets
from PyQt6.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *

from lib.bw_types import BWMatrix


# Camera POV preview for cutscene cameras (cCamera), shown in the Main side tab.
#
# Renders the level through a camera the way the game frames it: terrain, object
# models and water only - no editor markers. Rendering reuses the main viewport's
# shared GL resources (terrain display lists, model display lists, textures,
# terrain shader), which works because AA_ShareOpenGLContexts is set at startup.
# The v2 instanced renderer is not used here (VAOs don't cross GL contexts).
#
# Two modes:
# - Selected camera (sticky): selecting a cCamera in the tree/3D view points the
#   preview through it. Selecting waypoints or other objects does NOT retarget
#   the preview, so paths can be edited while watching through the lens.
#   Play flies the camera along its mCurrentWP -> NextWP chain, aiming at
#   mTarget (which may itself travel its own waypoint chain).
# - Cutscene: the level's decompiled Lua scripts (LuaWorkbench) are parsed for
#   the camera API both games share (SetCamera / CameraSetWaypoint /
#   CameraSetTarget / CameraSetFOV / CameraFade / WaitFor). Each script using it
#   becomes a playable timeline of shots (intro/mid/ending cutscenes etc.).
#   Parsing is line-based over the linear statement flow of decompiled cutscene
#   scripts; Lua control flow is not simulated.

DEFAULT_FOV = 58.0
FAR_PLANE = 4000.0
DRAW_DISTANCE = 1500.0
CHAIN_LIMIT = 64
TAIL_TIME = 2.0
STATIC_SHOT_TIME = 4.0


def _obj_pos(obj):
    mtx = obj.getmatrix()
    if mtx is None:
        return None
    height = getattr(obj, "height", None)
    y = mtx.mtx[13] if height is None else max(mtx.mtx[13], height)
    return (mtx.mtx[12], y, mtx.mtx[14])


def _raw_pos(obj):
    mtx = obj.getmatrix()
    if mtx is None:
        return None
    return (mtx.mtx[12], mtx.mtx[13], mtx.mtx[14])


class WaypointChain(object):
    """A camera waypoint chain: positions + per-segment speed/pause sampling."""
    def __init__(self, head_wp):
        self.nodes = []          # (pos, speed, pausetime)
        self.cycle_start = None  # index the chain loops back to, or None
        seen = {}
        wp = head_wp
        while wp is not None and len(self.nodes) < CHAIN_LIMIT:
            if id(wp) in seen:
                self.cycle_start = seen[id(wp)]
                break
            seen[id(wp)] = len(self.nodes)
            pos = _obj_pos(wp)  # terrain-aware: lifts ground-level waypoint heights
            if pos is None:
                break
            speed = getattr(wp, "mSpeed", 10.0)
            if speed is None or speed < 0.01:
                speed = 10.0
            pause = getattr(wp, "mPauseTime", 0.0) or 0.0
            self.nodes.append((pos, speed, pause))
            wp = getattr(wp, "NextWP", None)

        # Per-segment travel times, walked once so sampling is simple.
        self.segments = []  # (start_time, duration, from_index, to_index, kind)
        t = 0.0
        for i, (pos, speed, pause) in enumerate(self.nodes):
            if pause > 0.0:
                self.segments.append((t, pause, i, i, "pause"))
                t += pause
            nexti = i + 1
            if nexti >= len(self.nodes):
                if self.cycle_start is not None:
                    nexti = self.cycle_start
                else:
                    break
            dist = math.dist(pos, self.nodes[nexti][0])
            dur = dist / speed if speed > 0 else 0.0
            if dur > 0.0:
                self.segments.append((t, dur, i, nexti, "move"))
                t += dur
        self.duration = t

    def sample(self, t):
        if not self.nodes:
            return None
        if not self.segments or t <= 0.0:
            return self.nodes[0][0]
        if t >= self.duration:
            if self.cycle_start is not None and self.duration > 0.0:
                t = t % self.duration
            else:
                return self.nodes[-1][0]
        for start, dur, i, j, kind in self.segments:
            if t < start + dur:
                if kind == "pause" or dur <= 0.0:
                    return self.nodes[i][0]
                f = (t - start) / dur
                a, b = self.nodes[i][0], self.nodes[j][0]
                return (a[0] + (b[0] - a[0]) * f,
                        a[1] + (b[1] - a[1]) * f,
                        a[2] + (b[2] - a[2]) * f)
        return self.nodes[-1][0]


class UnitRoute(object):
    """A scripted unit movement: walk a polyline at a speed."""
    def __init__(self, start_time, start_pos, points, speed):
        self.start_time = start_time
        self.speed = speed if speed > 0.01 else 5.0
        self.points = [start_pos] + list(points)
        self.lengths = []
        total = 0.0
        for i in range(len(self.points) - 1):
            seg = math.dist(self.points[i], self.points[i + 1])
            self.lengths.append(seg)
            total += seg
        self.total = total

    def sample(self, t):
        """(pos, horizontal direction) at time t."""
        dist = max(t - self.start_time, 0.0) * self.speed
        if dist >= self.total or not self.lengths:
            p = self.points[-1]
            a, b = self.points[-2] if len(self.points) > 1 else p, p
        else:
            walked = 0.0
            a = b = self.points[0]
            for i, seg in enumerate(self.lengths):
                if dist <= walked + seg:
                    a, b = self.points[i], self.points[i + 1]
                    f = (dist - walked) / seg if seg > 0 else 0.0
                    p = (a[0] + (b[0] - a[0]) * f,
                         a[1] + (b[1] - a[1]) * f,
                         a[2] + (b[2] - a[2]) * f)
                    break
                walked += seg
        dx, dz = b[0] - a[0], b[2] - a[2]
        length = math.hypot(dx, dz)
        if length < 1e-5:
            direction = (0.0, 1.0)
        else:
            direction = (dx / length, dz / length)
        return p, direction


def _facing_matrix(pos, direction):
    """BW column-major matrix at pos, model +Z facing the travel direction."""
    import numpy
    dx, dz = direction
    return numpy.array([dz, 0.0, -dx, 0.0,
                        0.0, 1.0, 0.0, 0.0,
                        dx, 0.0, dz, 0.0,
                        pos[0], pos[1], pos[2], 1.0], dtype=numpy.float32)


class CutsceneTimeline(object):
    """One Lua script's camera timeline: timed events + derived shot list."""
    RE_WAIT = re.compile(r"WaitFor\(\s*([0-9.]+)\s*\)")
    RE_SETCAM = re.compile(r"\bSetCamera\(\s*([\w.]+)\s*\)")
    RE_SETWP = re.compile(r"CameraSetWaypoint\(\s*([\w.]+)\s*,\s*([\w.]+)\s*\)")
    RE_SETTARGET = re.compile(r"CameraSetTarget\(\s*([\w.]+)\s*,\s*([\w.]+)\s*\)")
    RE_SETFOV = re.compile(r"CameraSetFOV\(\s*([\w.]+)\s*,\s*([0-9.]+)")
    RE_FADE = re.compile(r"CameraFade\(\s*constant\.(FADE_IN|FADE_OUT)\s*,\s*constant\.(WAIT|NO_WAIT)\s*,\s*([0-9.]+)")
    RE_FOLLOW = re.compile(r"FollowWaypoint\(\s*([\w.]+)\s*,\s*([\w.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)")
    RE_GOTO = re.compile(r"GoToArea\(\s*([\w.]+)\s*,\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)")
    RE_KILL = re.compile(r"\bKill\(\s*([\w.]+)\s*\)")
    GOTO_SPEED = 10.0

    RE_BLOCK_OPEN = re.compile(r"\b(?:if\b.*\bthen|while\b.*\bdo|for\b.*\bdo|function\b)")
    RE_BLOCK_CLOSE = re.compile(r"^\s*end\b")

    def __init__(self, name, text, resolve):
        self.name = name
        self.events = []   # (time, kind, data)
        self.fades = []    # (time, direction, duration)
        self.follows = []  # (time, unit_obj, "wp"|"area", wp_obj_or_xz, speed, conditional)
        self.kills = []    # (time, obj, conditional)
        self.camera_first_time = {}  # camera obj -> earliest time it becomes active
        clock = 0.0
        has_camera_op = False
        # Track control-flow nesting: commands inside if/while/for blocks are
        # gameplay-conditional; the game runs every script from level start, so
        # only the linear top-of-function flow is safe to merge into another
        # script's cutscene as background movement.
        depth = 0
        for line in text.splitlines():
            conditional = depth > 1  # depth 1 = the function body itself
            if self.RE_BLOCK_CLOSE.search(line):
                depth = max(depth - 1, 0)
            if self.RE_BLOCK_OPEN.search(line):
                depth += 1
            m = self.RE_SETCAM.search(line)
            if m is not None:
                obj = resolve(m.group(1))
                if obj is not None:
                    self.events.append((clock, "camera", obj))
                    self.camera_first_time.setdefault(obj, clock)
                    has_camera_op = True
            m = self.RE_SETWP.search(line)
            if m is not None:
                cam, wp = resolve(m.group(1)), resolve(m.group(2))
                if wp is not None:
                    self.events.append((clock, "waypoint", (cam, wp)))
                    if cam is not None:
                        self.camera_first_time.setdefault(cam, clock)
                    has_camera_op = True
            m = self.RE_SETTARGET.search(line)
            if m is not None:
                target = resolve(m.group(2))
                self.events.append((clock, "target", target))
            m = self.RE_SETFOV.search(line)
            if m is not None:
                self.events.append((clock, "fov", float(m.group(2))))
                cam = resolve(m.group(1))
                if cam is not None:
                    # e.g. the level's FIRSTCAM opens a cutscene without any
                    # SetCamera call - the FOV line is its only reference.
                    self.camera_first_time.setdefault(cam, clock)
            m = self.RE_FADE.search(line)
            if m is not None:
                direction, wait, dur = m.group(1), m.group(2), float(m.group(3))
                self.fades.append((clock, direction, dur))
                if wait == "WAIT":
                    clock += dur
            m = self.RE_FOLLOW.search(line)
            if m is not None:
                unit, wp = resolve(m.group(1)), resolve(m.group(2))
                if unit is not None and wp is not None:
                    self.follows.append((clock, unit, "wp", wp, float(m.group(4)), conditional))
            m = self.RE_GOTO.search(line)
            if m is not None:
                unit = resolve(m.group(1))
                if unit is not None:
                    dest = (float(m.group(2)), float(m.group(3)))
                    self.follows.append((clock, unit, "area", dest, self.GOTO_SPEED, conditional))
            m = self.RE_KILL.search(line)
            if m is not None:
                obj = resolve(m.group(1))
                if obj is not None:
                    self.kills.append((clock, obj, conditional))
            m = self.RE_WAIT.search(line)
            if m is not None:
                clock += float(m.group(1))
        self.valid = has_camera_op
        self.duration = clock + TAIL_TIME
        # A shot starts wherever the camera is cut or re-railed.
        shot_times = sorted(set(t for t, kind, data in self.events
                                if kind in ("camera", "waypoint")))
        self.shots = shot_times if shot_times else [0.0]

    def state_at(self, t):
        # Before the first SetCamera, the earliest camera the script references
        # (usually the level's FIRSTCAM) is the one on screen.
        first_cam = None
        if self.camera_first_time:
            first_cam = min(self.camera_first_time, key=self.camera_first_time.get)
        cam = wp = target = None
        fov = None
        wp_set_time = target_set_time = 0.0
        for time, kind, data in self.events:
            if time > t:
                break
            if kind == "camera":
                if data is not cam:
                    # A cut to a different camera drops the previous rail/target/
                    # FOV; the new camera falls back to its own XML state.
                    wp = target = fov = None
                cam = data
            elif kind == "waypoint":
                if data[0] is not None:
                    cam = data[0]
                wp = data[1]
                wp_set_time = time
            elif kind == "target":
                target = data
                target_set_time = time
            elif kind == "fov":
                fov = data
        if cam is None:
            cam = first_cam
        return cam, wp, t - wp_set_time, target, t - target_set_time, fov

    def fade_at(self, t):
        alpha = 0.0
        for time, direction, dur in self.fades:
            if time > t:
                break
            if t >= time + dur:
                alpha = 1.0 if direction == "FADE_OUT" else 0.0
            else:
                f = (t - time) / dur if dur > 0 else 1.0
                alpha = f if direction == "FADE_OUT" else 1.0 - f
        return alpha


class CameraPreviewGL(QtOpenGLWidgets.QOpenGLWidget):
    def __init__(self, parent, editor):
        super().__init__(parent)
        self.editor = editor
        self.owner = parent
        self.setMinimumHeight(160)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Expanding)
        self._error_shown = False
        self._static_list = None
        self._static_key = None

    def paintGL(self):
        try:
            import time
            start = time.perf_counter()
            self._paint()
            self.owner.perf_note("preview_paint", time.perf_counter() - start)
        except Exception:
            if not self._error_shown:
                self._error_shown = True
                traceback.print_exc()

    def _paint(self):
        glClearColor(0.55, 0.70, 0.90, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        lv = self.editor.level_view
        pose = self.owner.current_pose()
        if lv.bwmodelhandler is None or self.editor.level_file is None or pose is None:
            return
        campos, lookat, fov, fade = pose

        w, h = max(self.width(), 1), max(self.height(), 1)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(fov, w / h, 1.0, FAR_PLANE)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        # BW world (x, y=height, z) -> GL z-up render space (x, z, y).
        gluLookAt(campos[0], campos[2], campos[1],
                  lookat[0], lookat[2], lookat[1], 0.0, 0.0, 1.0)
        glEnable(GL_DEPTH_TEST)

        self._render_terrain(lv)
        self._render_objects(lv, campos)
        self._render_water(lv)

        if fade > 0.001:
            self._render_fade(fade)

    def _render_terrain(self, lv):
        if lv.bwterrain is None or lv.shader is None or not lv.terrainmap:
            return
        glUseProgram(lv.shader)
        glDisable(GL_ALPHA_TEST)
        glUniform1i(glGetUniformLocation(lv.shader, "overlayTex"), 2)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D, lv.overlay_texture.id)
        glUniform1i(glGetUniformLocation(lv.shader, "tex"), 0)
        glUniform1i(glGetUniformLocation(lv.shader, "tex2"), 1)
        for meshindex, displist in zip(lv.bwterrain.meshes, lv.terrainmap):
            material = lv.bwterrain.materials[meshindex]
            tex1 = lv.bwmodelhandler.textures.get_texture(material.mat1)
            tex2 = lv.bwmodelhandler.textures.get_texture(material.mat2)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, tex1[1])
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, tex2[1])
            glCallList(displist)
        glUseProgram(0)
        glActiveTexture(GL_TEXTURE1)
        glDisable(GL_TEXTURE_2D)
        glActiveTexture(GL_TEXTURE0)

    def _render_objects(self, lv, campos):
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GEQUAL, 0.5)
        glDisable(GL_BLEND)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        handler = lv.bwmodelhandler
        overrides = self.owner.unit_overrides()
        killed = self.owner.killed_units()
        # Everything that never moves (non-troops without an override) is
        # compiled once per level+route set into a single display list -
        # per-frame Python GL overhead was ~40ms/frame without this.
        dynamic_ids = set(self.owner._unit_routes)
        static_key = (id(self.editor.level_file), frozenset(dynamic_ids))
        if self._static_key == static_key and self._static_list is not None:
            glCallList(self._static_list)
        elif getattr(self, "_static_warm", None) != static_key:
            # First frame after a change: draw statics directly so lazily-built
            # model display lists get created now - creating them nested inside
            # our own list compile is a GL error (black preview).
            self._draw_statics(handler, dynamic_ids, compile_list=False)
            self._static_warm = static_key
        else:
            if self._static_list is not None:
                glDeleteLists(self._static_list, 1)
                self._static_list = None
            try:
                self._static_list = glGenLists(1)
                glNewList(self._static_list, GL_COMPILE)
                try:
                    self._draw_statics(handler, dynamic_ids, compile_list=True)
                finally:
                    glEndList()
                self._static_key = static_key
                glCallList(self._static_list)
            except Exception:
                traceback.print_exc()
                self._static_list = None
                self._static_key = None
                self._draw_statics(handler, dynamic_ids, compile_list=False)

        # Troops + script-moved units render per frame (poses/positions change).
        self._render_dynamic(lv, campos, handler, overrides, killed, dynamic_ids)
        glDisable(GL_TEXTURE_2D)

    def _draw_statics(self, handler, dynamic_ids, compile_list):
        for objid, obj in self.editor.level_file.objects_with_positions.items():
            modelname = obj._modelname
            if (modelname is None or modelname not in handler.models
                    or objid in dynamic_ids):
                continue
            mtx = obj.getmatrix()
            if mtx is None:
                continue
            currmtx = mtx.mtx.copy()
            height = getattr(obj, "height", None)
            if height is not None:
                currmtx[13] = height
            if obj.type == "cTroop":
                BWMatrix.static_rotate_y(currmtx, math.pi)
            handler.rendermodel(modelname, currmtx, None, 0)

    def _render_dynamic(self, lv, campos, handler, overrides, killed, dynamic_ids):
        maxdist_sq = DRAW_DISTANCE ** 2
        for objid, obj in self.editor.level_file.objects_with_positions.items():
            modelname = obj._modelname
            if modelname is None or modelname not in handler.models:
                continue
            if objid not in dynamic_ids:
                continue  # everything else is in the compiled static scene
            if objid in killed:
                continue
            mtx = obj.getmatrix()
            if mtx is None:
                continue
            override = overrides.get(objid)
            dx = mtx.mtx[12] - campos[0]
            dz = mtx.mtx[14] - campos[2]
            if override is not None:
                pos, direction = override
                currmtx = _facing_matrix(pos, direction)
            else:
                if dx * dx + dz * dz > maxdist_sq:
                    continue
                currmtx = mtx.mtx.copy()
                height = getattr(obj, "height", None)
                if height is not None:
                    currmtx[13] = height
            if obj.type == "cTroop":
                BWMatrix.static_rotate_y(currmtx, math.pi)
            handler.rendermodel(modelname, currmtx, None, 0)
        glDisable(GL_TEXTURE_2D)

    def _render_water(self, lv):
        if lv.waterheight is None:
            return
        glDisable(GL_ALPHA_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.0, 12 / 255.0, 92 / 255.0, 0.7)
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(-2048, -2048, lv.waterheight)
        glVertex3f(2048, -2048, lv.waterheight)
        glVertex3f(2048, 2048, lv.waterheight)
        glVertex3f(-2048, 2048, lv.waterheight)
        glEnd()
        glDisable(GL_BLEND)
        glEnable(GL_ALPHA_TEST)

    def _render_fade(self, fade):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_ALPHA_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.0, 0.0, 0.0, min(fade, 1.0))
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(-1.0, -1.0, 0.0)
        glVertex3f(1.0, -1.0, 0.0)
        glVertex3f(1.0, 1.0, 0.0)
        glVertex3f(-1.0, 1.0, 0.0)
        glEnd()
        glDisable(GL_BLEND)
        glEnable(GL_ALPHA_TEST)
        glEnable(GL_DEPTH_TEST)


class CameraPreviewWidget(QtWidgets.QWidget):
    """Header + GL POV view + transport controls. Lives in the Main side tab."""
    def __init__(self, parent, editor):
        super().__init__(parent)
        self.editor = editor

        self._level_ref = None
        self._camera = None            # sticky selected cCamera
        self._chain = None             # WaypointChain of self._camera
        self._target_chain = None
        self._cutscenes = []           # CutsceneTimeline list
        self._active_cutscene = None
        self._t = 0.0
        self._playing = False
        self._duration = 0.0
        self._unit_routes = {}         # objid -> [UnitRoute] sorted by start time
        self._all_timelines = []       # every level script, for background movement
        self._merged_kills = []
        self._parse_retries = 0
        self._overridden = set()       # objids with an active display override
        self._tick_count = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        self.header = QtWidgets.QLabel("Camera Preview: no camera selected")
        font = QtGui.QFont()
        font.setFamily("Consolas")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        font.setPointSize(8)
        self.header.setFont(font)
        layout.addWidget(self.header)

        self.glview = CameraPreviewGL(self, editor)
        layout.addWidget(self.glview, 1)

        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(2)
        self.button_prev = QtWidgets.QPushButton("<")
        self.button_prev.setFixedWidth(24)
        self.button_prev.setToolTip("Previous camera / cutscene shot")
        self.button_play = QtWidgets.QPushButton("Play")
        self.button_play.setToolTip("Fly the camera along its waypoints, or play the chosen cutscene")
        self.button_next = QtWidgets.QPushButton(">")
        self.button_next.setFixedWidth(24)
        self.button_next.setToolTip("Next camera / cutscene shot")
        self.cutscene_box = QtWidgets.QComboBox()
        self.cutscene_box.setToolTip("Play a whole cutscene as sequenced by the level's Lua scripts")
        controls.addWidget(self.button_prev)
        controls.addWidget(self.button_play)
        controls.addWidget(self.button_next)
        controls.addWidget(self.cutscene_box, stretch=1)
        layout.addLayout(controls)

        self.button_prev.pressed.connect(lambda: self.navigate(-1))
        self.button_next.pressed.connect(lambda: self.navigate(1))
        self.button_play.pressed.connect(self.toggle_play)
        self.cutscene_box.activated.connect(self.choose_cutscene)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)  # 60fps playback
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)

        editor.level_view.select_update.connect(self.on_select_update)

    # ------------------------------------------------------------------ state

    def check_level(self):
        """Detect level load/reset and rebuild cutscene list + camera state."""
        level = self.editor.level_file
        if level is self._level_ref:
            return
        self._level_ref = level
        self._camera = None
        self._chain = None
        self._target_chain = None
        self._active_cutscene = None
        self._unit_routes = {}
        self._all_timelines = []
        self._merged_kills = []
        self._parse_retries = 3
        self.stop_play()
        self._cutscenes = []
        if level is not None:
            self._cutscenes = self.parse_cutscenes()
        self.populate_cutscene_box()
        self.update_header()

    def populate_cutscene_box(self):
        self.cutscene_box.blockSignals(True)
        self.cutscene_box.clear()
        self.cutscene_box.addItem("Selected Camera")
        for cutscene in self._cutscenes:
            self.cutscene_box.addItem("Cutscene: " + cutscene.name)
        self.cutscene_box.blockSignals(False)

    def parse_cutscenes(self):
        workbench = getattr(self.editor, "lua_workbench", None)
        if workbench is None or workbench.entityinit is None:
            return []
        name_to_obj = {}
        level, preload = self.editor.level_file, self.editor.preload_file
        for objid, luaname in workbench.entityinit.reflection_ids.items():
            obj = level.objects.get(objid)
            if obj is None and preload is not None:
                obj = preload.objects.get(objid)
            if obj is not None:
                name_to_obj[luaname] = obj

        def resolve(name):
            return name_to_obj.get(name)

        cutscenes = []
        self._all_timelines = []
        try:
            paths = workbench.get_lua_script_paths()
        except Exception:
            return []
        for path in sorted(paths):
            try:
                with open(path, "r", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            # Every script is parsed: non-camera scripts still contribute
            # background unit movement to cutscene playback (the game runs
            # all scripts concurrently from level start).
            timeline = CutsceneTimeline(
                os.path.splitext(os.path.basename(path))[0], text, resolve)
            self._all_timelines.append(timeline)
            if timeline.valid:
                cutscenes.append(timeline)
        return cutscenes

    def on_select_update(self):
        self.check_level()
        # The Lua workbench may finish decompiling after the level-change check;
        # retry the cutscene scan a few times until scripts appear.
        if not self._cutscenes and self._parse_retries > 0 and self.editor.level_file is not None:
            self._parse_retries -= 1
            self._cutscenes = self.parse_cutscenes()
            if self._cutscenes:
                self.populate_cutscene_box()
        # Sticky rule: only an actual cCamera selection retargets the preview.
        for obj in self.editor.level_view.selected:
            if obj.type == "cCamera":
                if obj is not self._camera:
                    self.set_camera(obj)
                break
        self.glview.update()

    def set_camera(self, obj):
        self.stop_play()
        self._camera = obj
        self._chain = None
        self._target_chain = None
        self._active_cutscene = None
        self._unit_routes = {}
        self._t = 0.0
        wp = getattr(obj, "mCurrentWP", None)
        if wp is not None:
            self._chain = WaypointChain(wp)
        target = getattr(obj, "mTarget", None)
        if target is not None and target.type == "cWaypoint":
            self._target_chain = WaypointChain(target)
        self.cutscene_box.blockSignals(True)
        self.cutscene_box.setCurrentIndex(0)
        self.cutscene_box.blockSignals(False)
        self.update_header()

    def choose_cutscene(self, index):
        self.stop_play()
        self._t = 0.0
        self._unit_routes = {}
        if index <= 0:
            self._active_cutscene = None
        elif index - 1 < len(self._cutscenes):
            self._active_cutscene = self._cutscenes[index - 1]
            self.build_unit_routes()
        self.update_header()
        self.glview.update()

    # ------------------------------------------------------------------ pose

    def current_pose(self):
        """(pos, lookat, fov_degrees, fade) in BW world coords, or None."""
        self.check_level()
        if self._active_cutscene is not None:
            return self.cutscene_pose()
        return self.camera_pose()

    def camera_fov(self, camera):
        base = getattr(camera, "mBase", None)
        fov = getattr(base, "fov", None) if base is not None else None
        if fov is None or fov <= 0.0:
            return DEFAULT_FOV
        return math.degrees(fov)

    def aim_from_matrix(self, camera, pos):
        mtx = camera.getmatrix()
        if mtx is None:
            return (pos[0], pos[1], pos[2] - 10.0)
        # Look along the matrix' local Z axis; degenerate guard below.
        fx, fy, fz = mtx.mtx[8], mtx.mtx[9], mtx.mtx[10]
        if abs(fx) < 1e-3 and abs(fz) < 1e-3:
            return (pos[0], pos[1], pos[2] - 10.0)
        return (pos[0] + fx * 10.0, pos[1] + fy * 10.0, pos[2] + fz * 10.0)

    def resolve_pose(self, camera, chain, chain_t, target, target_chain, target_t, fov):
        if camera is None:
            return None
        if chain is not None and chain.nodes:
            pos = chain.sample(chain_t)
        else:
            pos = _raw_pos(camera)
        if pos is None:
            return None
        lookat = None
        if target is not None:
            if target_chain is not None and target_chain.nodes:
                lookat = target_chain.sample(target_t)
            else:
                lookat = _obj_pos(target)
        if lookat is None:
            if chain is not None and chain.nodes:
                ahead = chain.sample(chain_t + 0.5)
                if ahead != pos:
                    lookat = ahead
            if lookat is None:
                lookat = self.aim_from_matrix(camera, pos)
        if (abs(lookat[0] - pos[0]) < 1e-3 and abs(lookat[1] - pos[1]) < 1e-3
                and abs(lookat[2] - pos[2]) < 1e-3):
            lookat = (pos[0], pos[1], pos[2] - 10.0)
        return pos, lookat, fov, 0.0

    def camera_pose(self):
        if self._camera is None or self._camera.deleted:
            return None
        # Re-read the pointers each frame so edits take effect immediately.
        wp = getattr(self._camera, "mCurrentWP", None)
        if wp is None:
            self._chain = None
        elif self._chain is None or not self._chain.nodes or _obj_pos(wp) != self._chain.nodes[0][0]:
            self._chain = WaypointChain(wp)
        target = getattr(self._camera, "mTarget", None)
        if target is not None and target.type == "cWaypoint":
            self._target_chain = WaypointChain(target)
        else:
            self._target_chain = None
        # At rest the camera sits where it is placed in the level (matching the
        # rendered camera model); it only moves onto its waypoint rail during
        # playback/scrubbing. In-game, CameraSetWaypoint re-rails it the same way.
        use_chain = self._chain if (self._playing or self._t > 0.0) else None
        return self.resolve_pose(self._camera, use_chain, self._t,
                                 target, self._target_chain, self._t,
                                 self.camera_fov(self._camera))

    def cutscene_pose(self):
        cutscene = self._active_cutscene
        cam, wp, wp_t, target, target_t, fov_override = cutscene.state_at(self._t)
        if cam is None:
            return None
        # The level XML holds each camera's initial rail/target; the script overrides them.
        if wp is None:
            wp = getattr(cam, "mCurrentWP", None)
        if target is None:
            target = getattr(cam, "mTarget", None)
        chain = WaypointChain(wp) if wp is not None else None
        target_chain = None
        if target is not None and target.type == "cWaypoint":
            target_chain = WaypointChain(target)
        fov = fov_override if fov_override is not None else self.camera_fov(cam)
        pose = self.resolve_pose(cam, chain, wp_t, target, target_chain, target_t, fov)
        if pose is None:
            return None
        pos, lookat, fov, _ = pose
        return pos, lookat, fov, cutscene.fade_at(self._t)

    # ------------------------------------------------------------------ playback

    def toggle_play(self):
        if self._playing:
            self.stop_play()
            return
        self.check_level()
        start_time = 0.0
        if self._active_cutscene is None and self._camera is not None:
            # Playing a camera that a cutscene script uses runs that cutscene
            # from this camera's first shot, so scripted units move as well.
            for cutscene in self._cutscenes:
                if self._camera in cutscene.camera_first_time:
                    self._active_cutscene = cutscene
                    start_time = cutscene.camera_first_time[self._camera]
                    index = self._cutscenes.index(cutscene) + 1
                    self.cutscene_box.blockSignals(True)
                    self.cutscene_box.setCurrentIndex(index)
                    self.cutscene_box.blockSignals(False)
                    break
        if self._active_cutscene is not None:
            self._duration = self._active_cutscene.duration
            self.build_unit_routes()
        elif self._camera is not None:
            if self._chain is not None and self._chain.nodes:
                self._duration = self._chain.duration + TAIL_TIME
                if self._chain.cycle_start is not None:
                    self._duration = float("inf")
            else:
                # Static camera: still play so the transport visibly works.
                self._duration = STATIC_SHOT_TIME
        else:
            self.header.setText("Select a cCamera (or pick a cutscene) first")
            return
        self._t = start_time
        self._playing = True
        import lib.BattalionXMLLib as bwxml
        bwxml.HEIGHT_CACHE_ENABLED = True
        self.button_play.setText("Stop")
        self.timer.start()

    def stop_play(self):
        self._playing = False
        import lib.BattalionXMLLib as bwxml
        bwxml.HEIGHT_CACHE_ENABLED = False
        self.timer.stop()
        self.button_play.setText("Play")
        if self.editor.level_view is not None:
            self.clear_main_view_overrides()

    def gather_movement(self):
        """Movement/kill commands for the active cutscene: everything from its
        own script, plus the unconditional top-level commands of every other
        level script (all scripts start together at level load in-game)."""
        follows = [entry[:5] for entry in self._active_cutscene.follows]
        kills = [entry[:2] for entry in self._active_cutscene.kills]
        for timeline in self._all_timelines:
            if timeline is self._active_cutscene:
                continue
            follows.extend(entry[:5] for entry in timeline.follows if not entry[5])
            kills.extend(entry[:2] for entry in timeline.kills if not entry[2])
        follows.sort(key=lambda entry: entry[0])
        kills.sort(key=lambda entry: entry[0])
        return follows, kills

    def build_unit_routes(self):
        """Turn the scripted movement calls (FollowWaypoint, GoToArea) into
        per-unit routes. A later order for the same unit starts where the
        previous route put the unit at that moment."""
        self._unit_routes = {}
        follows, self._merged_kills = self.gather_movement()
        bwterrain = self.editor.level_view.bwterrain
        for time, unit, kind, data, speed in follows:
            objid = unit.id
            routes = self._unit_routes.setdefault(objid, [])
            if routes:
                start_pos, _ = routes[-1].sample(time)
            else:
                start_pos = _obj_pos(unit)
            if start_pos is None:
                continue
            if kind == "wp":
                points = [node[0] for node in WaypointChain(data).nodes]
            else:
                x, z = data
                y = start_pos[1]
                if bwterrain is not None and unit.type != "cAirVehicle":
                    terrain_y = bwterrain.check_height(x, z)
                    if terrain_y is not None:
                        y = terrain_y
                points = [(x, y, z)]
            if not points:
                continue
            routes.append(UnitRoute(time, start_pos, points, speed))

    def unit_overrides(self):
        """objid -> (pos, direction) for scripted units at the current time."""
        if self._active_cutscene is None or not self._unit_routes:
            return {}
        overrides = {}
        for objid, routes in self._unit_routes.items():
            active = None
            for route in routes:
                if route.start_time <= self._t:
                    active = route
            if active is not None:
                overrides[objid] = active.sample(self._t)
        return overrides

    def killed_units(self):
        """Object ids the scripts have removed (Kill) by the current time."""
        if self._active_cutscene is None:
            return set()
        return set(obj.id for time, obj in self._merged_kills if time <= self._t)

    def perf_note(self, name, seconds):
        stats = getattr(self, "_perf", None)
        if stats is None:
            stats = self._perf = {}
        total, count, worst = stats.get(name, (0.0, 0, 0.0))
        stats[name] = (total + seconds, count + 1, max(worst, seconds))

    def tick(self):
        import time
        tick_start = time.perf_counter()
        last = getattr(self, "_last_tick", None)
        if last is not None:
            # Scheduled every 33ms; a big gap = the main thread is blocked
            # (by main-view painting), which IS the perceived lag.
            self.perf_note("tick_gap", tick_start - last)
        self._last_tick = tick_start
        self._t += self.timer.interval() / 1000.0
        if self._t >= self._duration:
            self.stop_play()
        if self._tick_count % 6 == 0:  # label relayout at 10Hz is plenty
            self.update_header()
        # The static-scene display list brought preview paints to ~4ms, so the
        # preview runs at the full 60fps tick rate now.
        if self.isVisible():
            self.glview.update()
        override_start = time.perf_counter()
        self.apply_main_view_overrides()
        self.perf_note("overrides+redraw", time.perf_counter() - override_start)
        self.perf_note("tick_total", time.perf_counter() - tick_start)
        if self._tick_count % 90 == 0 and getattr(self, "_perf", None):
            print("CS-PERF " + "  ".join(
                "%s avg=%.1fms worst=%.1fms n=%d" % (k, v[0] / v[1] * 1000, v[2] * 1000, v[1])
                for k, v in self._perf.items()))
            self._perf = {}

    def apply_main_view_overrides(self):
        """Move the ACTUAL units in the main viewport during playback via the
        display-only mtxoverride (same mechanism as Dolphin live view) - the
        objects' real edit data is never modified."""
        # Main-view unit movement is disabled (performance): cutscene motion
        # renders in the preview only. The main viewport just refreshes the
        # camera marker on the spline overlay at a low rate.
        self._tick_count += 1
        if self._tick_count % 6 == 0:
            self.editor.level_view.do_redraw()

    def clear_main_view_overrides(self):
        lv = self.editor.level_view
        level = self.editor.level_file
        lv.cutscene_anim_override = False
        if level is not None:
            for objid in self._overridden:
                obj = level.objects.get(objid)
                if obj is not None:
                    obj.set_mtx_override(None)
        self._overridden = set()
        lv.do_redraw(force=True)

    def navigate(self, delta):
        self.check_level()
        if self._active_cutscene is not None:
            # Jump between the cutscene's shots.
            shots = self._active_cutscene.shots
            current = 0
            for i, start in enumerate(shots):
                if self._t >= start:
                    current = i
            self._t = shots[(current + delta) % len(shots)]
        else:
            cameras = [obj for obj in self.editor.level_file.objects.values()
                       if obj.type == "cCamera"] if self.editor.level_file else []
            if not cameras:
                return
            if self._camera in cameras:
                index = cameras.index(self._camera) + delta
            else:
                index = 0 if delta > 0 else -1
            self.set_camera(cameras[index % len(cameras)])
        self.update_header()
        self.glview.update()

    # ------------------------------------------------------------------ overlay

    def overlay_state(self):
        """State for the main-viewport spline overlay (plugin_camera_preview_overlay):
        {"poschain": [...], "aimchain": [...], "campos": ..., "lookat": ...}
        in BW world coords, or None when inactive. Cached per playback time -
        the main view repaints more often than the state changes."""
        cache = getattr(self, "_overlay_cache", None)
        if cache is not None and cache[0] == (self._t, id(self._camera), id(self._active_cutscene)):
            return cache[1]
        state = self._overlay_state_uncached()
        self._overlay_cache = ((self._t, id(self._camera), id(self._active_cutscene)), state)
        return state

    def _overlay_state_uncached(self):
        try:
            if self.editor.level_file is None:
                return None
            if self._active_cutscene is not None:
                cam, wp, wp_t, target, target_t, fov = self._active_cutscene.state_at(self._t)
                if cam is None:
                    return None
                if wp is None:
                    wp = getattr(cam, "mCurrentWP", None)
                if target is None:
                    target = getattr(cam, "mTarget", None)
                chain = WaypointChain(wp) if wp is not None else None
                target_chain = None
                if target is not None and target.type == "cWaypoint":
                    target_chain = WaypointChain(target)
                pose = self.cutscene_pose()
            elif self._camera is not None and not self._camera.deleted:
                pose = self.camera_pose()
                chain, target_chain = self._chain, self._target_chain
            else:
                return None
            if pose is None:
                return None
            pos, lookat, fov, fade = pose
            return {
                "poschain": [node[0] for node in chain.nodes] if chain is not None else [],
                "aimchain": [node[0] for node in target_chain.nodes] if target_chain is not None else [],
                "campos": pos,
                "lookat": lookat,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------ ui

    def update_header(self):
        if self._active_cutscene is not None:
            cutscene = self._active_cutscene
            shot = 0
            for i, start in enumerate(cutscene.shots):
                if self._t >= start:
                    shot = i
            self.header.setText("{0} - shot {1}/{2} - {3:.1f}s/{4:.1f}s".format(
                cutscene.name, shot + 1, len(cutscene.shots), self._t, cutscene.duration))
        elif self._camera is not None:
            text = self._camera.name
            if self._playing:
                text += " - {0:.1f}s".format(self._t)
            self.header.setText(text)
        else:
            self.header.setText("Camera Preview: no camera selected")
