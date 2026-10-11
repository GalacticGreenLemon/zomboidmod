#!/usr/bin/env python3
"""Renders the pack's models with their textures to PNGs, to check them without the game.

  python3 tools/preview_models.py [out_dir] [model ...]

Faces are culled one-sided, as Viewpoint draws them, and shaded with the file's normals.
"""

import math
import os
import sys

import numpy as np
from PIL import Image

PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "Contents", "mods", "ViewpointModelFix", "42", "media", "viewpoint", "ViewpointModelFix")
W = H = 420


def load(path):
    """Positions and normals back to y-up for viewing; texture from the MTL."""
    v, vt, vn, faces, mtl = [], [], [], [], None
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            x, y, z = (float(c) for c in p[1:4])
            v.append([x, z, y])
        elif p[0] == "vt":
            vt.append([float(c) for c in p[1:3]])
        elif p[0] == "vn":
            x, y, z = (float(c) for c in p[1:4])
            vn.append([x, z, y])
        elif p[0] == "f":
            faces.append([[int(i) - 1 for i in c.split("/")] for c in p[1:]])
        elif p[0] == "mtllib":
            mtl = p[1]
    texture = None
    for line in open(os.path.join(os.path.dirname(path), mtl)):
        if line.startswith("map_Kd"):
            texture = os.path.normpath(os.path.join(os.path.dirname(path), line.split(None, 1)[1].strip()))
    tex = np.asarray(Image.open(texture).convert("RGB"), np.float32)
    return np.array(v), np.array(vt), np.array(vn), faces, tex


def render(path, yaw=-35, pitch=22, centre=None, distance=3.0, zoom=None):
    """Renders one OBJ, or several drawn together (a list of paths)."""
    paths = path if isinstance(path, (list, tuple)) else [path]
    models = [load(p) for p in paths]
    if centre is None:  # frame the models
        allv = np.concatenate([m[0] for m in models])
        lo, hi = allv.min(0), allv.max(0)
        centre = (lo + hi) / 2
        zoom = 0.75 * 2 * distance / (np.linalg.norm(hi - lo) * 1.15)
    y, p = math.radians(yaw), math.radians(pitch)
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    rot = rx @ ry
    img = np.full((H, W, 3), 40.0)
    zbuf = np.full((H, W), np.inf)
    light = rot @ (np.array([0.4, 0.8, 0.5]) / np.linalg.norm([0.4, 0.8, 0.5]))
    for v, vt, vn, faces, tex in models:
        th, tw = tex.shape[:2]
        cam = (rot @ (v - np.array(centre)).T).T
        cam[:, 2] -= distance
        sx = W / 2 + cam[:, 0] / -cam[:, 2] * zoom * W / 2
        sy = H / 2 - cam[:, 1] / -cam[:, 2] * zoom * W / 2
        nrm = (rot @ vn.T).T
        for face in faces:
            ids = [c[0] for c in face]
            a, b, c = sx[ids], sy[ids], cam[ids, 2]
            area = (a[1] - a[0]) * (b[2] - b[0]) - (a[2] - a[0]) * (b[1] - b[0])
            if area <= 0:  # the y/z swap in load() mirrors, so front faces wind the other way
                continue
            x0, x1 = max(int(a.min()), 0), min(int(a.max()) + 1, W - 1)
            y0, y1 = max(int(b.min()), 0), min(int(b.max()) + 1, H - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((a[1] - gx) * (b[2] - gy) - (a[2] - gx) * (b[1] - gy)) / area
            w1 = ((a[2] - gx) * (b[0] - gy) - (a[0] - gx) * (b[2] - gy)) / area
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            z = -(w0 * c[0] + w1 * c[1] + w2 * c[2])
            py, px = np.nonzero(inside)
            zz = z[inside]
            sy_, sx_ = py + y0, px + x0
            closer = zz < zbuf[sy_, sx_]
            if not closer.any():
                continue
            sy_, sx_, zz = sy_[closer], sx_[closer], zz[closer]
            ww = np.stack([w0[inside][closer], w1[inside][closer], w2[inside][closer]], 1)
            uv = ww @ vt[[c_[1] for c_ in face]]
            n = ww @ nrm[[c_[2] for c_ in face]]
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            n = np.where((n[:, 2:3] < 0), -n, n)  # face the camera
            shade = 0.5 + 0.5 * np.clip(n @ light, 0, 1)
            tu = np.clip((uv[:, 0] * tw).astype(int), 0, tw - 1)
            tv = np.clip(((1 - uv[:, 1]) * th).astype(int), 0, th - 1)
            zbuf[sy_, sx_] = zz
            img[sy_, sx_] = tex[tv, tu] * shade[:, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def main(args):
    out = args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "previews")
    names = args[1:] or sorted(n[:-4] for n in os.listdir(PACK) if n.endswith(".obj") and n.count(".") == 1)
    os.makedirs(out, exist_ok=True)
    tiles = []
    for n in names:
        # "a+b" draws models together, as goods over their shelf
        im = render([os.path.join(PACK, part + ".obj") for part in n.split("+")])
        im.save(os.path.join(out, n + ".png"))
        tiles.append(im)
    cols = min(4, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (W * cols, H * rows), (40, 40, 40))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * W, (i // cols) * H))
    sheet.save(os.path.join(out, "all.png"))
    print("wrote", os.path.abspath(out))


if __name__ == "__main__":
    main(sys.argv[1:])
