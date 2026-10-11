#!/usr/bin/env python3
"""Builds the ViewpointModelFix model pack: low-poly OBJ models plus one texture atlas.

Run from the repo root:  python3 tools/build_models.py

Viewpoint's model packs read OBJ files in the game's own world axes: X east, Y south, Z up.
1 unit is one tile wide, a storey is 2.449 units tall (sqrt 6), and the origin is the
centre of the tile on its floor. `degrees` in a bind turns a model from east towards south.

The shapes below are authored Y-up for convenience: X east, Y up, Z south (the front),
back against the -Z edge, which is a north wall. Mesh.write converts to Viewpoint's axes.
Every face is written both ways round: Viewpoint mirrors the file on loading and draws
faces one-sided, so this keeps the models whole whichever side it takes for the front.
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

MOD = os.path.join(os.path.dirname(__file__), "..", "Contents", "mods", "ViewpointModelFix")
OUT = os.path.join(MOD, "42", "media", "viewpoint", "ViewpointModelFix")
# The mod writes extra pack files at run time, into 42/ or common/ depending on the game build;
# their models are named relative to them, so the models ship in both.
COPIES = [OUT, os.path.join(MOD, "common", "media", "viewpoint", "ViewpointModelFix")]
ATLAS = "atlas.png"

# --- texture atlas: a 4x4 grid of 64px swatches ---------------------------------------------

CELL = 64
SWATCHES = ["porcelain", "basin", "chrome", "cardboard",
            "tape", "darkmetal", "seat", "drain"]


def swatch_uv(name):
    i = SWATCHES.index(name)
    cx, cy = i % 4, i // 4
    pad = 4  # keep samples away from neighbours so mipmaps don't bleed
    u0 = (cx * CELL + pad) / (4 * CELL)
    u1 = ((cx + 1) * CELL - pad) / (4 * CELL)
    # OBJ's v runs bottom-up, images top-down
    v1 = 1 - (cy * CELL + pad) / (4 * CELL)
    v0 = 1 - ((cy + 1) * CELL - pad) / (4 * CELL)
    return u0, v0, u1, v1


def noisy(base, amount, rng, size=CELL):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            n = rng.uniform(-amount, amount)
            px[x, y] = tuple(max(0, min(255, int(c + n))) for c in base)
    return img


def build_atlas(path):
    rng = random.Random(42)
    atlas = Image.new("RGB", (4 * CELL, 4 * CELL), (255, 0, 255))

    def put(name, img):
        i = SWATCHES.index(name)
        atlas.paste(img, ((i % 4) * CELL, (i // 4) * CELL))

    put("porcelain", noisy((232, 234, 236), 5, rng).filter(ImageFilter.SMOOTH))
    put("seat", noisy((240, 238, 232), 4, rng).filter(ImageFilter.SMOOTH))

    # basin: white rim fading to a cool grey bowl with a dark drain in the middle
    basin = Image.new("RGB", (CELL, CELL))
    bp = basin.load()
    for y in range(CELL):
        for x in range(CELL):
            d = math.hypot(x - CELL / 2 + 0.5, y - CELL / 2 + 0.5) / (CELL / 2)
            if d > 0.86:
                c = (236, 238, 240)
            else:
                t = d / 0.86
                c = tuple(int(a + (b - a) * t) for a, b in zip((176, 186, 194), (222, 226, 230)))
            if d < 0.12:
                c = (70, 72, 76)
            bp[x, y] = c
    put("basin", basin.filter(ImageFilter.SMOOTH))

    chrome = Image.new("RGB", (CELL, CELL))
    cp = chrome.load()
    for y in range(CELL):
        for x in range(CELL):
            t = 0.5 + 0.5 * math.sin(x / CELL * math.pi * 2)
            v = int(150 + 80 * t)
            cp[x, y] = (v, v, min(255, v + 6))
    put("chrome", chrome)

    card = noisy((186, 146, 96), 10, rng)
    d = ImageDraw.Draw(card)
    for _ in range(30):  # a few fibres and scuffs
        x, y = rng.randrange(CELL), rng.randrange(CELL)
        d.line([(x, y), (x + rng.randint(-6, 6), y + rng.randint(-2, 2))], fill=(160, 122, 78))
    put("cardboard", card.filter(ImageFilter.SMOOTH))
    put("tape", noisy((214, 190, 140), 6, rng).filter(ImageFilter.SMOOTH))
    put("darkmetal", noisy((58, 61, 66), 6, rng).filter(ImageFilter.SMOOTH))
    put("drain", noisy((60, 62, 66), 4, rng))

    atlas.save(path)


# --- meshes ---------------------------------------------------------------------------------

class Mesh:
    def __init__(self):
        self.v, self.vt, self.vn, self.f = [], [], [], []

    def _index(self, lst, item):
        lst.append(item)
        return len(lst)

    def tri(self, a, b, c, uva, uvb, uvc):
        """One triangle, corners counter-clockwise seen from outside."""
        ux, uy, uz = (b[i] - a[i] for i in range(3))
        vx, vy, vz = (c[i] - a[i] for i in range(3))
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        ln = math.sqrt(sum(x * x for x in n)) or 1.0
        ni = self._index(self.vn, tuple(x / ln for x in n))
        corners = []
        for p, uv in ((a, uva), (b, uvb), (c, uvc)):
            corners.append((self._index(self.v, p), self._index(self.vt, uv), ni))
        self.f.append(corners)

    def quad(self, a, b, c, d, swatch):
        """A quad a-b-c-d counter-clockwise from outside, the swatch stretched over it."""
        u0, v0, u1, v1 = swatch_uv(swatch)
        self.tri(a, b, c, (u0, v0), (u1, v0), (u1, v1))
        self.tri(a, c, d, (u0, v0), (u1, v1), (u0, v1))

    def box(self, x0, x1, y0, y1, z0, z1, swatch, top=None, front=None):
        s = {"top": top or swatch, "front": front or swatch}
        self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), s["front"])  # +Z
        self.quad((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), swatch)      # -Z
        self.quad((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), swatch)      # +X
        self.quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0), swatch)      # -X
        self.quad((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0), s["top"])    # +Y
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), swatch)      # -Y

    def lathe(self, cx, cz, rings, swatch, segments=12, a0=0.0, a1=360.0,
              top=None, bottom=None, close_back=False):
        """A vertical solid of revolution with an elliptical section.

        rings: [(y, rx, rz), ...] from bottom to top. a0..a1 limits the sweep (degrees,
        0 = +X, 90 = +Z) so a half sweep makes a shape that sits flat against a wall.
        top/bottom: swatch for the caps (None leaves the cap off)."""
        full = (a1 - a0) >= 360.0
        n = segments
        angles = [math.radians(a0 + (a1 - a0) * i / n) for i in range(n + 1)]

        def at(ring, a):
            y, rx, rz = ring
            return (cx + rx * math.cos(a), y, cz + rz * math.sin(a))

        u0, v0, u1, v1 = swatch_uv(swatch)
        for r0, r1 in zip(rings, rings[1:]):
            for i in range(n):
                a, b = angles[i], angles[i + 1]
                p00, p01 = at(r0, a), at(r0, b)
                p10, p11 = at(r1, a), at(r1, b)
                ua = u0 + (u1 - u0) * i / n
                ub = u0 + (u1 - u0) * (i + 1) / n
                # angles increase towards +Z from +X, so b-then-a is counter-clockwise outside
                self.tri(p01, p00, p10, (ub, v0), (ua, v0), (ua, v1))
                self.tri(p01, p10, p11, (ub, v0), (ua, v1), (ub, v1))

        def cap(ring, swatch_name, up):
            cu0, cv0, cu1, cv1 = swatch_uv(swatch_name)
            y, rx, rz = ring
            centre = (cx, y, cz)
            cuv = ((cu0 + cu1) / 2, (cv0 + cv1) / 2)

            def uv_of(p):
                return (cuv[0] + (p[0] - cx) / (2 * rx) * (cu1 - cu0),
                        cuv[1] - (p[2] - cz) / (2 * rz) * (cv1 - cv0))
            for i in range(n):
                a, b = at(ring, angles[i]), at(ring, angles[i + 1])
                if up:
                    self.tri(centre, b, a, cuv, uv_of(b), uv_of(a))
                else:
                    self.tri(centre, a, b, cuv, uv_of(a), uv_of(b))

        if top:
            cap(rings[-1], top, True)
        if bottom:
            cap(rings[0], bottom, False)
        if close_back and not full:
            # flat face along the cut, facing away from the sweep
            for r0, r1 in zip(rings, rings[1:]):
                a, b = at(r0, angles[0]), at(r0, angles[-1])
                c, d = at(r1, angles[-1]), at(r1, angles[0])
                self.quad(b, a, d, c, swatch)

    def write(self, path, mtl):
        # authored (x east, y up, z south) -> Viewpoint (x east, y south, z up)
        with open(path, "w") as f:
            f.write("# ViewpointModelFix, built by tools/build_models.py\n")
            f.write(f"mtllib {mtl}\n")
            for x, y, z in self.v:
                f.write("v %.4f %.4f %.4f\n" % (x, z, y))
            for t in self.vt:
                f.write("vt %.4f %.4f\n" % t)
            for x, y, z in self.vn:
                f.write("vn %.4f %.4f %.4f\n" % (x, z, y))
            for x, y, z in self.vn:
                f.write("vn %.4f %.4f %.4f\n" % (-x, -z, -y))
            f.write("usemtl atlas\n")
            flip = len(self.vn)
            for face in self.f:
                # swapping y and z mirrors, so the authored order now winds the other way
                f.write("f " + " ".join("%d/%d/%d" % c for c in reversed(face)) + "\n")
                f.write("f " + " ".join("%d/%d/%d" % (v, t, n + flip) for v, t, n in face) + "\n")


WALL = -0.5  # the back edge of the tile


def urinal():
    m = Mesh()
    # wall plate the bowl hangs from
    m.box(-0.19, 0.19, 0.48, 1.08, WALL, WALL + 0.03, "porcelain")
    # the bowl: half an ellipse sweeping out from the wall, narrowing to the bottom
    m.lathe(0.0, WALL + 0.03, [
        (0.50, 0.13, 0.16),
        (0.58, 0.17, 0.26),
        (0.90, 0.19, 0.30),
        (1.05, 0.19, 0.27),
    ], "porcelain", segments=12, a0=0, a1=180, top="basin", bottom="porcelain", close_back=True)
    # drip lip at the front
    m.box(-0.10, 0.10, 0.50, 0.56, WALL + 0.20, WALL + 0.30, "porcelain")
    # flush valve: pipe up the wall and a lever
    m.lathe(0.0, WALL + 0.07, [(1.05, 0.022, 0.022), (1.32, 0.022, 0.022)], "chrome",
            segments=8, top="chrome")
    m.box(-0.07, 0.07, 1.28, 1.34, WALL + 0.04, WALL + 0.11, "chrome")
    m.box(0.07, 0.17, 1.30, 1.32, WALL + 0.08, WALL + 0.10, "chrome")
    return m


def toilet():
    m = Mesh()
    # tank and lid against the wall
    m.box(-0.22, 0.22, 0.40, 0.78, WALL + 0.02, WALL + 0.21, "porcelain")
    m.box(-0.23, 0.23, 0.78, 0.81, WALL + 0.01, WALL + 0.22, "porcelain")
    m.box(-0.20, -0.14, 0.70, 0.72, WALL + 0.21, WALL + 0.24, "chrome")  # flush handle
    # pedestal
    m.lathe(0.0, -0.08, [(0.0, 0.13, 0.18), (0.30, 0.15, 0.20)], "porcelain",
            segments=14, bottom="porcelain")
    # bowl
    m.lathe(0.0, -0.06, [(0.30, 0.16, 0.22), (0.38, 0.19, 0.27), (0.40, 0.19, 0.27)],
            "porcelain", segments=14)
    # seat, its top painted as the bowl seen from above
    m.lathe(0.0, -0.06, [(0.40, 0.195, 0.275), (0.425, 0.195, 0.275)], "seat",
            segments=14, top="basin")
    # neck joining the bowl to the tank
    m.box(-0.10, 0.10, 0.25, 0.42, WALL + 0.20, -0.20, "porcelain")
    return m


def sink():
    m = Mesh()
    # wall-hung basin, the top painted as the bowl
    m.box(-0.28, 0.28, 0.74, 0.88, WALL + 0.01, WALL + 0.46, "porcelain", top="basin")
    # back splash
    m.box(-0.28, 0.28, 0.88, 0.96, WALL + 0.01, WALL + 0.06, "porcelain")
    # tap
    m.lathe(0.0, WALL + 0.10, [(0.88, 0.02, 0.02), (1.00, 0.02, 0.02)], "chrome",
            segments=8, top="chrome")
    m.box(-0.015, 0.015, 0.97, 1.00, WALL + 0.10, WALL + 0.22, "chrome")
    m.box(-0.10, -0.05, 0.89, 0.92, WALL + 0.08, WALL + 0.12, "chrome")
    m.box(0.05, 0.10, 0.89, 0.92, WALL + 0.08, WALL + 0.12, "chrome")
    # drain pipe down to the wall
    m.lathe(0.0, WALL + 0.18, [(0.45, 0.025, 0.025), (0.74, 0.025, 0.025)], "chrome",
            segments=8)
    m.box(-0.025, 0.025, 0.45, 0.50, WALL, WALL + 0.18, "chrome")
    return m


def box_small():
    m = Mesh()
    m.box(-0.24, 0.24, 0.0, 0.36, -0.18, 0.18, "cardboard")
    m.box(-0.04, 0.04, 0.36, 0.365, -0.18, 0.18, "tape")
    m.box(-0.04, 0.04, 0.0, 0.365, 0.18, 0.185, "tape")
    return m


def shelf_metal():
    m = Mesh()
    x0, x1 = -0.48, 0.48
    z0, z1 = WALL + 0.02, WALL + 0.48
    for x in (x0, x1 - 0.035):
        for z in (z0, z1 - 0.035):
            m.box(x, x + 0.035, 0.0, 1.85, z, z + 0.035, "darkmetal")
    for y in (0.10, 0.58, 1.06, 1.54):
        m.box(x0, x1, y, y + 0.03, z0, z1, "darkmetal")
    # cross braces on the sides
    for x in (x0, x1 - 0.02):
        m.box(x, x + 0.02, 0.85, 0.88, z0, z1, "darkmetal")
    return m


MODELS = {
    "urinal": urinal,
    "toilet": toilet,
    "sink": sink,
    "box_small": box_small,
    "shelf_metal": shelf_metal,
}


def main():
    for out in COPIES:
        os.makedirs(out, exist_ok=True)
        build_atlas(os.path.join(out, ATLAS))
        with open(os.path.join(out, "atlas.mtl"), "w") as f:
            f.write("newmtl atlas\nKd 1 1 1\nmap_Kd %s\n" % ATLAS)
        for name, make in MODELS.items():
            mesh = make()
            mesh.write(os.path.join(out, name + ".obj"), "atlas.mtl")
            if out == OUT:
                print("%-12s %4d triangles (each written both ways round)" % (name, len(mesh.f)))


if __name__ == "__main__":
    main()
