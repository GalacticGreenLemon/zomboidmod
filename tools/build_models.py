#!/usr/bin/env python3
"""Builds the ViewpointModelFix model pack: low-poly OBJ models, each with its own texture
baked to look worn and grimy, like the rest of Project Zomboid.

Run from the repo root:  python3 tools/build_models.py [model ...]

Viewpoint's model packs read OBJ files in the game's own world axes: X east, Y south, Z up.
1 unit is one tile wide, a storey is 2.449 units tall (sqrt 6), and the origin is the
centre of the tile on its floor. `degrees` in a bind turns a model from east towards south.
The shapes here are authored Y-up (see meshlib.py); materials.py paints them.
"""

import os
import sys
import time

from PIL import Image

import materials
from bake import bake
from meshlib import WALL, Mesh, write_obj

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Contents", "mods", "ViewpointModelFix")
PACK = os.path.join("media", "viewpoint", "ViewpointModelFix")
OUT = os.path.join(MOD, "42", PACK)
# The mod writes extra pack files at run time, into 42/ or common/ depending on the game build,
# naming models beside them; so OBJs and MTLs ship in both, the textures in 42/ only.
COMMON = os.path.join(MOD, "common", PACK)
TEXTURE_FROM_COMMON = "../../../../42/media/viewpoint/ViewpointModelFix/"

DENSITY = 128  # texels per unit (a tile's width); about the game's own art


def urinal():
    m = Mesh(wall=True)
    back = WALL + 0.03
    m.box(-0.19, 0.19, 0.48, 1.10, WALL, back, "porcelain")  # wall plate
    # trough at the bottom: half an ellipse out from the wall, its top the bowl's floor
    m.lathe(0.0, back, [(0.50, 0.13, 0.17), (0.58, 0.18, 0.27), (0.64, 0.19, 0.29)],
            "porcelain", segments=12, a0=0, a1=180, top="basin", bottom="porcelain", close_back=True,
            top_prm={"cx": 0.0, "cz": back, "rx": 0.19, "rz": 0.29, "drain": (0.0, back + 0.07)})
    # hood at the top
    m.lathe(0.0, back, [(0.98, 0.19, 0.29), (1.08, 0.18, 0.25)],
            "porcelain", segments=12, a0=0, a1=180, top="porcelain", bottom="inner", close_back=True)
    # the two side walls, leaving the front open between them
    for a0, a1 in ((0, 38), (142, 180)):
        m.lathe(0.0, back, [(0.64, 0.19, 0.29), (0.98, 0.19, 0.29)], "porcelain",
                segments=4, a0=a0, a1=a1)
    # the hollow's back: a half cylinder curving into the wall, seen from inside
    m.lathe(0.0, back + 0.15, [(0.64, 0.16, 0.15), (0.98, 0.16, 0.15)], "inner",
            segments=10, a0=180, a1=360)
    # flush valve: pipe up the wall and a lever
    m.lathe(0.0, WALL + 0.07, [(1.08, 0.022, 0.022), (1.34, 0.022, 0.022)], "chrome",
            segments=8, top="chrome")
    m.box(-0.07, 0.07, 1.30, 1.36, WALL + 0.04, WALL + 0.11, "chrome")
    m.box(0.07, 0.17, 1.32, 1.34, WALL + 0.08, WALL + 0.10, "chrome")
    return m


def toilet():
    m = Mesh(wall=True)
    # tank and lid against the wall
    m.box(-0.22, 0.22, 0.40, 0.78, WALL + 0.02, WALL + 0.21, "porcelain")
    m.box(-0.23, 0.23, 0.78, 0.81, WALL + 0.01, WALL + 0.22, "porcelain")
    m.box(-0.20, -0.14, 0.70, 0.72, WALL + 0.21, WALL + 0.24, "chrome")  # flush handle
    m.lathe(0.0, -0.08, [(0.0, 0.13, 0.18), (0.30, 0.15, 0.20)], "porcelain",
            segments=14, bottom="porcelain")                                # pedestal
    m.lathe(0.0, -0.06, [(0.30, 0.16, 0.22), (0.38, 0.19, 0.27), (0.40, 0.19, 0.27)],
            "porcelain", segments=14)                                       # bowl
    # seat, its top the bowl seen from above
    m.lathe(0.0, -0.06, [(0.40, 0.195, 0.275), (0.425, 0.195, 0.275)], "seat",
            segments=14, top="basin",
            top_prm={"cx": 0.0, "cz": -0.06, "rx": 0.195, "rz": 0.275, "water": 0.6})
    m.box(-0.10, 0.10, 0.25, 0.42, WALL + 0.20, -0.20, "porcelain")       # neck to the tank
    return m


def sink():
    m = Mesh(wall=True)
    z0, z1 = WALL + 0.01, WALL + 0.46
    # wall-hung basin, the top painted as the bowl, rusted below the tap
    m.box(-0.28, 0.28, 0.74, 0.88, z0, z1, "porcelain", top="basin",
          top_prm={"cx": 0.0, "cz": WALL + 0.26, "rx": 0.22, "rz": 0.17, "tap": (0.0, WALL + 0.2)})
    m.box(-0.28, 0.28, 0.88, 0.96, z0, WALL + 0.06, "porcelain")           # back splash
    m.lathe(0.0, WALL + 0.10, [(0.88, 0.02, 0.02), (1.00, 0.02, 0.02)], "chrome",
            segments=8, top="chrome")                                       # tap
    m.box(-0.015, 0.015, 0.97, 1.00, WALL + 0.10, WALL + 0.22, "chrome")
    m.box(-0.10, -0.05, 0.89, 0.92, WALL + 0.08, WALL + 0.12, "chrome")
    m.box(0.05, 0.10, 0.89, 0.92, WALL + 0.08, WALL + 0.12, "chrome")
    m.lathe(0.0, WALL + 0.18, [(0.45, 0.025, 0.025), (0.74, 0.025, 0.025)], "chrome",
            segments=8)                                                     # drain pipe
    m.box(-0.025, 0.025, 0.45, 0.50, WALL, WALL + 0.18, "chrome")
    return m


def box_small():
    m = Mesh()
    m.box(-0.24, 0.24, 0.0, 0.36, -0.18, 0.18, "cardboard")
    m.box(-0.04, 0.04, 0.36, 0.365, -0.18, 0.18, "tape")
    m.box(-0.04, 0.04, 0.0, 0.365, 0.18, 0.185, "tape")
    return m


def shelf_metal():
    m = Mesh(wall=True)
    x0, x1 = -0.48, 0.48
    z0, z1 = WALL + 0.02, WALL + 0.48
    for x in (x0, x1 - 0.035):
        for z in (z0, z1 - 0.035):
            m.box(x, x + 0.035, 0.0, 1.85, z, z + 0.035, "darkmetal")
    for y in (0.10, 0.58, 1.06, 1.54):
        m.box(x0, x1, y, y + 0.03, z0, z1, "darkmetal")
    for x in (x0, x1 - 0.02):
        m.box(x, x + 0.02, 0.85, 0.88, z0, z1, "darkmetal")  # cross braces on the sides
    return m


def bed(blanket):
    def make():
        # one tile of a bed: beds are two sprites long, so each half is a full tile of bed
        # running along its facing (Z here), and the halves meet end to end
        m = Mesh()
        x0, x1 = -0.46, 0.46
        for x in (x0, x1 - 0.06):
            for z in (-0.5, 0.44):
                m.box(x, x + 0.06, 0.0, 0.14, z, z + 0.06, "wood", prm={"grain": 1})  # legs
        m.box(x0, x1, 0.14, 0.26, -0.5, 0.5, "wood", prm={"grain": 2})                # frame
        m.box(x0 + 0.02, x1 - 0.02, 0.26, 0.40, -0.5, 0.5, "mattress")
        m.box(x0 - 0.01, x1 + 0.01, 0.34, 0.46, -0.5, 0.5, blanket)
        return m
    return make


def mirror():
    m = Mesh(wall=True)
    m.box(-0.30, 0.30, 1.02, 1.82, WALL, WALL + 0.02, "chrome")                       # frame
    m.box(-0.28, 0.28, 1.04, 1.80, WALL + 0.02, WALL + 0.026, "glass",
          prm={"rect": (-0.28, 0.28, 1.04, 1.80)})                                    # glass
    return m


def light_switch():
    m = Mesh(wall=True)
    touched = {"touched": (0.0, 1.12)}
    m.box(-0.04, 0.04, 1.06, 1.18, WALL, WALL + 0.012, "plastic", prm=touched)       # plate
    m.box(-0.01, 0.01, 1.105, 1.135, WALL + 0.012, WALL + 0.03, "plastic", prm=touched)
    return m


def hand_dryer():
    m = Mesh(wall=True)
    m.box(-0.13, 0.13, 1.00, 1.26, WALL, WALL + 0.17, "plastic")
    m.lathe(0.0, WALL + 0.11, [(0.94, 0.035, 0.035), (1.00, 0.04, 0.04)], "chrome",
            segments=8, bottom="drain")                                               # nozzle
    m.box(-0.08, 0.08, 1.20, 1.23, WALL + 0.17, WALL + 0.175, "chrome")              # badge
    return m


MODELS = {
    "urinal": urinal,
    "toilet": toilet,
    "sink": sink,
    "box_small": box_small,
    "shelf_metal": shelf_metal,
    "bed": bed("blanket"),
    "bed_blue": bed("blanket_blue"),
    "bed_red": bed("blanket_red"),
    "bed_green": bed("blanket_green"),
    "mirror": mirror,
    "light_switch": light_switch,
    "hand_dryer": hand_dryer,
}


def build(name):
    mesh = MODELS[name]()
    img, uvs, density = bake(mesh, materials.PAINTERS, DENSITY)
    Image.fromarray(img).save(os.path.join(OUT, name + ".png"), optimize=True)
    for folder, texture in ((OUT, ""), (COMMON, TEXTURE_FROM_COMMON)):
        write_obj(mesh, uvs, os.path.join(folder, name + ".obj"), name + ".mtl")
        with open(os.path.join(folder, name + ".mtl"), "w") as f:
            f.write("newmtl model\nKd 1 1 1\nmap_Kd %s%s.png\n" % (texture, name))
    return mesh, img, density


def main(names):
    for folder in (OUT, COMMON):
        os.makedirs(folder, exist_ok=True)
    for name in names or MODELS:
        start = time.time()
        mesh, img, density = build(name)
        print("%-12s %4d triangles, %dx%d texture at %d texels a tile (%.1fs)"
              % (name, len(mesh.tris), img.shape[1], img.shape[0], density, time.time() - start))


if __name__ == "__main__":
    main(sys.argv[1:])
