#!/usr/bin/env python3
"""Renders the pack's OBJ models to PNGs so they can be checked without the game.

  python3 tools/preview_models.py [out_dir]

Back faces are culled, as a game renderer would, so a face wound the wrong way
shows as a hole.
"""

import math
import os
import sys

import numpy as np
from PIL import Image

PACK = os.path.join(os.path.dirname(__file__), "..",
                    "Contents", "mods", "ViewpointModelFix", "42", "media", "viewpoint", "ViewpointModelFix")
W = H = 360


def load(path):
    v, vt, faces = [], [], []
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            v.append([float(x) for x in p[1:4]])
        elif p[0] == "vt":
            vt.append([float(x) for x in p[1:3]])
        elif p[0] == "f":
            faces.append([[int(i) - 1 for i in c.split("/")[:2]] for c in p[1:]])
    return np.array(v), np.array(vt), faces


def render(path, tex, yaw=-35, pitch=22):
    v, vt, faces = load(path)
    tw, th = tex.shape[1], tex.shape[0]
    centre = np.array([0.0, 0.6, 0.0])
    y, p = math.radians(yaw), math.radians(pitch)
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    cam = (rx @ ry @ (v - centre).T).T  # camera looks down -Z
    cam[:, 2] -= 3.0
    f = 3.2
    sx = W / 2 + cam[:, 0] / -cam[:, 2] * f * W / 2
    sy = H / 2 - cam[:, 1] / -cam[:, 2] * f * W / 2
    img = np.full((H, W, 3), 40, np.uint8)
    zbuf = np.full((H, W), np.inf)
    light = np.array([0.4, 0.8, 0.5]) / np.linalg.norm([0.4, 0.8, 0.5])
    for face in faces:
        for k in range(1, len(face) - 1):
            tri = [face[0], face[k], face[k + 1]]
            ids = [c[0] for c in tri]
            a, b, c = sx[ids], sy[ids], cam[ids, 2]
            area = (a[1] - a[0]) * (b[2] - b[0]) - (a[2] - a[0]) * (b[1] - b[0])
            if area >= 0:  # clockwise on screen (y down) = back face
                continue
            wn = np.cross(v[ids[1]] - v[ids[0]], v[ids[2]] - v[ids[0]])
            wn /= np.linalg.norm(wn) or 1
            shade = 0.45 + 0.55 * max(0.0, float(wn @ light))
            uv = vt[[c_[1] for c_ in tri]]
            x0, x1 = int(max(0, a.min())), int(min(W - 1, a.max()))
            y0, y1 = int(max(0, b.min())), int(min(H - 1, b.max()))
            for py in range(y0, y1 + 1):
                for px in range(x0, x1 + 1):
                    w0 = ((a[1] - px) * (b[2] - py) - (a[2] - px) * (b[1] - py)) / area
                    w1 = ((a[2] - px) * (b[0] - py) - (a[0] - px) * (b[2] - py)) / area
                    w2 = 1 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    z = -(w0 * c[0] + w1 * c[1] + w2 * c[2])
                    if z >= zbuf[py, px]:
                        continue
                    zbuf[py, px] = z
                    u, vv = w0 * uv[0] + w1 * uv[1] + w2 * uv[2]
                    t = tex[int((1 - vv) * (th - 1)), int(u * (tw - 1))]
                    img[py, px] = np.clip(t * shade, 0, 255)
    return Image.fromarray(img)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PACK, "..", "..", "..", "..", "..", "..", "..", "previews")
    os.makedirs(out, exist_ok=True)
    tex = np.asarray(Image.open(os.path.join(PACK, "atlas.png")).convert("RGB"), np.float32)
    names = sorted(n[:-4] for n in os.listdir(PACK) if n.endswith(".obj"))
    tiles = []
    for n in names:
        im = render(os.path.join(PACK, n + ".obj"), tex)
        im.save(os.path.join(out, n + ".png"))
        tiles.append(im)
    sheet = Image.new("RGB", (W * len(tiles), H))
    for i, im in enumerate(tiles):
        sheet.paste(im, (i * W, 0))
    sheet.save(os.path.join(out, "all.png"))
    print("wrote", os.path.abspath(out))


if __name__ == "__main__":
    main()
