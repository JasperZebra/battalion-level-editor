import math
import struct
import traceback
from io import BytesIO

import numpy
from OpenGL.GL import *

from lib.bw.model_rendering import BW1Model, BW2Model, NodeBW1, NodeBW2


# Skeletal animation for the camera preview: decodes MINA clips (port of the
# verified io_scene_bw implementation) and renders units with per-node
# animated transforms during cutscene playback. BW models are rigid-node
# (no vertex skinning), so posing the node hierarchy fully animates a unit.
#
# The static model pipeline flattens node hierarchies at load, so animated
# units re-parse their raw LDOM model from the resource archive (cached per
# model name). Geometry display lists are compiled with transforms neutralized
# (parents cut, apply_transform no-op'd) so the per-frame FK world matrix can
# be applied on the GL matrix stack around each node's list.

FPS = 30.0
_F16 = 3.0517578125e-05


def _decode_bw1_rot(s0, s1, s2):
    ox = ((s0 & 0x7FFF) - 16384) * 6.103515625e-05
    oy = ((s1 & 0x7FFF) - 16384) * 6.103515625e-05
    oz = (s2 - 32768) * _F16
    w2 = 1.0 - ox * ox - oy * oy - oz * oz
    ow = math.sqrt(w2) if w2 > 0.0 else 0.0
    if s0 >> 15:
        ow = -ow
    if s1 & 0x8000:
        ox, oy, oz, ow = -ox, -oy, -oz, -ow
    return (-ox, -oy, -oz, ow)


def _decode_bw2_rot(s0, s1, s2, s3):
    ox = ((s0 & 0x3FFF) << 1) * _F16
    oy = ((s1 & 0x3FFF) << 1) * _F16
    oz = (s2 & 0x7FFF) * _F16
    ow = (s3 & 0x7FFF) * _F16
    if s0 & 0x4000:
        ox = -ox
    if s1 & 0x4000:
        oy = -oy
    if s2 & 0x8000:
        oz = -oz
    if s3 & 0x8000:
        ow = -ow
    if (s1 >> 15) & 1:
        ox, oy, oz, ow = -ox, -oy, -oz, -ow
    return (-ox, -oy, -oz, ow)


class AnimBone(object):
    def __init__(self, name, weird_id, pos_keys, rot_keys):
        self.name = name
        self.weird_id = weird_id
        self.pos_keys = pos_keys
        self.rot_keys = rot_keys


def decode_mina(data, is_bw1):
    """Decode a MINA blob -> (bones, frame_count). Raises on malformed data."""
    rotsize = 6 if is_bw1 else 8
    last_error = None
    for bigendian in (is_bw1, not is_bw1):
        e = ">" if bigendian else "<"
        try:
            bonecount = struct.unpack_from(e + "I", data, 0x4C)[0]
            if not 0 < bonecount < 400:
                raise ValueError("bone count {0}".format(bonecount))
            base = 0x58
            bones = []
            total = 0
            for i in range(bonecount):
                off = base + i * 64
                name = data[off:off + 16].split(b"\x00")[0].decode("latin-1")
                poskf, rotkf = struct.unpack_from(e + "II", data, off + 0x10)
                if poskf > 100000 or rotkf > 100000:
                    raise ValueError("keyframe counts")
                deltas = struct.unpack_from(e + "fff", data, off + 0x20)
                mins = struct.unpack_from(e + "fff", data, off + 0x2C)
                weird_id = struct.unpack_from(e + "I", data, off + 0x3C)[0]
                bones.append((name, weird_id, poskf, rotkf, deltas, mins))
                total += poskf * 4 + rotkf * rotsize
            off = base + bonecount * 64
            if off + total > len(data) + 4:
                raise ValueError("keyframes exceed data")
            out = []
            frame_count = 1
            for name, weird_id, poskf, rotkf, deltas, mins in bones:
                if data[off:off + 2] == b"\xcd\xcd":
                    off += 2
                pos_keys = []
                for k in range(poskf):
                    fu = struct.unpack_from(">I", data, off)[0]
                    su = fu & 0xFFFF
                    pos_keys.append((((fu >> 21) & 0x7FF) * deltas[0] + mins[0],
                                     ((fu >> 10) & 0x7FF) * deltas[1] + mins[1],
                                     (su & 0x3FF) * deltas[2] + mins[2]))
                    off += 4
                rot_keys = []
                for k in range(rotkf):
                    if is_bw1:
                        s = struct.unpack_from(">HHH", data, off)
                        rot_keys.append(_decode_bw1_rot(*s))
                    else:
                        s = struct.unpack_from(">HHHH", data, off)
                        rot_keys.append(_decode_bw2_rot(*s))
                    off += rotsize
                out.append(AnimBone(name, weird_id, pos_keys, rot_keys))
                frame_count = max(frame_count, poskf, rotkf)
            return out, frame_count
        except Exception as exc:
            last_error = exc
    raise ValueError("MINA decode failed: {0}".format(last_error))


def _local_matrix(pos, quat):
    """Local node matrix from position + file-order quaternion (x,y,z,w),
    matching the model's static Transform convention (T @ R, column vectors)."""
    x, y, z, w = quat
    m = numpy.array([
        [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * w * z, 2 * x * z + 2 * w * y, pos[0]],
        [2 * x * y + 2 * w * z, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * w * x, pos[1]],
        [2 * x * z - 2 * w * y, 2 * y * z + 2 * w * x, 1 - 2 * x * x - 2 * y * y, pos[2]],
        [0.0, 0.0, 0.0, 1.0]], dtype=numpy.float64)
    return m


class AnimatedModel(object):
    def __init__(self, arc, modelname, is_bw1):
        res = arc.get_resource(b"LDOM", modelname)
        if res is None:
            raise KeyError(modelname)
        model = (BW1Model if is_bw1 else BW2Model)()
        # from_file() compiles display lists mid-parse with the bind transforms
        # baked in; suppress that so ensure_lists() can build geometry-only
        # lists after the transforms are neutralized below.
        nodecls = NodeBW1 if is_bw1 else NodeBW2
        orig_create = nodecls.create_displaylists
        nodecls.create_displaylists = lambda node_self: None
        try:
            model.from_file(BytesIO(res.data[8:]))
        finally:
            nodecls.create_displaylists = orig_create
        self.model = model
        self.nodes = model.nodes
        index_of = {id(node): i for i, node in enumerate(self.nodes)}
        self.parents = []
        self.bind_locals = []
        self.by_name = {}
        self.by_wid = {}
        for i, node in enumerate(self.nodes):
            parent = getattr(node, "parent", None)
            self.parents.append(index_of.get(id(parent), -1))
            floats = node.transform.floats
            self.bind_locals.append(_local_matrix(floats[0:3], floats[3:7]))
            name = getattr(node, "name", None)
            if isinstance(name, bytes):
                name = name.split(b"\x00")[0].decode("latin-1", errors="replace")
            if name:
                self.by_name.setdefault(name.lower(), i)
            wid = getattr(node, "unkshort1", None)
            if wid is not None:
                self.by_wid.setdefault(wid, i)
            # Neutralize baked transforms so display lists hold pure geometry;
            # the animated world matrix is applied on the matrix stack instead.
            node.parent = None
            node.transform.apply_transform = lambda: None
        self._lists_built = False

    def ensure_lists(self):
        if not self._lists_built:
            for node in self.nodes:
                node.create_displaylists()
            self._lists_built = True

    def bind_clip(self, bones, is_bw1):
        """node index -> AnimBone, by WeirdId (BW1) or node name (BW2)."""
        binding = {}
        for bone in bones:
            ni = None
            if not is_bw1 and bone.name:
                ni = self.by_name.get(bone.name.lower())
            if ni is None:
                ni = self.by_wid.get(bone.weird_id)
            if ni is not None and ni not in binding:
                binding[ni] = bone
        return binding

    def pose(self, binding, frame):
        worlds = [None] * len(self.nodes)
        for i in range(len(self.nodes)):
            local = self.bind_locals[i]
            bone = binding.get(i)
            if bone is not None and bone.rot_keys:
                quat = bone.rot_keys[min(frame, len(bone.rot_keys) - 1)]
                if bone.pos_keys:
                    pos = bone.pos_keys[min(frame, len(bone.pos_keys) - 1)]
                else:
                    pos = (local[0][3], local[1][3], local[2][3])
                local = _local_matrix(pos, quat)
            elif bone is not None and bone.pos_keys:
                local = local.copy()
                pos = bone.pos_keys[min(frame, len(bone.pos_keys) - 1)]
                local[0][3], local[1][3], local[2][3] = pos
            pi = self.parents[i]
            worlds[i] = worlds[pi] @ local if 0 <= pi < i and worlds[pi] is not None else local
        return worlds


class _TextureAdapter(object):
    """The legacy node renderer passes raw bytes material names; the texture
    archive expects clean lowercase strings. Bridge without touching lib/bw."""
    def __init__(self, texarchive):
        self.texarchive = texarchive

    def get_texture(self, name):
        try:
            if isinstance(name, bytes):
                name = name.split(b"\x00")[0].decode("latin-1", errors="replace")
            name = name.strip().lower()
            if not name:
                return (None, 0)
            return self.texarchive.get_texture(name)
        except Exception:
            return (None, 0)


class AnimationRenderer(object):
    """Per-level cache of animated models/clips + the animated draw call."""
    def __init__(self):
        self.models = {}    # modelname -> AnimatedModel | None (failed)
        self.clips = {}     # animname -> (bones, frame_count) | None
        self.bindings = {}  # (modelname, animname) -> {node index: AnimBone}
        self.poses = {}     # (modelname, animname, frame) -> worlds (shared!)
        self.no_anim = set()
        self._adapter = None

    def clear(self):
        self.models = {}
        self.clips = {}
        self.bindings = {}
        self.poses = {}
        self.no_anim = set()
        self._adapter = None

    def move_anim_name(self, obj):
        """The unit's movement clip: base -> mAnimationSet -> walk/run slot."""
        base = getattr(obj, "mBase", None)
        aset = getattr(base, "mAnimationSet", None)
        for slot in ("mWalkAnimation", "mRunAnimation", "mMoveAnimation"):
            res = getattr(aset, slot, None)
            name = getattr(res, "mName", None)
            if name:
                return name
        return None

    def render_animated(self, arc, textures, obj, modelname, placement, t, is_bw1):
        """Draw obj's model posed by its movement clip at time t under the
        already-applied placement matrix. Returns False to use the static path."""
        if arc is None or obj.id in self.no_anim:
            return False
        try:
            animname = self.move_anim_name(obj)
            if animname is None:
                self.no_anim.add(obj.id)
                return False
            if animname not in self.clips:
                res = arc.get_resource(b"MINA", animname)
                self.clips[animname] = decode_mina(res.data, is_bw1) if res is not None else None
            clip = self.clips[animname]
            if clip is None:
                self.no_anim.add(obj.id)
                return False
            if modelname not in self.models:
                try:
                    self.models[modelname] = AnimatedModel(arc, modelname, is_bw1)
                except Exception:
                    traceback.print_exc()
                    self.models[modelname] = None
            amodel = self.models[modelname]
            if amodel is None:
                return False
            key = (modelname, animname)
            if key not in self.bindings:
                self.bindings[key] = amodel.bind_clip(clip[0], is_bw1)
            binding = self.bindings[key]
            if not binding:
                self.no_anim.add(obj.id)
                return False
            amodel.ensure_lists()
            frame = int(t * FPS) % clip[1]
            # Units share rigs and clips (all grunts, all vets, ...): compute
            # each (model, clip, frame) pose once and reuse it for every unit.
            posekey = (modelname, animname, frame)
            worlds = self.poses.get(posekey)
            if worlds is None:
                worlds = amodel.pose(binding, frame)
                self.poses[posekey] = worlds
            if self._adapter is None or self._adapter.texarchive is not textures:
                self._adapter = _TextureAdapter(textures)

            glPushMatrix()
            # Same stack as the static path: y/z swap, then instance placement.
            glMultMatrixf([1.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 1.0, 0.0,
                           0.0, 1.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 1.0])
            glMultMatrixf(placement)
            for i, node in enumerate(amodel.nodes):
                if node.do_skip():
                    continue
                glPushMatrix()
                glMultMatrixf(numpy.asarray(worlds[i], dtype=numpy.float32).flatten(order="F"))
                node.render(self._adapter, None)
                glPopMatrix()
            glPopMatrix()
            return True
        except Exception:
            traceback.print_exc()
            self.no_anim.add(obj.id)
            return False
