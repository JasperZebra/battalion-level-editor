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
    def __init__(self, start_time, start_pos, points, speed, fixed_dir=None):
        self.fixed_dir = fixed_dir
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
        if self.fixed_dir is not None:
            direction = self.fixed_dir
        elif length < 1e-5:
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


def schedule_messages(raw_messages, clears, background=None):
    """Game-accurate global message queue: back-to-back playback in call
    order; ClearMessageQueue drops not-yet-shown entries. Background-script
    messages (approximate clocks) append AFTER the cutscene's own dialogue
    and never clear the queue."""
    scheduled = []
    queue_end = 0.0
    items = sorted([("m",) + msg[:5] for msg in raw_messages]
                   + [("c", t) for t, cond in clears], key=lambda e: e[1])
    for item in items:
        if item[0] == "c":
            t = item[1]
            scheduled = [s for s in scheduled if s[0] <= t]
            queue_end = max([t] + [s[0] + s[2] for s in scheduled if s[0] <= t])
        else:
            _, t, msgid, dur, sprite, army = item
            start = max(t, queue_end)
            scheduled.append((start, msgid, dur, sprite, army))
            queue_end = start + dur
    for msg in sorted(background or [], key=lambda m: m[0]):
        t, msgid, dur, sprite, army = msg[:5]
        start = max(t, queue_end)
        scheduled.append((start, msgid, dur, sprite, army))
        queue_end = start + dur
    return scheduled


class CutsceneTimeline(object):
    """One Lua script's camera timeline: timed events + derived shot list."""
    RE_WAIT = re.compile(r"WaitFor\(\s*([\w.]+)\s*\)")
    RE_NUM_ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(-?[0-9.]+)\s*$")
    # The game blocks cutscene scripts on this until the dialogue queue drains.
    RE_MSGDRAIN = re.compile(r"until\s+GetNumItemsInMessageQueue")
    RE_SETCAM = re.compile(r"\bSetCamera\(\s*([\w.]+)\s*\)")
    RE_SETWP = re.compile(r"CameraSetWaypoint\(\s*([\w.]+)\s*,\s*([\w.]+)\s*\)")
    RE_SETTARGET = re.compile(r"CameraSetTarget\(\s*([\w.]+)\s*,\s*([\w.]+)\s*\)")
    RE_SETFOV = re.compile(r"CameraSetFOV\(\s*([\w.]+)\s*,\s*([0-9.]+)")
    RE_FADE = re.compile(r"CameraFade\(\s*constant\.(FADE_IN|FADE_OUT)\s*,\s*constant\.(WAIT|NO_WAIT)\s*,\s*([0-9.]+)")
    RE_FOLLOW = re.compile(r"FollowWaypoint\(\s*([\w.]+)\s*,\s*([\w.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)")
    RE_FOLLOWUNIT = re.compile(r"FollowUnit\(\s*([\w.]+)\s*,\s*([\w.]+)\s*,")
    # Army arg: BW1 passes a plain integer, BW2 a constant.ARMY_* name.
    RE_PHONE = re.compile(r"PhoneMessage\(\s*(\d+)\s*,\s*[\w.]+\s*,\s*(?:(-?\d+)|constant\.ARMY_(\w+))\s*,\s*([0-9.]+)\s*,\s*([\w.]+)")
    RE_CLEARQ = re.compile(r"ClearMessageQueue\(")
    RE_GOTO = re.compile(r"GoToArea\(\s*([\w.]+)\s*,\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)")
    RE_TELEPORT = re.compile(r"\bTeleport\(\s*([\w.]+)\s*,\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)")
    RE_SPAWN = re.compile(r"\bSpawn\(\s*([\w.]+)\s*\)")
    RE_DESPAWN = re.compile(r"\bDespawn\(\s*([\w.]+)\s*\)")
    RE_KILL = re.compile(r"\bKill\(\s*([\w.]+)\s*\)")
    # Landing coordinates are literals or GetObjectX/ZPosition(Waypoint.Name) -
    # the waypoint name is statically present, so both resolve at parse time.
    _COORD = r"(-?[0-9.]+|GetObject[XZ]Position\(\s*[\w.]+\s*\))"
    RE_LANDAIR = re.compile(r"\bLandAirUnit\(\s*([\w.]+)\s*,\s*" + _COORD
                            + r"\s*,\s*" + _COORD
                            + r"(?:\s*,\s*[\w.]+\s*,\s*[\w.]+\s*,\s*([0-9.]+))?")
    RE_BEACH = re.compile(r"\bBeachWaterUnit\(\s*([\w.]+)\s*,\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)")
    RE_COORDWP = re.compile(r"GetObject[XZ]Position\(\s*([\w.]+)\s*\)")
    RE_ENTERVEH = re.compile(r"\bEnterVehicle\(\s*([\w.]+)\s*,\s*([\w.]+)")
    RE_PUTIN = re.compile(r"\bPutUnitInVehicle\(\s*([\w.]+)\s*,\s*([\w.]+)")
    RE_EXITVEH = re.compile(r"\bExitVehicle\(\s*([\w.]+)\s*,\s*([\w.]+)")
    GOTO_SPEED = 10.0

    RE_BLOCK_OPEN = re.compile(r"\b(?:if\b.*\bthen|while\b.*\bdo|for\b.*\bdo|function\b)")
    RE_BLOCK_CLOSE = re.compile(r"^\s*end\b")

    def __init__(self, name, text, resolve, owner=None, number_vars=None):
        self.name = name
        base_resolve = resolve
        number_vars = number_vars or {}

        def resolve(token):
            # In unit-attached scripts (mpScript), "owner" is the unit itself.
            return owner if token == "owner" else base_resolve(token)

        def coord(expr):
            m = self.RE_COORDWP.search(expr)
            if m is None:
                try:
                    return float(expr)
                except ValueError:
                    return None
            obj = resolve(m.group(1))
            pos = _obj_pos(obj) if obj is not None else None
            if pos is None:
                return None
            return pos[0] if "XPosition" in expr else pos[2]

        self.events = []   # (time, kind, data)
        self.fades = []    # (time, direction, duration)
        self.follows = []  # (time, unit_obj, "wp"|"area", wp_obj_or_xz, speed, conditional)
        self.kills = []    # (time, obj, conditional)
        self.spawns = []   # (time, obj, visible, conditional) - Spawn/Despawn
        self.vehicle_ops = []  # (time, "put"|"enter"|"exit", unit_or_None, veh_or_None, conditional)
        self.messages = []  # (start, msgid, duration, sprite, army) - queued popups
        self._msg_clears = []
        self.camera_first_time = {}  # camera obj -> earliest time it becomes active
        clock = 0.0
        msg_queue_end = 0.0
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
            m = self.RE_TELEPORT.search(line)
            if m is not None:
                unit = resolve(m.group(1))
                if unit is not None:
                    dest = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
                    self.follows.append((clock, unit, "tp", dest, 1e9, conditional))
            m = self.RE_DESPAWN.search(line)
            if m is not None:
                obj = resolve(m.group(1))
                if obj is not None:
                    self.spawns.append((clock, obj, False, conditional))
            else:
                m = self.RE_SPAWN.search(line)
                if m is not None:
                    obj = resolve(m.group(1))
                    if obj is not None:
                        self.spawns.append((clock, obj, True, conditional))
            m = self.RE_FOLLOWUNIT.search(line)
            if m is not None:
                unit, tgt = resolve(m.group(1)), resolve(m.group(2))
                if unit is not None and tgt is not None:
                    self.follows.append((clock, unit, "unit", tgt, 7.0, conditional))
            m = self.RE_LANDAIR.search(line)
            if m is not None:
                unit = resolve(m.group(1))
                x, z = coord(m.group(2)), coord(m.group(3))
                if unit is not None and x is not None and z is not None:
                    speed = float(m.group(4)) if m.group(4) else 10.0
                    self.follows.append((clock, unit, "land", (x, z), speed, conditional))
            m = self.RE_BEACH.search(line)
            if m is not None:
                unit = resolve(m.group(1))
                if unit is not None:
                    dest = (float(m.group(2)), float(m.group(3)))
                    self.follows.append((clock, unit, "land", dest, self.GOTO_SPEED, conditional))
            m = self.RE_PUTIN.search(line)
            if m is not None:
                unit, veh = resolve(m.group(1)), resolve(m.group(2))
                if unit is not None and veh is not None:
                    self.vehicle_ops.append((clock, "put", unit, veh, conditional))
            m = self.RE_ENTERVEH.search(line)
            if m is not None:
                unit, veh = resolve(m.group(1)), resolve(m.group(2))
                if unit is not None and veh is not None:
                    self.vehicle_ops.append((clock, "enter", unit, veh, conditional))
            m = self.RE_EXITVEH.search(line)
            if m is not None:
                # constant.ID_NONE as the unit = every passenger exits; as the
                # vehicle = the unit exits whatever it is currently inside.
                unit = None if m.group(1) == "constant.ID_NONE" else resolve(m.group(1))
                veh = None if m.group(2) == "constant.ID_NONE" else resolve(m.group(2))
                if unit is not None or veh is not None:
                    self.vehicle_ops.append((clock, "exit", unit, veh, conditional))
            m = self.RE_PHONE.search(line)
            if m is not None:
                dur = float(m.group(4))
                dur = dur if dur > 0 else 5.0
                sprite = resolve(m.group(5))
                army = int(m.group(2)) if m.group(2) is not None else m.group(3)
                self.messages.append((clock, int(m.group(1)), dur,
                                      sprite, army, conditional))
                msg_queue_end = max(clock, msg_queue_end) + dur
            if self.RE_CLEARQ.search(line):
                self._msg_clears.append((clock, conditional))
                msg_queue_end = clock
            if self.RE_MSGDRAIN.search(line):
                # repeat EndFrame() until GetNumItemsInMessageQueue(...) == 0:
                # the script stalls here while the queued dialogue plays out.
                clock = max(clock, msg_queue_end)
            m = self.RE_NUM_ASSIGN.match(line)
            if m is not None:
                number_vars[m.group(1)] = float(m.group(2))
            m = self.RE_WAIT.search(line)
            if m is not None:
                try:
                    clock += float(m.group(1))
                except ValueError:
                    clock += number_vars.get(m.group(1), 0.0)
        # Phone messages QUEUE in-game: stacked calls play back to back, each
        # for its own duration; ClearMessageQueue drops not-yet-shown ones.
        self.raw_messages = list(self.messages)
        self.messages = schedule_messages(self.raw_messages, self._msg_clears)
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
                    # FOV; the new camera falls back to its own XML state, and
                    # its rail clock starts at the CUT, not at cutscene start -
                    # otherwise fallback rails begin mid-flight or already done.
                    wp = target = fov = None
                    wp_set_time = target_set_time = time
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

        self.owner.ensure_phone_textures(lv.bwmodelhandler.textures)
        self._render_sky(lv, campos)
        self._render_terrain(lv)
        self._render_objects(lv, campos)
        self._render_water(lv)

        if fade > 0.001:
            self._render_fade(fade)

    def _render_sky(self, lv, campos):
        """Draw the level's skydome model camera-centered with no depth writes."""
        key = id(self.editor.level_file)
        if getattr(self, "_sky_key", None) != key:
            self._sky_key = key
            self._sky_name = None
            self._sky_params = (100.0, 0.5, 45.0)
            for obj in self.editor.level_file.objects.values():
                if obj.type == "cRenderParams":
                    dome = getattr(obj, "mpWorldSkydome", None)
                    name = getattr(dome, "mName", None)
                    if name and name in lv.bwmodelhandler.models:
                        self._sky_name = name
                    self._sky_params = (
                        getattr(obj, "mfSkydomeSize", 100.0) or 100.0,
                        getattr(obj, "mfSkydomeHeightFactorUp", 0.5) or 0.5,
                        getattr(obj, "mfSkydomeHeightHorizonPos", 45.0) or 45.0)
                    break
            if self._sky_name is None:
                self._sky_name = next(
                    (n for n in lv.bwmodelhandler.models if "skydome" in n.lower()), None)
        if self._sky_name is None:
            return
        try:
            glEnable(GL_TEXTURE_2D)
            glDisable(GL_ALPHA_TEST)
            glDisable(GL_CULL_FACE)  # dome faces point inward
            glEnable(GL_BLEND)       # sky textures (e.g. rainbows) use alpha
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            glDisable(GL_DEPTH_TEST)  # a skybox is never depth-culled
            import numpy
            size, up, horizon = self._sky_params
            model = lv.bwmodelhandler.models[self._sky_name]
            radius = max(getattr(model, "boundsphereradius", 35.0), 0.001)
            # Scale from the measured bound sphere so the dome always fits
            # inside the far plane regardless of the level's units.
            s = 3200.0 / radius
            mtx = numpy.array([s, 0, 0, 0,  0, s * up, 0, 0,  0, 0, s, 0,
                               campos[0], campos[1], campos[2], 1], dtype=numpy.float32)
            lv.bwmodelhandler.rendermodel(self._sky_name, mtx, None, 0)
        except Exception:
            if not getattr(self, "_sky_error", False):
                self._sky_error = True
                traceback.print_exc()
        finally:
            glDisable(GL_BLEND)
            glEnable(GL_DEPTH_TEST)
            glDepthMask(GL_TRUE)
            glEnable(GL_ALPHA_TEST)
            glDisable(GL_TEXTURE_2D)

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
        glAlphaFunc(GL_GEQUAL, 0.1)
        # Blend so semi-transparent texels render clear instead of black.
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        handler = lv.bwmodelhandler
        overrides = self.owner.unit_overrides()
        killed = self.owner.killed_units()
        # Everything that never moves (non-troops without an override) is
        # compiled once per level+route set into a single display list -
        # per-frame Python GL overhead was ~40ms/frame without this.
        vismenu = getattr(lv, "visibility_menu", None)
        full_scenery = vismenu is not None and vismenu.show_full_scenery()
        dynamic_ids = set(self.owner._unit_routes) | getattr(self.owner, "_spawn_actor_ids", set())
        static_key = (id(self.editor.level_file), frozenset(dynamic_ids),
                      self.owner._filter_gen, full_scenery)
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
        vismenu = getattr(self.editor.level_view, "visibility_menu", None)
        for objid, obj in self.editor.level_file.objects_with_positions.items():
            modelname = obj._modelname
            if (modelname is None or modelname not in handler.models
                    or objid in dynamic_ids):
                continue
            if vismenu is not None and not (vismenu.object_3d_visible(obj.type)
                                            and vismenu.object_visible(obj.type, obj)):
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
        # Full scenery: reuse the main view's SceneryHandler scatter (same
        # RNG-accurate distribution) when its toggle is on.
        if vismenu is not None and vismenu.show_full_scenery():
            try:
                scenery = self.editor.level_view.graphics.scenery
                scenery.set_scenery(self.editor.level_file, vismenu.object_visible,
                                    self.editor.level_file.is_bw2())
                bwterrain = self.editor.level_view.bwterrain
                for comp in scenery.components:
                    if comp.modeltype is None or comp.modeltype not in handler.models:
                        continue
                    currmtx = comp.mtx.mtx.copy()
                    if bwterrain is not None:
                        h = bwterrain.check_height(currmtx[12], currmtx[14])
                        if h is not None:
                            currmtx[13] = h
                    handler.rendermodel(comp.modeltype, currmtx, None, 0)
            except Exception:
                traceback.print_exc()

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
        self._merged_spawns = []
        self._spawn_actor_ids = set()
        self._parse_retries = 0
        self._overridden = set()       # objids with an active display override
        self._tick_count = 0
        self._filter_gen = 0           # bumped on visibility-filter changes
        self._filter_hooked = False

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

        # In-game phone message (CO transmission) overlay, like the game's UI.
        self.msg_label = QtWidgets.QLabel(self.glview)
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet(
            "background-color: rgba(10, 20, 35, 190); color: white;"
            "border: 1px solid rgba(120, 180, 255, 150); padding: 4px;"
            "font-size: 8pt;")
        self.msg_label.hide()
        self._strings = None
        self._strings_tried = False
        self._msg_current = None

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

    def on_filter_update(self):
        self._filter_gen += 1
        self.glview.update()

    def check_level(self):
        """Detect level load/reset and rebuild cutscene list + camera state."""
        # Mirror the main editor's visibility filters in the preview: the menu
        # exists after startup wiring, so hook its signal lazily.
        if not self._filter_hooked:
            menu = getattr(self.editor.level_view, "visibility_menu", None)
            if menu is not None:
                menu.filter_update.connect(self.on_filter_update)
                self._filter_hooked = True
        level = self.editor.level_file
        if level is self._level_ref:
            return
        self._level_ref = level
        self._strings = None
        self._strings_tried = False
        self._player_army = None
        self._phone_tex_done = set()
        self._phone_pixmaps = {}
        self._camera = None
        self._chain = None
        self._target_chain = None
        self._active_cutscene = None
        self._unit_routes = {}
        self._all_timelines = []
        self._merged_kills = []
        self._merged_spawns = []
        self._spawn_actor_ids = set()
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

        # Unit-attached scripts (mpScript -> cGameScriptResource) refer to
        # their unit as "owner"; map script name -> owning object.
        script_owner = {}
        for obj in level.objects.values():
            script = getattr(obj, "mpScript", None)
            if script is not None and getattr(script, "mName", None):
                script_owner.setdefault(script.mName, obj)

        cutscenes = []
        self._all_timelines = []
        try:
            paths = workbench.get_lua_script_paths()
        except Exception:
            return []
        texts = []
        for path in sorted(paths):
            try:
                with open(path, "r", errors="replace") as f:
                    texts.append((path, f.read()))
            except OSError:
                continue
        # Lua globals are shared across scripts: a delay variable may be
        # assigned in one script and consumed by WaitFor() in another.
        number_vars = {}
        for path, text in texts:
            for line in text.splitlines():
                m = CutsceneTimeline.RE_NUM_ASSIGN.match(line)
                if m is not None:
                    number_vars.setdefault(m.group(1), float(m.group(2)))
        for path, text in texts:
            # Every script is parsed: non-camera scripts still contribute
            # background unit movement to cutscene playback (the game runs
            # all scripts concurrently from level start).
            scriptname = os.path.splitext(os.path.basename(path))[0]
            timeline = CutsceneTimeline(
                scriptname, text, resolve, script_owner.get(scriptname),
                dict(number_vars))
            self._all_timelines.append(timeline)
            if timeline.valid:
                cutscenes.append(timeline)
        # The player's army = the one whose CO sends the most phone messages
        # across the whole level (the mission is narrated by your own CO).
        # Enemy transmissions get the mirrored BW2 box layout.
        counts = {}
        for timeline in self._all_timelines:
            for msg in timeline.raw_messages:
                counts[msg[4]] = counts.get(msg[4], 0) + 1
        self._player_army = max(counts, key=counts.get) if counts else None
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
        # The game's cameras never clip through the ground: ride above terrain.
        bwterrain = getattr(self.editor.level_view, "bwterrain", None)
        if bwterrain is not None:
            ground = bwterrain.check_height(pos[0], pos[2])
            if ground is not None and pos[1] < ground + 2.0:
                pos = (pos[0], ground + 2.0, pos[2])
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
        # Vehicle ops enter the same stream as pseudo-follows so boarding,
        # disembarking and movement are processed in one chronological pass.
        follows.extend((t, unit, op, veh, 0.0)
                       for t, op, unit, veh, cond in self._active_cutscene.vehicle_ops)
        for timeline in self._all_timelines:
            if timeline is self._active_cutscene:
                continue
            follows.extend(entry[:5] for entry in timeline.follows if not entry[5])
            follows.extend((t, unit, op, veh, 0.0)
                           for t, op, unit, veh, cond in timeline.vehicle_ops if not cond)
            kills.extend(entry[:2] for entry in timeline.kills if not entry[2])
        follows.sort(key=lambda entry: entry[0])
        kills.sort(key=lambda entry: entry[0])
        return follows, kills

    def build_unit_routes(self):
        """Turn the scripted movement calls (FollowWaypoint, GoToArea, Teleport,
        LandAirUnit/BeachWaterUnit and the vehicle boarding ops) into per-unit
        routes. A later order for the same unit starts where the previous route
        put the unit at that moment."""
        self._unit_routes = {}
        follows, self._merged_kills = self.gather_movement()
        # Dialogue comes from the cutscene's own script only (verified in-game:
        # background scripts' messages belong to gameplay, not the cutscene).
        self._merged_messages = None
        spawns = [entry[:3] for entry in self._active_cutscene.spawns]
        for timeline in self._all_timelines:
            if timeline is not self._active_cutscene:
                spawns.extend(e[:3] for e in timeline.spawns if not e[3])
        bwterrain = self.editor.level_view.bwterrain

        def pos_at(obj, t):
            active = None
            for route in self._unit_routes.get(obj.id, ()):
                if route.start_time <= t:
                    active = route
            return active.sample(t)[0] if active is not None else _obj_pos(obj)

        # Units listed in a vehicle's mPassenger array start the level inside
        # it: hidden until an ExitVehicle puts them on the ground.
        passengers = {}   # vehicle id -> [unit objs], boarding order
        in_vehicle = {}   # unit id -> vehicle obj
        extra_spawns = []
        if self.editor.level_file is not None:
            for obj in self.editor.level_file.objects.values():
                for passenger in getattr(obj, "mPassenger", None) or ():
                    if passenger is not None:
                        passengers.setdefault(obj.id, []).append(passenger)
                        in_vehicle[passenger.id] = obj
                        extra_spawns.append((0.0, passenger, False))
        exit_count = {}   # vehicle id -> how many already stepped out
        for time, unit, kind, data, speed in follows:
            if kind in ("put", "enter", "exit"):
                veh = data
                if kind == "put":
                    in_vehicle[unit.id] = veh
                    passengers.setdefault(veh.id, []).append(unit)
                    extra_spawns.append((time, unit, False))
                    continue
                if kind == "enter":
                    start_pos, vpos = pos_at(unit, time), pos_at(veh, time)
                    if start_pos is None or vpos is None:
                        continue
                    route = UnitRoute(time, start_pos, [vpos], 7.0)
                    self._unit_routes.setdefault(unit.id, []).append(route)
                    in_vehicle[unit.id] = veh
                    passengers.setdefault(veh.id, []).append(unit)
                    extra_spawns.append((time + route.total / route.speed, unit, False))
                    continue
                if unit is not None:
                    targets = [unit]
                    veh = veh if veh is not None else in_vehicle.get(unit.id)
                else:
                    targets = list(passengers.get(veh.id, ()))
                vpos = pos_at(veh, time) if veh is not None else None
                for exiting in targets:
                    base = vpos if vpos is not None else pos_at(exiting, time)
                    if base is None:
                        continue
                    idx = exit_count.get(veh.id, 0) if veh is not None else 0
                    if veh is not None:
                        exit_count[veh.id] = idx + 1
                    ang = math.radians(90.0 + idx * 45.0)
                    radius = 4.0 + 2.0 * (idx // 8)
                    x = base[0] + radius * math.sin(ang)
                    z = base[2] + radius * math.cos(ang)
                    y = base[1]
                    if bwterrain is not None:
                        terrain_y = bwterrain.check_height(x, z)
                        if terrain_y is not None:
                            y = terrain_y
                    direction = (math.sin(ang), math.cos(ang))
                    self._unit_routes.setdefault(exiting.id, []).append(
                        UnitRoute(time, (x, y, z), [(x, y, z)], 1e9, direction))
                    extra_spawns.append((time, exiting, True))
                    in_vehicle.pop(exiting.id, None)
                    if veh is not None and exiting in passengers.get(veh.id, ()):
                        passengers[veh.id].remove(exiting)
                continue
            objid = unit.id
            routes = self._unit_routes.setdefault(objid, [])
            if routes:
                start_pos, _ = routes[-1].sample(time)
            else:
                start_pos = _obj_pos(unit)
            if start_pos is None:
                continue
            fixed_dir = None
            if kind == "tp":
                x, z, yaw = data
                rad = math.radians(yaw)
                fixed_dir = (math.sin(rad), math.cos(rad))
                y = start_pos[1]
                if bwterrain is not None:
                    ty = bwterrain.check_height(x, z)
                    if ty is not None:
                        y = ty
                points = [(x, y, z)]
            elif kind == "wp":
                points = [node[0] for node in WaypointChain(data).nodes]
            elif kind == "unit":
                # Trail the target: head to where it is now, then where it ends.
                troutes = self._unit_routes.get(data.id)
                if troutes:
                    points = [troutes[-1].sample(time)[0], troutes[-1].points[-1]]
                else:
                    tpos = _obj_pos(data)
                    points = [tpos] if tpos is not None else []
            elif kind == "land":
                # LandAirUnit/BeachWaterUnit: touch down ON the terrain even
                # for air/naval units (unlike GoToArea, which keeps altitude).
                x, z = data
                y = start_pos[1]
                if bwterrain is not None:
                    terrain_y = bwterrain.check_height(x, z)
                    if terrain_y is not None:
                        y = terrain_y
                points = [(x, y, z)]
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
            routes.append(UnitRoute(time, start_pos, points, speed, fixed_dir))
        spawns.extend(extra_spawns)
        spawns.sort(key=lambda e: e[0])
        self._merged_spawns = spawns
        self._spawn_actor_ids = set(obj.id for t, obj, vis in spawns)

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
        """Object ids hidden at the current time: Kill victims plus Despawned
        units (a unit whose FIRST event is Spawn starts hidden)."""
        if self._active_cutscene is None:
            return set()
        hidden = set(obj.id for time, obj in self._merged_kills if time <= self._t)
        state = {}
        for time, obj, visible in getattr(self, "_merged_spawns", []):
            if obj.id not in state:
                state[obj.id] = not visible  # before first event: opposite
            if time <= self._t:
                state[obj.id] = visible
        hidden.update(objid for objid, visible in state.items() if not visible)
        return hidden

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
            self.update_message()
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
        # renders in the preview only. The main viewport repaints (no scene
        # rebuild - cheap) at 30Hz so the camera marker glides along the spline.
        self._tick_count += 1
        if self._tick_count % 2 == 0:
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

    def message_text(self, msgid):
        """Resolve a PhoneMessage id through the level's .str strings file."""
        if not self._strings_tried:
            self._strings_tried = True
            try:
                from plugins.strings_editor.strings import BWLanguageFile
                path = self.editor.file_menu.get_strings_path("English")
                with open(path, "rb") as f:
                    self._strings = BWLanguageFile(f)
            except Exception:
                self._strings = None
        if self._strings is not None:
            try:
                return self._strings.get_message(msgid).get_message()
            except Exception:
                pass
        return "[Transmission #{0}]".format(msgid)

    def sprite_texture_name(self, sprite_obj):
        """cScriptSprite -> cSprite -> sSpriteBasetype -> texture resource name."""
        if sprite_obj is None:
            return None
        seen = [sprite_obj]
        for _ in range(3):
            nxt = []
            for node in seen:
                for ref in getattr(node, "references", []) or []:
                    if ref.type == "cTextureResource":
                        return getattr(ref, "mName", None)
                    nxt.append(ref)
            seen = nxt
        return None

    def phone_texture(self, name):
        """Decoded PNG (from the editor's texture cache) as QPixmap, or None.
        The GL paint path pre-caches names via ensure_phone_textures."""
        if not name:
            return None
        cache = getattr(self, "_phone_pixmaps", None)
        if cache is None:
            cache = self._phone_pixmaps = {}
        key = name.lower()
        if key not in cache:
            path = os.path.join("texture_cache", key + ".png")
            cache[key] = QtGui.QPixmap(path) if os.path.exists(path) else None
        return cache[key]

    def ensure_phone_textures(self, texarchive):
        """Called from the preview GL paint (context current): force-decode the
        phone UI textures into the PNG cache. Retries per name so portraits of
        a cutscene chosen AFTER the first paint still get cached."""
        done = getattr(self, "_phone_tex_done", None)
        if done is None:
            done = self._phone_tex_done = set()
        if self.editor.level_file is not None and self.editor.level_file.bw2:
            names = ["CO_DIALOGUE_left", "CO_DIALOGUE_mid", "CO_DIALOG_rt",
                     "CO_DIALOG_lft_hi", "CODIALOGUEflash"]
        else:
            names = ["CO_DIALOGUE_01", "CO_DIALOGUE_02", "CO_box_lightning"]
        if self._active_cutscene is not None:
            for entry in self._active_cutscene.messages:
                tex = self.sprite_texture_name(entry[3])
                if tex:
                    names.append(tex)
        for name in names:
            key = name.lower()
            if key in done:
                continue
            try:
                texarchive.get_texture(key)
            except Exception:
                pass
            done.add(key)
            self._phone_pixmaps.pop(key, None)  # retry pixmap load from cache

    def update_message(self):
        """Show the active PhoneMessage over the preview, game-accurate:
        CO_DIALOGUE_01 atlas box at the TOP of the screen with the CO portrait
        (see decomp/phone_message_gui_analysis.md)."""
        active = None
        if self._active_cutscene is not None and (self._playing or self._t > 0.0):
            msgs = getattr(self, "_merged_messages", None) or self._active_cutscene.messages
            for entry in msgs:
                if entry[0] <= self._t < entry[0] + entry[2]:
                    active = entry
        portrait_ok = (active is not None and
                       self.phone_texture(self.sprite_texture_name(active[3])) is not None)
        # Lightning: one 7-frame pass when the message opens, no loop. BW1's
        # sheet plays at 10fps; BW2's sprite declares frameTime 0.075s
        # (13.3fps, SP_1.1 cPanelSprites mCOLightening).
        if active is not None:
            fps = 13.3 if (self.editor.level_file is not None
                           and self.editor.level_file.bw2) else 10.0
            frame = int((self._t - active[0]) * fps)
            self._spark_frame = frame if 0 <= frame <= 6 else None
        else:
            self._spark_frame = None
        key = None if active is None else (active[1], self.glview.width(), portrait_ok,
                                           self._spark_frame)
        if key != self._msg_current:
            self._msg_current = key
            if active is None:
                self.msg_label.hide()
            else:
                pixmap = self.compose_phone_box(self.message_text(active[1]),
                                                self.sprite_texture_name(active[3]),
                                                active[4], self._spark_frame)
                if pixmap is not None:
                    self.msg_label.setStyleSheet("background: transparent;")
                    self.msg_label.setPixmap(pixmap)
                    # Box origin in 640x480 screen space: BW1 sits at
                    # (150.5, 37.5); BW2 boxes hug the top-left corner.
                    if self.editor.level_file is not None and self.editor.level_file.bw2:
                        origin_x, origin_y = 12.0, 26.0
                    else:
                        origin_x, origin_y = 150.5, 37.5
                    self.msg_label.setGeometry(int(self.glview.width() * origin_x / 640.0),
                                               int(self.glview.height() * origin_y / 480.0),
                                               pixmap.width(), pixmap.height())
                else:
                    self.msg_label.setStyleSheet(
                        "background-color: rgba(10, 20, 35, 190); color: white;"
                        "border: 1px solid rgba(120, 180, 255, 150); padding: 4px;"
                        "font-size: 8pt;")
                    self.msg_label.setText(self.message_text(active[1]))
                    self.msg_label.setGeometry(6, 4, max(self.glview.width() - 12, 50), 52)
                self.msg_label.show()
                self.msg_label.raise_()  # text/box always on top of the preview

    # BW1 per-army HUD tint (cHUDVariables m*RadarColour), multiplied onto the
    # frame; BW1 scripts pass the army as an integer (WF, XY, TU, SE, UW).
    # BW2 boxes are NOT army-coloured (verified against in-game screenshots):
    # every faction gets the same neutral translucent bar.
    ARMY_TINTS = {0: (120, 170, 80), 1: (75, 110, 125), 2: (198, 50, 50),
                  3: (245, 208, 80), 4: (144, 112, 144)}

    def compose_phone_box(self, text, portrait_name, army=0, spark_frame=0):
        """Assemble the CO dialogue box from the CO_DIALOGUE_01 atlas crops,
        mapped in 640x480 screen space per axis so proportions match the game
        at any preview aspect. Returns None if textures aren't cached yet."""
        if self.editor.level_file is not None and self.editor.level_file.bw2:
            return self.compose_phone_box_bw2(text, portrait_name, army, spark_frame)
        atlas = self.phone_texture("CO_DIALOGUE_01")
        if atlas is None or atlas.isNull():
            return None
        sx = self.glview.width() / 640.0
        sy = self.glview.height() / 480.0
        w = int(473.5 * sx)
        h = int(146 * sy)
        sm = QtCore.Qt.TransformationMode.SmoothTransformation
        # Frame layer: left cap + stretched middle + portrait frame, tinted by
        # the army colour (masked by its own alpha so nothing bleeds).
        frame = QtGui.QPixmap(max(w, 1), max(h, 1))
        frame.fill(QtCore.Qt.GlobalColor.transparent)
        fp = QtGui.QPainter(frame)
        left = atlas.copy(0, 2, 29, 97).scaled(int(29 * sx), int(97 * sy), transformMode=sm)
        right = atlas.copy(63, 2, 128, 146).scaled(int(128 * sx), int(146 * sy), transformMode=sm)
        mid_w = w - left.width() - right.width()
        # Atlas rects are (x0,y0,x1,y1): middle strip is 32..60 = 28px wide.
        middle = atlas.copy(32, 2, 28, 97).scaled(max(mid_w, 1), left.height(), transformMode=sm)
        fp.drawPixmap(0, 0, left)
        fp.drawPixmap(left.width(), 0, middle)
        fp.drawPixmap(w - right.width(), 0, right)
        fp.end()
        tint = self.ARMY_TINTS.get(army)
        if tint is not None:
            # Capture the untinted frame as the alpha mask BEFORE tinting.
            mask = QtGui.QPixmap(frame)
            fp = QtGui.QPainter(frame)
            fp.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Multiply)
            fp.fillRect(0, 0, w, h, QtGui.QColor(*tint))
            fp.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_DestinationIn)
            fp.drawPixmap(0, 0, mask)
            fp.end()
        # Final composite: portrait BEHIND the frame (the frame's glass area is
        # translucent and overlays the face, like in-game), then the frame, text.
        out = QtGui.QPixmap(max(w, 1), max(h, 1))
        out.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(out)
        portrait = self.phone_texture(portrait_name)
        if portrait is not None and not portrait.isNull():
            pw, ph = int(64 * sx), int(80 * sy)
            # Portrait center: spec 404.5, visually tuned to 403.5.
            painter.drawPixmap(int(403.5 * sx - pw / 2), int(51.5 * sy - ph / 2),
                               portrait.scaled(pw, ph, transformMode=sm))
        painter.drawPixmap(0, 0, frame)
        # CO_DIALOGUE_02: the glass/highlight overlay, mapped over the whole
        # box with the same three-crop layout as the frame atlas.
        glass = self.phone_texture("CO_DIALOGUE_02")
        if glass is not None and not glass.isNull():
            g_left = glass.copy(0, 2, 29, 97).scaled(left.width(), left.height(),
                                                     transformMode=sm)
            g_mid = glass.copy(32, 2, 28, 97).scaled(middle.width(), middle.height(),
                                                     transformMode=sm)
            g_right = glass.copy(63, 2, 128, 146).scaled(right.width(), right.height(),
                                                         transformMode=sm)
            painter.drawPixmap(0, 0, g_left)
            painter.drawPixmap(left.width(), 0, g_mid)
            painter.drawPixmap(w - right.width(), 0, g_right)
        # Lightning flip-book (CO_box_lightning, 3x3 sheet, 7 frames) at the
        # frame corner, center (560,155) screen => (409.5,117.5) box, 2.5x.
        spark = self.phone_texture("CO_box_lightning")
        if spark_frame is not None and spark is not None and not spark.isNull():
            cw, ch = spark.width() // 3, spark.height() // 3
            fx, fy = spark_frame % 3, spark_frame // 3
            cell = spark.copy(fx * cw, fy * ch, cw, ch).scaled(
                int(cw * 2.5 * sx), int(ch * 2.5 * sy), transformMode=sm)
            painter.drawPixmap(int(409.5 * sx - cell.width() / 2),
                               int(117.5 * sy - cell.height() / 2), cell)
        painter.setPen(QtGui.QColor(255, 255, 255))  # CO text is always white
        font = QtGui.QFont()
        font.setPixelSize(max(int(14 * sy), 9))
        font.setBold(True)
        painter.setFont(font)
        # Game text rect (screen 183..492 x, 48..126 y) relative to box origin.
        painter.drawText(QtCore.QRect(int(32.5 * sx), int(10.5 * sy),
                                      int(309 * sx), int(78 * sy)),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                         | Qt.TextFlag.TextWordWrap, text)
        painter.end()
        return out

    def compose_phone_box_bw2(self, text, portrait_name, army=0, spark_frame=0):
        """BW2's CO message, measured off in-game SP_1.1 screenshots
        (Pictures/Screenshots 2026-07-23 151544/151614/151629): a neutral
        translucent bar (same for every faction), the CO medallion on the LEFT
        for the player's army and on the RIGHT for enemy transmissions (bar
        first, rounded cap on the outer end). The disc texture is drawn WHOLE
        (its sSpriteBasetype UVs are stale atlas coords; cropping at 69 slices
        the ring), kept circular at 76x76. The CO head is drawn 1.2x the ring
        diameter, bottom-aligned with the ring's bottom rim, unclipped - in
        game Windsor's hat rises above the ring. The glass-shine arc
        (CO_DIALOG_lft_hi) overlays the disc under the head. Text is white
        with a dark outline, starting 80px right of the disc center per
        cHUDVariables (mTextPos 105 vs mLeftSidePos 25)."""
        disc = self.phone_texture("CO_DIALOGUE_left")
        if disc is None or disc.isNull():
            return None
        enemy = (getattr(self, "_player_army", None) is not None
                 and army != self._player_army)
        sx = self.glview.width() / 640.0
        sy = self.glview.height() / 480.0
        w = int(500 * sx)
        h = int(97 * sy)
        # Full 80x80 disc texture drawn square (ring content dia ~77 of 80).
        disc_w, disc_h = int(76 * sx), int(76 * sy)
        disc_cx = (w - 62 * sx) if enemy else 62 * sx
        disc_cy = 56 * sy
        bar_h = int(64 * sy)      # native texture height, centered on the disc
        bar_y = int(disc_cy - bar_h / 2)
        cap_w = int(16 * sx)
        sm = QtCore.Qt.TransformationMode.SmoothTransformation
        out = QtGui.QPixmap(max(w, 1), max(h, 1))
        out.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(out)
        # Bar: mid gradient stretched from under the disc to the cap on the
        # outer end (cap mirrored for the enemy layout). Drawn twice - the
        # texture alpha is ~0.4 but the in-game bar reads closer to ~0.65.
        mid = self.phone_texture("CO_DIALOGUE_mid")
        cap = self.phone_texture("CO_DIALOG_rt")
        # The bar is FIXED - it does not follow the medallion. Its hidden end
        # sits at 66.5 (where the disc tucked over it in the original layout).
        tuck = int(66.5 * sx) if not enemy else int(w - 66.5 * sx)
        bar = QtGui.QPixmap(max(w, 1), max(h, 1))
        bar.fill(QtCore.Qt.GlobalColor.transparent)
        bp = QtGui.QPainter(bar)
        if enemy:
            if cap is not None and not cap.isNull():
                bp.drawPixmap(0, bar_y, cap.transformed(QtGui.QTransform().scale(-1, 1))
                              .scaled(cap_w, bar_h, transformMode=sm))
            if mid is not None and not mid.isNull():
                bp.drawPixmap(cap_w, bar_y, mid.scaled(
                    max(tuck - cap_w, 1), bar_h, transformMode=sm))
        else:
            if mid is not None and not mid.isNull():
                bp.drawPixmap(tuck, bar_y, mid.scaled(
                    max(w - tuck - cap_w, 1), bar_h, transformMode=sm))
            if cap is not None and not cap.isNull():
                bp.drawPixmap(w - cap_w, bar_y, cap.scaled(cap_w, bar_h, transformMode=sm))
        bp.end()
        painter.drawPixmap(0, 0, bar)
        painter.drawPixmap(0, 0, bar)
        # Layering: bar first, the ring above it, the glass-shine arc on the
        # ring, the CO head topmost (its hat/hair rises past the ring's top
        # in-game; the bottom edge lands on the ring's bottom rim).
        disc_pos = (int(disc_cx - disc_w / 2), int(disc_cy - disc_h / 2))
        painter.drawPixmap(*disc_pos, disc.scaled(disc_w, disc_h,
                                                  transformMode=sm))
        shine = self.phone_texture("CO_DIALOG_lft_hi")
        if shine is not None and not shine.isNull():
            painter.drawPixmap(*disc_pos, shine.scaled(disc_w, disc_h,
                                                       transformMode=sm))
        portrait = self.phone_texture(portrait_name)
        if portrait is not None and not portrait.isNull():
            # 64x80 head at 1.2x the ring dia, facing the text (source art
            # faces slightly left, so the friendly left-side head is mirrored).
            ph = int(84 * sy)
            pw = int(67.2 * sx)
            if not enemy:
                portrait = portrait.transformed(QtGui.QTransform().scale(-1, 1))
            painter.drawPixmap(int(disc_cx - pw / 2),
                               int(disc_cy + 30 * sy) - ph,
                               portrait.scaled(pw, ph, transformMode=sm))
        # Lightning flip-book (CODIALOGUEflash 16x16, 3x3 sheet of ~5px cells,
        # 7 frames) sparking at the medallion's outer top rim on message open.
        # Authored mLighteningScale is 2.5 - the cells are tiny in-game too.
        flash = self.phone_texture("CODIALOGUEflash")
        if spark_frame is not None and flash is not None and not flash.isNull():
            cw, ch = flash.width() // 3, flash.height() // 3
            fx, fy = spark_frame % 3, spark_frame // 3
            cell = flash.copy(fx * cw, fy * ch, cw, ch).scaled(
                max(int(cw * 2.5 * sx), 1), max(int(ch * 2.5 * sy), 1),
                transformMode=sm)
            flash_x = disc_cx + (-26 * sx if enemy else 26 * sx)
            painter.drawPixmap(int(flash_x - cell.width() / 2),
                               int(disc_cy - 26 * sy - cell.height() / 2), cell)
        # White text with a dark outline; the game letters in a hand-drawn
        # comic font (Chisel), Comic Sans is the closest stock match. Starts
        # 80px right of the disc center (mTextPos 105 - mLeftSidePos 25).
        font = QtGui.QFont("Comic Sans MS")
        font.setPixelSize(max(int(14 * sy), 9))
        font.setBold(True)
        painter.setFont(font)
        if enemy:
            rect = QtCore.QRect(int(20 * sx), bar_y, w - int((20 + 121) * sx), bar_h)
        else:
            rect = QtCore.QRect(int(121 * sx), bar_y, w - int((121 + 20) * sx), bar_h)
        flags = (int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                 | Qt.TextFlag.TextWordWrap)
        painter.setPen(QtGui.QColor(45, 45, 45))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            painter.drawText(rect.translated(dx, dy), flags, text)
        painter.setPen(QtGui.QColor(255, 255, 255))
        painter.drawText(rect, flags, text)
        painter.end()
        return out

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
