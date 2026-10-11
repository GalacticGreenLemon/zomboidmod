"""Bakes one texture per model: unwraps it, then paints every texel from where it is in 3D.

Each texel gets its position, its normal, how open it is (ambient occlusion, ray cast
against the model and the floor and wall it stands by) and how near it is to a crease
(edge wear). materials.py turns those into colour.
"""

import math

import numpy as np
from scipy import ndimage

PAD = 3              # texels of bleed round each chart, so filtering never reaches a neighbour
AO_RADIUS = 0.22     # units; nothing further away shades a texel
AO_RAYS = 24
CREASE_ANGLE = 35.0  # degrees between faces for their edge to count as a crease
EDGE_WIDTH = 0.03    # units of wear either side of a crease


# --- noise ----------------------------------------------------------------------------------

def _hash(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = h & 0xFFFFFFFF
    h = ((h ^ (h >> 15)) * 0x2C1B3C6D) & 0xFFFFFFFF
    h = ((h ^ (h >> 12)) * 0x297A2D39) & 0xFFFFFFFF
    h = h ^ (h >> 15)
    return h.astype(np.float64) / 4294967296.0


def vnoise(p, seed=0):
    """Smooth value noise in 0..1 at points p (M, 3)."""
    pi = np.floor(p).astype(np.int64)
    f = p - pi
    w = f * f * (3 - 2 * f)
    out = np.zeros(len(p))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = _hash(pi[:, 0] + dx, pi[:, 1] + dy, pi[:, 2] + dz, seed)
                wx = w[:, 0] if dx else 1 - w[:, 0]
                wy = w[:, 1] if dy else 1 - w[:, 1]
                wz = w[:, 2] if dz else 1 - w[:, 2]
                out += h * wx * wy * wz
    return out


def fbm(p, octaves=4, seed=0):
    """Fractal noise in roughly 0..1."""
    total, amp, norm = np.zeros(len(p)), 1.0, 0.0
    for o in range(octaves):
        total += amp * vnoise(p * (2.0 ** o), seed + 17 * o)
        norm += amp
        amp *= 0.5
    return total / norm


# --- unwrapping -----------------------------------------------------------------------------

PROJECT = {0: (2, 1), 1: (0, 2), 2: (0, 1)}  # dominant axis -> the two axes it is laid out on


def _weld(p):
    return tuple(np.round(p, 4))


def _edges(mesh):
    edges = {}
    for i, t in enumerate(mesh.tris):
        keys = [_weld(v) for v in t.p]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            k = tuple(sorted((keys[a], keys[b])))
            edges.setdefault(k, []).append(i)
    return edges


def _charts(mesh, edges):
    """Groups triangles facing the same way, of the same material, that touch."""
    def key(t):
        fn = t.face_normal
        ax = int(np.argmax(np.abs(fn)))
        return (ax, fn[ax] > 0, t.mat, repr(sorted(t.prm.items())))

    keys = [key(t) for t in mesh.tris]
    parent = list(range(len(mesh.tris)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for tris in edges.values():
        for a in tris:
            for b in tris:
                if a < b and keys[a] == keys[b]:
                    parent[find(a)] = find(b)
    groups = {}
    for i in range(len(mesh.tris)):
        groups.setdefault(find(i), []).append(i)
    return [(keys[g[0]][0], g) for g in groups.values()]


def _pack(sizes, width):
    """Shelf-packs (w, h) boxes into a strip `width` wide; returns positions and height used."""
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][1])
    pos = [None] * len(sizes)
    x = y = shelf = 0
    for i in order:
        w, h = sizes[i]
        if w > width:
            return None, None
        if x + w > width:
            x, y, shelf = 0, y + shelf, 0
        pos[i] = (x, y)
        x += w
        shelf = max(shelf, h)
    return pos, y + shelf


def unwrap(mesh, density, max_size=512):
    """Lays the model out in a texture. Returns (size, density, per-triangle pixel corners)."""
    edges = _edges(mesh)
    charts = _charts(mesh, edges)
    d = density
    while True:
        boxes, origins = [], []
        for axis, tris in charts:
            a, b = PROJECT[axis]
            pts = np.concatenate([mesh.tris[i].p[:, [a, b]] for i in tris])
            lo, hi = pts.min(0), pts.max(0)
            origins.append(lo)
            boxes.append((max(2, int(math.ceil((hi[0] - lo[0]) * d))) + 2 * PAD,
                          max(2, int(math.ceil((hi[1] - lo[1]) * d))) + 2 * PAD))
        for size in (128, 256, 512, 1024):
            if size > max_size:
                break
            pos, used = _pack(boxes, size)
            if pos is not None and used <= size:
                break
        else:
            pos = None
        if pos is not None and used <= size:
            break
        d *= 0.85
    corners = [None] * len(mesh.tris)
    for (axis, tris), (px, py), lo, (bw, bh) in zip(charts, pos, origins, boxes):
        a, b = PROJECT[axis]
        for i in tris:
            p2 = mesh.tris[i].p[:, [a, b]]
            x = px + PAD + (p2[:, 0] - lo[0]) * d
            # second axis upwards in the picture, so the art reads the right way up when viewed
            y = py + bh - PAD - (p2[:, 1] - lo[1]) * d
            corners[i] = np.stack([x, y], 1)
    return size, d, corners, edges


# --- texel data -----------------------------------------------------------------------------

def rasterize(mesh, size, corners):
    """For every texel a triangle covers: which triangle, and where in it."""
    tri_of = np.full((size, size), -1, np.int32)
    bary = np.zeros((size, size, 3), np.float32)
    for i, c in enumerate(corners):
        x0, y0 = np.floor(c.min(0) - 0.5).astype(int)
        x1, y1 = np.ceil(c.max(0) + 0.5).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = c
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-9:
            continue
        w0 = ((bx - gx) * (cy - gy) - (cx - gx) * (by - gy)) / area
        w1 = ((cx - gx) * (ay - gy) - (ax - gx) * (cy - gy)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        ys, xs = np.nonzero(inside)
        tri_of[ys + y0, xs + x0] = i
        bary[ys + y0, xs + x0] = np.stack([w0[inside], w1[inside], w2[inside]], 1)
    return tri_of, bary


def _cells(points, cell):
    keys = np.floor(points / cell).astype(np.int64)
    table = {}
    order = np.lexsort(keys.T[::-1])
    k = keys[order]
    breaks = np.nonzero(np.any(np.diff(k, axis=0) != 0, axis=1))[0] + 1
    for chunk in np.split(order, breaks):
        table[tuple(keys[chunk[0]])] = chunk
    return table


def _near(table, lo, hi, cell):
    a = np.floor(lo / cell).astype(int)
    b = np.floor(hi / cell).astype(int)
    found = [table[(x, y, z)]
             for x in range(a[0], b[0] + 1)
             for y in range(a[1], b[1] + 1)
             for z in range(a[2], b[2] + 1)
             if (x, y, z) in table]
    return np.concatenate(found) if found else np.zeros(0, np.int64)


def _hemisphere(count):
    """Cosine-weighted directions about +Z (Hammersley)."""
    out = []
    for i in range(count):
        u = (i + 0.5) / count
        bits, inv, k = i, 0.0, 0.5
        while bits:
            inv += k * (bits & 1)
            bits >>= 1
            k *= 0.5
        r, phi = math.sqrt(u), 2 * math.pi * inv
        out.append((r * math.cos(phi), r * math.sin(phi), math.sqrt(max(0.0, 1 - u))))
    return np.array(out)


def ambient_occlusion(mesh, P, N, seed=1):
    """How open each point is on the side N faces: 1 open, 0 enclosed."""
    m = len(P)
    if m == 0:
        return np.zeros(0)
    local = _hemisphere(AO_RAYS)
    # a frame round each normal, turned by a random angle so the rays don't band
    helper = np.where(np.abs(N[:, 1:2]) > 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
    tx = np.cross(N, helper)
    tx /= np.linalg.norm(tx, axis=1, keepdims=True)
    ty = np.cross(N, tx)
    ang = np.random.default_rng(seed).uniform(0, 2 * np.pi, m)
    ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
    rx, ry = ca * tx + sa * ty, -sa * tx + ca * ty
    dirs = (local[None, :, 0:1] * rx[:, None] + local[None, :, 1:2] * ry[:, None]
            + local[None, :, 2:3] * N[:, None])                       # (m, rays, 3)
    origins = P + N * 1.5e-3
    o = np.repeat(origins, AO_RAYS, axis=0)
    d = dirs.reshape(-1, 3)
    best = np.full(len(o), np.inf)

    # the floor, and the wall a wall-hung model is against
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(d[:, 1] < -1e-6, -o[:, 1] / d[:, 1], np.inf)
        best = np.minimum(best, np.where(t > 1e-4, t, np.inf))
        if mesh.wall:
            t = np.where(d[:, 2] < -1e-6, (-0.5 - o[:, 2]) / d[:, 2], np.inf)
            best = np.minimum(best, np.where(t > 1e-4, t, np.inf))

    table = _cells(origins, AO_RADIUS)
    for tri in mesh.tris:
        v0, v1, v2 = tri.p
        idx = _near(table, np.minimum(np.minimum(v0, v1), v2) - AO_RADIUS,
                    np.maximum(np.maximum(v0, v1), v2) + AO_RADIUS, AO_RADIUS)
        if len(idx) == 0:
            continue
        rays = (idx[:, None] * AO_RAYS + np.arange(AO_RAYS)[None]).ravel()
        ro, rd = o[rays], d[rays]
        e1, e2 = v1 - v0, v2 - v0
        pv = np.cross(rd, e2)
        det = pv @ e1
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = ro - v0
        u = np.einsum("ij,ij->i", tv, pv) * inv
        qv = np.cross(tv, e1)
        v = np.einsum("ij,ij->i", rd, qv) * inv
        t = (qv @ e2) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4)
        best[rays] = np.where(hit, np.minimum(best[rays], t), best[rays])

    shade = np.where(best < AO_RADIUS, 1 - best / AO_RADIUS, 0.0)
    return 1 - shade.reshape(m, AO_RAYS).mean(1)


def creases(mesh, edges):
    """Segments where faces meet at an angle, or a surface ends."""
    out = []
    for (a, b), tris in edges.items():
        if len(tris) == 1:
            out.append((a, b))
            continue
        t0 = mesh.tris[tris[0]]
        for j in tris[1:]:
            t1 = mesh.tris[j]
            if t0.group is not None and t0.group == t1.group:
                continue
            cos = float(np.clip(t0.face_normal @ t1.face_normal, -1, 1))
            if math.degrees(math.acos(cos)) > CREASE_ANGLE:
                out.append((a, b))
                break
    return np.array(out, float).reshape(-1, 2, 3)


def crease_distance(P, segs):
    dist = np.full(len(P), np.inf)
    if len(segs) == 0 or len(P) == 0:
        return dist
    table = _cells(P, max(EDGE_WIDTH, 0.05))
    cell = max(EDGE_WIDTH, 0.05)
    for a, b in segs:
        idx = _near(table, np.minimum(a, b) - EDGE_WIDTH, np.maximum(a, b) + EDGE_WIDTH, cell)
        if len(idx) == 0:
            continue
        ab = b - a
        t = np.clip((P[idx] - a) @ ab / max(ab @ ab, 1e-12), 0, 1)
        dd = np.linalg.norm(P[idx] - (a + t[:, None] * ab), axis=1)
        dist[idx] = np.minimum(dist[idx], dd)
    return dist


class Texels:
    """Everything a material needs about the texels of one material."""

    def __init__(self, P, N, ao, edge, prm, wall):
        self.P, self.N, self.ao, self.edge, self.prm, self.wall = P, N, ao, edge, prm, wall
        self.x, self.y, self.z = P[:, 0], P[:, 1], P[:, 2]
        self.n = len(P)


def bake(mesh, painters, density=128, max_size=512, seed=1):
    """Returns (texture as an RGB array, per-triangle UVs in OBJ convention)."""
    size, d, corners, edges = unwrap(mesh, density, max_size)
    tri_of, bary = rasterize(mesh, size, corners)
    ys, xs = np.nonzero(tri_of >= 0)
    ti = tri_of[ys, xs]
    w = bary[ys, xs].astype(np.float64)

    tp = np.stack([t.p for t in mesh.tris])                  # (T, 3, 3)
    tn = np.stack([t.n for t in mesh.tris])
    fn = np.stack([t.face_normal for t in mesh.tris])
    P = np.einsum("mc,mcj->mj", w, tp[ti])
    Ns = np.einsum("mc,mcj->mj", w, tn[ti])
    Ns /= np.maximum(np.linalg.norm(Ns, axis=1, keepdims=True), 1e-9)

    # faces are drawn from both sides; the side that matters is the open one
    open_out = ambient_occlusion(mesh, P, fn[ti], seed)
    open_in = ambient_occlusion(mesh, P, -fn[ti], seed + 1)
    outward = open_out >= open_in
    ao = np.where(outward, open_out, open_in)
    N = np.where(outward[:, None], Ns, -Ns)

    dist = crease_distance(P, creases(mesh, edges))
    edge = np.clip(1 - dist / EDGE_WIDTH, 0, 1) ** 2

    rgb = np.zeros((len(P), 3))
    mats = np.array([t.mat for t in mesh.tris])[ti]
    prms = [mesh.tris[i].prm for i in range(len(mesh.tris))]
    for mat in np.unique(mats):
        sel = mats == mat
        # parameters can differ between triangles of one material; paint each set apart
        groups = {}
        for k in np.nonzero(sel)[0]:
            groups.setdefault(id(prms[ti[k]]), []).append(k)
        for ks in groups.values():
            ks = np.array(ks)
            tx = Texels(P[ks], N[ks], ao[ks], edge[ks], prms[ti[ks[0]]], mesh.wall)
            rgb[ks] = painters[mat](tx)

    img = np.zeros((size, size, 3))
    img[ys, xs] = np.clip(rgb, 0, 255)
    # bleed every chart outwards so filtering and mipmaps only ever see its own colours
    empty = tri_of < 0
    if empty.any():
        _, (iy, ix) = ndimage.distance_transform_edt(empty, return_indices=True)
        img = img[iy, ix]

    uvs = [np.stack([c[:, 0] / size, 1 - c[:, 1] / size], 1) for c in corners]
    return img.astype(np.uint8), uvs, d
