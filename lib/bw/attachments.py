"""Extra models that belong to a unit but are stored as SEPARATE models in the archive.

Two cases, both driven by real pointer fields on the object's base (no name guessing):

* **Ground vehicle tracks** -- `mpTreadTrackModelLeft` / `mpTreadTrackModelRight`. Tracks are
  authored in the hull's own model space, so they render with the hull's matrix unchanged.
* **Infantry accessories** -- `mHelmetModel` / `mWeaponModel` / `mBkPackModel`. These are
  authored in their ATTACH NODE's local frame, so they render at
  ``object matrix * attach node world matrix``.

The attach node is resolved from the body model's skeleton: BW2 nodes carry real bone names,
BW1 nodes are anonymous ("Node N"), so BW1 falls back to a signature table. There are only two
infantry rigs per game (verified across every level of both games: BW1 grunt 30 nodes / BW1+BW2
vet 31 nodes / BW2 grunt 46 nodes -- the vet rig is topologically IDENTICAL in both games), so
the table is exhaustive; the nearest-canonical-position fallback only covers modded rigs.

Node world matrices are composed exactly the way `model_rendering.make_textured_model` composes
them when it bakes vertices (node first, then ancestors, via `inplace_multiply_mat4`). That is
what keeps an accessory in the same space as the body mesh it sits on -- do not "correct" the
order here in isolation.
"""
import hashlib

from numpy import array, float32

from .vectors import Matrix4x4


# ---------------------------------------------------------------- object -> model names

# slot -> pointer field on the base object. Tracks use the hull matrix as-is; the other
# slots are placed at their attach node.
ATTACH_FIELDS = (
    ("track", "mpTreadTrackModelLeft"),
    ("track", "mpTreadTrackModelRight"),
    ("helmet", "mHelmetModel"),
    ("weapon", "mWeaponModel"),
    ("backpack", "mBkPackModel"),
)


def object_attachments(obj):
    """[(slot, modelname)] for an object. Reads the instance's base (cGroundVehicleBase /
    sTroopBase) when there is one, else the object itself (so bases render complete too)."""
    base = getattr(obj, "mBase", None)
    if base is None:
        base = obj

    result = []
    for slot, field in ATTACH_FIELDS:
        resource = getattr(base, field, None)
        if resource is None:
            continue
        name = getattr(resource, "mName", None)
        if name:
            result.append((slot, name))
    return result


# ---------------------------------------------------------------- attach node resolution

# BW2 skeletons name their bones. BONE_UB_R_GUN is the gun mount (its world transform equals
# BONE_R_HAND's); vet skeletons have no separate gun bone, so the hand is used.
BONE_NAMES = {
    "helmet": ("BONE_HELMET", "BONE_HEAD"),
    "weapon": ("BONE_UB_R_GUN", "BONE_R_HAND", "BONE_R_FINGER"),
    "backpack": ("BONE_BCK_MISC", "BONE_2_SPINE", "BONE_1_SPINE"),
}

# (nodecount, md5 of the parent-index array) -> {slot: node index}. Covers every infantry body
# model used by either game; the BW1 indices are the same bones as the BW2 names above.
RIG_ATTACH_NODES = {
    (30, "41705c8d"): {"helmet": 16, "weapon": 21, "backpack": 29},   # grunt rig, BW1
    (31, "144a11ab"): {"helmet": 15, "weapon": 22, "backpack": 13},   # vet rig, BW1 + BW2
    (46, "2f2f8ef0"): {"helmet": 16, "weapon": 30, "backpack": 45},   # grunt rig, BW2
}

# Last-resort fallback for an unknown (modded) rig: attach node world positions of a stock
# soldier, in model space. Only used when name and signature lookup both fail.
CANONICAL_POSITIONS = {
    "helmet": (0.0, 1.79, -0.02),
    "weapon": (-0.55, 1.02, 0.02),
    "backpack": (0.0, 1.34, 0.19),
}
CANONICAL_MAX_DISTANCE = 0.5


def _node_name(node):
    name = node.name
    if isinstance(name, bytes):
        name = name.split(b"\x00")[0].decode("ascii", "replace")
    return name.upper()


def _local_matrix(node):
    """Node local transform, built from the raw floats with the GAME's quaternion order
    (x, y, z, w) = floats[3:7). model_rendering.Transform still uses RenolY2's reversed order,
    which agrees for shallow/near-identity nodes but gives a different rotation per bone -- and
    a soldier's attach bones sit five joints deep, so the difference is what puts a helmet on
    the head instead of through it. Left alone there: it only matters for these chains."""
    floats = node.transform.floats
    x, y, z, w = floats[3], floats[4], floats[5], floats[6]
    mtx = Matrix4x4(
        1 - 2*y**2 - 2*z**2,  2*x*y + 2*w*z,        2*x*z - 2*w*y,        0.0,
        2*x*y - 2*w*z,        1 - 2*x**2 - 2*z**2,  2*y*z + 2*w*x,        0.0,
        2*x*z + 2*w*y,        2*y*z - 2*w*x,        1 - 2*x**2 - 2*y**2,  0.0,
        floats[0],            floats[1],            floats[2],            1.0)
    mtx.transpose()
    return mtx


def _node_world_matrix(node):
    """World transform of a node: root, then each descendant down to the node. Composing the
    other way round only matches when the ancestors are near identity -- it scatters deep
    hierarchies like a skeleton."""
    chain = []
    current = node
    while current is not None and len(chain) < 64:
        chain.append(current)
        current = current.parent

    mvmat = Matrix4x4.identity()
    for ancestor in reversed(chain):
        mvmat.inplace_multiply_mat4(_local_matrix(ancestor))
    return mvmat


def _flatten(mtx):
    """Matrix4x4 -> the flat 16 floats the instanced renderer wants (column major, translation
    at 12/13/14), matching BWMatrix's layout."""
    return [mtx.a1, mtx.a2, mtx.a3, mtx.a4,
            mtx.b1, mtx.b2, mtx.b3, mtx.b4,
            mtx.c1, mtx.c2, mtx.c3, mtx.c4,
            mtx.d1, mtx.d2, mtx.d3, mtx.d4]


def _rig_signature(model):
    indices = {id(node): i for i, node in enumerate(model.nodes)}
    parents = [str(indices.get(id(node.parent), -1)) if node.parent is not None else "-1"
               for node in model.nodes]
    digest = hashlib.md5(",".join(parents).encode("ascii")).hexdigest()[:8]
    return (len(model.nodes), digest)


def _by_name(model):
    byname = {}
    for i, node in enumerate(model.nodes):
        byname.setdefault(_node_name(node), i)

    found = {}
    for slot, candidates in BONE_NAMES.items():
        for candidate in candidates:
            if candidate in byname:
                found[slot] = byname[candidate]
                break
    return found


def _by_position(model, worlds, slot):
    x, y, z = CANONICAL_POSITIONS[slot]
    best, bestdist = None, None
    for i, mtx in enumerate(worlds):
        dist = ((mtx.d1 - x)**2 + (mtx.d2 - y)**2 + (mtx.d3 - z)**2)**0.5
        if bestdist is None or dist < bestdist:
            best, bestdist = i, dist
    if best is not None and bestdist <= CANONICAL_MAX_DISTANCE:
        return best
    return None


def attach_matrices(model):
    """{slot: flat 16-float matrix} for one parsed body model. Empty for anything that is not
    an infantry body (no matching bone names and no known rig signature)."""
    if not model.nodes:
        return {}

    nodes = _by_name(model)
    if len(nodes) < len(BONE_NAMES):
        for slot, index in RIG_ATTACH_NODES.get(_rig_signature(model), {}).items():
            if slot not in nodes and 0 <= index < len(model.nodes):
                nodes[slot] = index

    if not nodes:
        return {}

    worlds = None
    for slot in BONE_NAMES:
        if slot in nodes:
            continue
        if worlds is None:
            worlds = [_node_world_matrix(node) for node in model.nodes]
        index = _by_position(model, worlds, slot)
        if index is not None:
            nodes[slot] = index

    return {slot: _flatten(_node_world_matrix(model.nodes[index]))
            for slot, index in nodes.items()}


# ---------------------------------------------------------------- render-time composition

# The BW1 grunt rig (every faction) puts its helmet bone on the CROWN of the skull rather than
# inside the head, and its helmet models are modelled from the RIM up -- so dropping the helmet
# origin straight onto that bone leaves it hovering above the head. Vet rigs in both games sink
# the bone 0.17-0.53 into the head and are placed correctly as-is. Detect the crown-mounted case
# by comparing the attach height against the top of the body mesh (measured across every troop
# in both games: crown-mounted +0.09..+0.13, correct -0.17..-0.53), then seat the helmet by
# putting the TOP of its dome on the bone.
RIM_MOUNT_MARGIN = 0.10


def _corners(bounds):
    minx, miny, minz, maxx, maxy, maxz = bounds
    return [(x, y, z) for x in (minx, maxx) for y in (miny, maxy) for z in (minz, maxz)]


def _highest_point(matrix, bounds):
    return max(matrix[1]*x + matrix[5]*y + matrix[9]*z + matrix[13]
               for x, y, z in _corners(bounds))


def _seat_on_attach_point(matrix, bounds):
    """Lower the accessory so its highest point sits at the attach node instead of its origin."""
    drop = _highest_point(matrix, bounds) - matrix[13]
    if drop <= 0.0:
        return matrix
    seated = list(matrix)
    seated[13] -= drop
    return seated


def accessory_matrix(slot, attachmatrix, objectmatrix, bodybounds, accessorybounds):
    """Instance matrix for one accessory. `bodybounds`/`accessorybounds` are model space
    (minx, miny, minz, maxx, maxy, maxz) boxes, or None when unknown."""
    if (slot == "helmet" and bodybounds is not None and accessorybounds is not None
            and attachmatrix[13] >= bodybounds[4] - RIM_MOUNT_MARGIN):
        attachmatrix = _seat_on_attach_point(attachmatrix, accessorybounds)
    return combine(objectmatrix, attachmatrix)


def combine(objectmatrix, attachmatrix):
    """Object matrix * attach matrix, both flat column-major 16."""
    obj = array(objectmatrix, dtype=float32).reshape((4, 4), order="F")
    attach = array(attachmatrix, dtype=float32).reshape((4, 4), order="F")
    return obj.dot(attach).flatten("F")
