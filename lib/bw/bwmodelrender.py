from functools import partial
from OpenGL.GL import *
from .model_rendering import BW1Model, BW2Model
from .bw_archive import BWArchive
from .texture import TextureArchive
from . import attachments
from lib.render.model_renderingv2 import BWModelV2
from lib.lua.bwarchivelib import BattalionArchive
from io import BytesIO


class BWModelHandler(object):
    def __init__(self):
        self.models = {}
        self.instancemodels = {}
        self.attachpoints = {}  # modelname -> {slot: attach node matrix}, for helmet/weapon/backpack
        self._bounds = {}
        self.textures: TextureArchive = None

    @classmethod
    def from_archive(cls, bwarc, callback=None):
        bwmodels = cls()

        bwmodels.textures = TextureArchive(bwarc)
        models = [x for x in bwarc.models()]
        for i, modeldata in enumerate(models):
            name = modeldata.name  # str(modeldata.res_name, encoding="ascii")
            print(name)
            if bwarc.textures.is_bw1:
                model = BW1Model()
            else:
                model = BW2Model()
            # data = modeldata.entries[0]
            # data.fileobj.seek(0)
            # f = data.fileobj
            f = BytesIO(modeldata.data[8:])
            model.from_file(f)
            texmodel = model.make_textured_model(bwmodels.textures)
            bwmodels.models[name] = texmodel  # model
            bwmodels.instancemodels[name] = BWModelV2.from_textured_bw_model(texmodel)
            bwmodels.attachpoints[name] = attachments.attach_matrices(model)
            if callback is not None: callback(len(models), i)
        return bwmodels

    @classmethod
    def from_file(cls, f, callback=None):
        bwarc = BattalionArchive.from_file(f)  # BWArchive(f)
        return cls.from_archive(bwarc, callback)

    def update_models(self, bwarc, force_update_models=[], force_update_textures=[]):
        self.textures.update_textures(bwarc, force_update_textures)

        for i, modeldata in enumerate(bwarc.models()):
            name = modeldata.name#str(modeldata.res_name, encoding="ascii")
            if name not in self.models or name in force_update_models:
                print(name)
                if bwarc.textures.is_bw1:
                    model = BW1Model()
                else:
                    model = BW2Model()
                #data = modeldata.entries[0]
                #data.fileobj.seek(0)
                #f = data.fileobj
                f = BytesIO(modeldata.data[8:])
                model.from_file(f)
                texmodel = model.make_textured_model(self.textures)
                self.models[name] = texmodel#model
                self.instancemodels[name] = BWModelV2.from_textured_bw_model(texmodel)
                self.attachpoints[name] = attachments.attach_matrices(model)

    def bounds(self, name):
        """Model space bounding box (minx, miny, minz, maxx, maxy, maxz), or None. Computed on
        demand and cached -- only the handful of models involved in an attachment need it."""
        if name in self._bounds:
            return self._bounds[name]

        model = self.models.get(name)
        box = None
        if model is not None:
            for mesh in model.mesh_list:
                for vertex, uv in mesh.trilist:
                    if box is None:
                        box = [vertex[0], vertex[1], vertex[2], vertex[0], vertex[1], vertex[2]]
                    else:
                        for i in range(3):
                            if vertex[i] < box[i]:
                                box[i] = vertex[i]
                            elif vertex[i] > box[i + 3]:
                                box[i + 3] = vertex[i]
        self._bounds[name] = box
        return box

    def rendermodel(self, name, mtx, bwterrain, offset):
        """pos = bwmatrix.position
        x,y = int((pos.x+2048)*0.25), int((pos.z+2048)*0.25)
        if x >= 0 and x < 4096 and y >= 0 and y < 4096:
            if bwterrain.pointdata[x][y] is not None:
                y = bwterrain.pointdata[x][y][0]/32.0
            else:
                y = pos.y"""

        glPushMatrix()

        #glTranslatef(pos.x, pos.z, y)

        """glMultMatrixf([mtx.a1, mtx.a2, mtx.a3, mtx.a4,
                       mtx.b1, mtx.b2, mtx.b3, mtx.b4,
                       mtx.c1, mtx.c2, mtx.c3, mtx.c4,
                       mtx.d1, mtx.d2, mtx.d3, mtx.d4])"""
        #glRotatef(90, 1, 0, 0)
        """glMultMatrixf([mtx.a1, mtx.b1, mtx.c1, mtx.d1,
                       mtx.a2, mtx.b2, mtx.c2, mtx.d2,
                       mtx.a3, mtx.b3, mtx.c3, mtx.d3,
                       mtx.a4, mtx.b4, mtx.c4, mtx.d4])"""
        glMultMatrixf([ 1.0, 0.0, 0.0, 0.0,
                        0.0, 0.0, 1.0, 0.0,
                        0.0, 1.0, 0.0, 0.0,
                        0.0, 0.0, 0.0, 1.0])

        #glMultMatrixf([mtx.a1, mtx.a2, mtx.a3, mtx.a4,
        #               mtx.b1, mtx.b2, mtx.b3, mtx.b4,
        #               mtx.c1, mtx.c2, mtx.c3, mtx.c4,
        #               mtx.d1, mtx.d2, mtx.d3, mtx.d4])
        glMultMatrixf(mtx)

        model = self.models[name]
        model.render(self.textures, None)

        glPopMatrix()

    def render_model_inplace(self, name):
        model = self.models[name]
        model.render(self.textures, None)


if __name__ == "__main__":
    with open("C1_OnPatrol_Level.res", "rb") as f:
        bwmodels = BWModelHandler.from_file(f)