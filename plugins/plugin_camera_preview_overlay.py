from OpenGL.GL import *


# Draws the camera-preview splines in the main viewport (AM3D-editor style):
# the active preview camera's flight path (yellow), its look-at path (green),
# the camera->look-at aim line (red) with a marker at the camera's current
# position, and markers for units moved by the cutscene's FollowWaypoint calls
# (magenta). State comes from the Camera Preview panel in the Main side tab
# (widgets/camera_preview.py, editor.pik_control.camera_preview.overlay_state()).


def _vertex(p):
    # BW world (x, y=height, z) -> GL z-up render space (x, z, y).
    glVertex3f(p[0], p[2], p[1] + 0.5)


def _chain_lines(points, r, g, b, width):
    if len(points) < 2:
        return
    glColor4f(r, g, b, 1.0)
    glLineWidth(width)
    glBegin(GL_LINE_STRIP)
    for p in points:
        _vertex(p)
    glEnd()


def _markers(points, r, g, b, size):
    if not points:
        return
    glColor4f(r, g, b, 1.0)
    glPointSize(size)
    glBegin(GL_POINTS)
    for p in points:
        _vertex(p)
    glEnd()


class Plugin(object):
    def __init__(self):
        self.name = "Camera Preview Overlay"
        self.actions = []
        self.editor = None

    def plugin_init(self, editor):
        self.editor = editor

    def render_post(self, viewer):
        if self.editor is None:
            return
        preview = getattr(self.editor.pik_control, "camera_preview", None)
        if preview is None:
            return
        state = preview.overlay_state()
        if state is None:
            return

        glDisable(GL_TEXTURE_2D)
        glDisable(GL_ALPHA_TEST)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)

        _chain_lines(state["poschain"], 1.0, 0.85, 0.1, 3.0)          # flight path
        _markers(state["poschain"], 1.0, 0.85, 0.1, 7.0)
        _chain_lines(state["aimchain"], 0.2, 1.0, 0.3, 2.0)           # look-at path
        _markers(state["aimchain"], 0.2, 1.0, 0.3, 6.0)
        _chain_lines([state["campos"], state["lookat"]], 1.0, 0.2, 0.2, 1.5)  # aim line
        _markers([state["campos"]], 1.0, 0.4, 0.1, 11.0)              # camera position
        _markers([state["lookat"]], 1.0, 0.2, 0.2, 8.0)               # look-at point

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_ALPHA_TEST)

    def unload(self):
        pass
