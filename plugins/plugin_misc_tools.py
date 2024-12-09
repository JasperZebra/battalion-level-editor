import os
import time
import shutil
import random
from PIL import Image, ImageOps

from lib.bw.vectors import Vector3
from lib.BattalionXMLLib import BattalionFilePaths

import PyQt6.QtWidgets as QtWidgets
import PyQt6.QtGui as QtGui
import PyQt6.QtCore as QtCore
from widgets.editor_widgets import open_error_dialog
from widgets.menu.file_menu import PF2
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import bw_editor


def open_yesno_box(mainmsg, sidemsg):
    msgbox = QtWidgets.QMessageBox()
    msgbox.setText(
        mainmsg)
    msgbox.setInformativeText(sidemsg)
    msgbox.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
    msgbox.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
    msgbox.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    msgbox.setWindowIcon(QtGui.QIcon('resources/icon.ico'))
    msgbox.setWindowTitle("Warning")
    result = msgbox.exec()
    return result == QtWidgets.QMessageBox.StandardButton.Yes


class LoadingBar(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        WIDTH = 200
        HEIGHT = 50
        self.setFixedWidth(WIDTH)
        self.setFixedHeight(HEIGHT)

        self.timer = QtCore.QTimer()
        self.timer.setInterval(1000//60)
        self.timer.timeout.connect(self.update_loadingbar)
        self.timer.start()

        self.progress = 0
        self.starttime = time.time()

        self.vertical_distance = 10
        self.horizontal_distance = 10
        self.loadingbar_width = WIDTH-self.horizontal_distance*2
        self.loadingbar_height = HEIGHT-self.vertical_distance*2

        self.bar_highlight = -20
        self.last_time = None

    def closeEvent(self, closeevent):
        self.timer.stop()

    def update_loadingbar(self):
        self.update()

        timepassed = (time.time()-self.starttime)*3
        self.progress = timepassed/100.0
        self.progress = min(self.progress, 1.0)

        if self.last_time is None:
            self.last_time = time.time()
        else:
            curr = time.time()
            delta = curr-self.last_time
            self.last_time = curr
            self.bar_highlight += delta*50
            if self.bar_highlight > self.loadingbar_width * self.progress+100:
                self.bar_highlight = -20

    def paintEvent(self, paintevent:QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        bar_limit = int(self.loadingbar_width * self.progress)
        painter.fillRect(self.horizontal_distance,
                         self.vertical_distance,
                         bar_limit,
                         self.loadingbar_height,
                         0x00FF00)

        highlightcolor = Vector3(0xCF, 0xFF, 0xCF)
        barcolor = Vector3(0x00, 0xFF, 0x00)

        for x in range(0, self.loadingbar_width):
            distance = ((x-self.bar_highlight)**2)/1000.0 #abs(x - self.bar_highlight)/20.0
            if distance > 1:
                distance = 1

            color = highlightcolor*(1-distance) + barcolor*distance
            pencolor = int(color.x)<<16 | int(color.y)<<8 | int(color.z)
            painter.setPen(pencolor)
            if x < bar_limit:
                painter.drawLine(x+self.horizontal_distance,
                                 self.vertical_distance,
                                 x+self.horizontal_distance,
                                 self.vertical_distance+self.loadingbar_height)


class Plugin(object):
    def __init__(self):
        self.name = "Misc"
        self.actions = [#("ID Randomizer", self.randomize_ids),
                        ("Save State", self.save_state),
                        ("Load State", self.load_savestate),
                        ("Dump PF2 to PNG", self.pf2dump),
                        ("Update Texture Cache for Selection", self.update_texture_cache)]
                        #("Loading Bar Test", self.loading_bar)]
        print("I have been initialized")

    def update_texture_cache(self, editor: "bw_editor.LevelEditor"):
        selected = editor.level_view.selected

        texture_lookup = {}
        for objid, obj in editor.level_file.objects.items():
            if obj.type == "cTextureResource":
                texture_lookup[obj.mName.lower()] = obj

        texlist = []
        check = []

        for obj in selected:
            check.append(obj)
            for dep in obj.get_dependencies():
                if dep not in check:
                    check.append(dep)

        for obj in check:
            if obj.type == "cNodeHierarchyResource":
                modelname = obj.mName

                textures = editor.level_view.bwmodelhandler.models[modelname].all_textures
                for texname in textures:
                    if texname.lower() in texture_lookup:
                        texlist.append(texture_lookup[texname.lower()].mName)
            if obj.type == "cTextureResource":
                texlist.append(obj.mName)
        print("clearing...", texlist)
        editor.level_view.bwmodelhandler.textures.clear_cache(texlist)

    def loading_bar(self, editor):
        bar = LoadingBar(editor)
        bar.show()
        pass

    def pf2dump(self, editor):
        filepath, chosentype = QtWidgets.QFileDialog.getOpenFileName(
            editor, "Open PF2 File",
            editor.pathsconfig["xml"],
            "PF2 files (*.pf2);;All files (*)")

        pf2 = PF2(filepath)

        missionboundary = Image.new("RGB", (512, 512))
        ford = Image.new("RGB", (512, 512))
        nogo = Image.new("RGB", (512, 512))

        for i in range(512*512):
            x = (i) % 512
            y = (i) // 512
            if x < 256:
                x *= 2
            else:
                x = x - 256
                x *= 2
                x += 1

            # NOGO
            val = pf2.data[x][y][0]
            nogo.putpixel((x,y), (val, val, val))

            # FORD
            val = pf2.data[x][y][1]
            ford.putpixel((x, y), (val, val, val))

            # MISSION BOUNDARY
            val = pf2.data[x][y][2]
            missionboundary.putpixel((x, y), (val, val, val))

        ImageOps.flip(nogo).save(filepath+"_dump_nogo.png")
        ImageOps.flip(ford).save(filepath+"_dump_ford.png")
        ImageOps.flip(missionboundary).save(filepath+"_dump_missionboundary.png")
        print("Saved PNG dumps in same folder as", filepath)

    def randomize_ids(self, editor: "bw_editor.LevelEditor"):
        yes = open_yesno_box("You are about to randomize all IDs.", "Are you sure?")
        if yes:
            print("randomize...")
            newids = {}

            editor.lua_workbench.entityinit.reflection_ids = {}

            for id, obj in editor.level_file.objects.items():
                newid = random.randint(1, 800000)
                while newid in newids:
                    newid = random.randint(1, 800000)

                obj._node.attrib["id"] = str(newid)
                assert newid not in newids
                newids[newid] = True

                if obj.lua_name:
                    editor.lua_workbench.entityinit.reflection_ids[newid] = obj.lua_name

                editor.lua_workbench.write_entity_initialization()

            for id, obj in editor.level_file.objects.items():
                obj.update_xml()
            print("done")

    def save_state(self, editor: "bw_editor.LevelEditor"):
        try:
            os.mkdir("savestates")
        except FileExistsError:
            pass

        base = os.path.dirname(editor.file_menu.current_path)
        fname = os.path.basename(editor.file_menu.current_path)
        with open(editor.file_menu.current_path) as f:
            levelpaths = BattalionFilePaths(f)
        savestatename = "{0}_savestate_{1}".format(fname[:-4], int(time.time()))
        print(savestatename)
        savestatepath = os.path.join("savestates", savestatename)
        os.mkdir(savestatepath)
        pf2path = fname[:-4]+".pf2"
        editor.file_menu.button_save_level()

        for path in (levelpaths.terrainpath,
                     levelpaths.resourcepath,
                     levelpaths.objectpath,
                     levelpaths.preloadpath):
            shutil.copy(os.path.join(base, path),
                        os.path.join(savestatepath, path))

        try:
            shutil.copy(os.path.join(base, pf2path),
                        os.path.join(savestatepath,pf2path))
        except FileNotFoundError:
            pass

    def load_savestate(self, editor: "bw_editor.LevelEditor"):
        savestatepath = QtWidgets.QFileDialog.getExistingDirectory(
            editor, "Open Save State",
            "savestates/")

        savestatename = os.path.basename(savestatepath)
        if "_savestate_" in savestatename:
            levelname, time = savestatename.split("_savestate_")

            if levelname in editor.file_menu.current_path:
                base = os.path.dirname(editor.file_menu.current_path)
                fname = os.path.basename(editor.file_menu.current_path)
                with open(editor.file_menu.current_path) as f:
                    levelpaths = BattalionFilePaths(f)

                pf2path = fname[:-4] + ".pf2"

                for path in (levelpaths.terrainpath,
                             levelpaths.resourcepath,
                             levelpaths.objectpath,
                             levelpaths.preloadpath):
                    if not os.path.exists(os.path.join(
                        savestatepath, path
                        )):
                        open_error_dialog("Savestate was created with a different compression setting compared to current level!"
                                          "Cannot load.", editor)
                        return


                for path in (levelpaths.terrainpath,
                             levelpaths.resourcepath,
                             levelpaths.objectpath,
                             levelpaths.preloadpath):
                    shutil.copy(os.path.join(savestatepath, path),
                                os.path.join(base, path))

                try:
                    shutil.copy(os.path.join(savestatepath, pf2path),
                                os.path.join(base, pf2path))
                except FileNotFoundError:
                    pass
                editor.file_menu.button_load_level(fpathoverride=editor.file_menu.current_path)

                basepath = os.path.dirname(editor.current_gen_path)
                resname = editor.file_menu.level_paths.resourcepath

                editor.lua_workbench.unpack_scripts(os.path.join(basepath, resname))

            else:
                print("Level mismatch!")
        else:
            print("Not a savestate!")


    def unload(self):
        print("I have been unloaded")
