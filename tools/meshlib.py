"""Triangle meshes for the model pack, authored Y-up, and writing them as Viewpoint OBJs.

Authored axes: X east, Y up, Z south (a model's front). A wall-hung model has its back
against the -Z edge of the tile (a north wall). Viewpoint reads OBJs in the game's world
axes (X east, Y south, Z up); write_obj converts.
"""

import math

import numpy as np

WALL = -0.5  # the back edge of the tile


class Tri:
    __slots__ = ("p", "n", "mat", "prm", "group")

    def __init__(self, p, n, mat, prm, group):
        self.p, self.n, self.mat, self.prm, self.group = p, n, mat, prm, group

    @property
    def face_normal(self):
        fn = np.cross(self.p[1] - self.p[0], self.p[2] - self.p[0])
        ln = np.linalg.norm(fn)
        return fn / ln if ln else np.array([0.0, 1.0, 0.0])


class Mesh:
    """Triangles, each with a material name, the material's parameters and corner normals.

    wall: the model hangs on (or stands against) the north wall, which then shades it.
    occluders: triangles that shade the model when it is baked but are not part of it
    (the shelf under a shelf's goods)."""

    def __init__(self, wall=False, occluders=None, ao_radius=None):
        self.tris = []
        self.wall = wall
        self.occluders = occluders or []
        self.ao_radius = ao_radius
        self._groups = 0

    def group(self):
        """A new smooth group: edges inside one are never treated as creases."""
        self._groups += 1
        return self._groups

    def tri(self, a, b, c, mat, prm=None, normals=None, group=None):
        """One triangle, corners counter-clockwise seen from outside."""
        t = Tri(np.array([a, b, c], float), None, mat, prm if prm is not None else {}, group)
        t.n = np.array(normals, float) if normals is not None else np.tile(t.face_normal, (3, 1))
        self.tris.append(t)

    def quad(self, a, b, c, d, mat, prm=None):
        self.tri(a, b, c, mat, prm)
        self.tri(a, c, d, mat, prm)

    def box(self, x0, x1, y0, y1, z0, z1, mat, top=None, front=None, prm=None, top_prm=None):
        top = top or mat
        front = front or mat
        self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), front, prm)  # +Z
        self.quad((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), mat, prm)    # -Z
        self.quad((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), mat, prm)    # +X
        self.quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0), mat, prm)    # -X
        self.quad((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0), top,
                  top_prm if top_prm is not None else prm)                             # +Y
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), mat, prm)    # -Y

    def obox(self, cx, cz, y0, sx, sy, sz, yaw, mat, prm=None, top=None, top_prm=None):
        """A box standing on y0, centred on (cx, cz), sx by sz across, sy tall, turned by yaw
        degrees about the vertical (for things set down not quite square)."""
        a = math.radians(yaw)
        ca, sa = math.cos(a), math.sin(a)

        def at(lx, y, lz):
            return (cx + lx * ca - lz * sa, y, cz + lx * sa + lz * ca)
        x0, x1, z0, z1, y1 = -sx / 2, sx / 2, -sz / 2, sz / 2, y0 + sy
        top = top or mat
        tp = top_prm if top_prm is not None else prm
        self.quad(at(x0, y0, z1), at(x1, y0, z1), at(x1, y1, z1), at(x0, y1, z1), mat, prm)  # front
        self.quad(at(x1, y0, z0), at(x0, y0, z0), at(x0, y1, z0), at(x1, y1, z0), mat, prm)  # back
        self.quad(at(x1, y0, z1), at(x1, y0, z0), at(x1, y1, z0), at(x1, y1, z1), mat, prm)
        self.quad(at(x0, y0, z0), at(x0, y0, z1), at(x0, y1, z1), at(x0, y1, z0), mat, prm)
        self.quad(at(x0, y1, z1), at(x1, y1, z1), at(x1, y1, z0), at(x0, y1, z0), top, tp)   # top
        self.quad(at(x0, y0, z0), at(x1, y0, z0), at(x1, y0, z1), at(x0, y0, z1), mat, prm)  # bottom

    def lathe(self, cx, cz, rings, mat, segments=12, a0=0.0, a1=360.0, top=None, bottom=None,
              close_back=False, prm=None, top_prm=None, bottom_prm=None):
        """A vertical solid of revolution with an elliptical section, smooth-shaded round.

        rings: [(y, rx, rz), ...] from bottom to top. a0..a1 limits the sweep (degrees,
        0 = +X, 90 = +Z) so a half sweep makes a shape that sits flat against a wall.
        top/bottom: material for the caps (None leaves the cap off)."""
        full = (a1 - a0) >= 360.0
        n = segments
        angles = [math.radians(a0 + (a1 - a0) * i / n) for i in range(n + 1)]
        smooth = self.group()

        def at(ring, a):
            y, rx, rz = ring
            return (cx + rx * math.cos(a), y, cz + rz * math.sin(a))

        def normal(i, a):
            # the surface (a, t) -> (cx + rx(t) cos a, y(t), cz + rz(t) sin a), its slope taken
            # across the neighbouring rings
            lo, hi = rings[max(i - 1, 0)], rings[min(i + 1, len(rings) - 1)]
            dy, drx, drz = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
            _, rx, rz = rings[i]
            da = np.array([-rx * math.sin(a), 0.0, rz * math.cos(a)])
            dt = np.array([drx * math.cos(a), dy, drz * math.sin(a)])
            nv = np.cross(da, dt)
            if nv @ np.array([math.cos(a), 0.0, math.sin(a)]) < 0:
                nv = -nv
            ln = np.linalg.norm(nv)
            return nv / ln if ln else np.array([math.cos(a), 0.0, math.sin(a)])

        for i in range(len(rings) - 1):
            r0, r1 = rings[i], rings[i + 1]
            for j in range(n):
                a, b = angles[j], angles[j + 1]
                p00, p01, p10, p11 = at(r0, a), at(r0, b), at(r1, a), at(r1, b)
                n00, n01, n10, n11 = normal(i, a), normal(i, b), normal(i + 1, a), normal(i + 1, b)
                # angles increase towards +Z from +X, so b-then-a is counter-clockwise outside
                self.tri(p01, p00, p10, mat, prm, (n01, n00, n10), smooth)
                self.tri(p01, p10, p11, mat, prm, (n01, n10, n11), smooth)

        def cap(ring, cap_mat, cap_prm, up):
            y, _, _ = ring
            centre = (cx, y, cz)
            for j in range(n):
                a, b = at(ring, angles[j]), at(ring, angles[j + 1])
                if up:
                    self.tri(centre, b, a, cap_mat, cap_prm)
                else:
                    self.tri(centre, a, b, cap_mat, cap_prm)

        if top:
            cap(rings[-1], top, top_prm if top_prm is not None else prm, True)
        if bottom:
            cap(rings[0], bottom, bottom_prm if bottom_prm is not None else prm, False)
        if close_back and not full:
            # flat face along the cut, facing away from the sweep
            for r0, r1 in zip(rings, rings[1:]):
                a, b = at(r0, angles[0]), at(r0, angles[-1])
                c, d = at(r1, angles[-1]), at(r1, angles[0])
                self.quad(b, a, d, c, mat, prm)


def write_obj(mesh, uvs, path, mtl):
    """uvs: one (3, 2) array per triangle, OBJ convention (v up from the bottom).

    Every face is written both ways round: Viewpoint mirrors the file on loading and draws
    faces one-sided, so this keeps the models whole whichever side it takes for the front."""
    out = ["# ViewpointModelFix, built by tools/build_models.py", f"mtllib {mtl}"]
    faces = []
    k = 0
    for t, uv in zip(mesh.tris, uvs):
        for c in range(3):
            x, y, z = t.p[c]
            out.append("v %.4f %.4f %.4f" % (x, z, y))  # authored y-up -> Viewpoint z-up
        for c in range(3):
            out.append("vt %.5f %.5f" % (uv[c][0], uv[c][1]))
        for c in range(3):
            x, y, z = t.n[c]
            out.append("vn %.4f %.4f %.4f" % (x, z, y))
        for c in range(3):
            x, y, z = t.n[c]
            out.append("vn %.4f %.4f %.4f" % (-x, -z, -y))
        v, n = 3 * k + 1, 6 * k + 1
        # swapping y and z mirrors, so the authored order now winds the other way
        faces.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (v + 2, v + 2, n + 2, v + 1, v + 1, n + 1, v, v, n))
        faces.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (v, v, n + 3, v + 1, v + 1, n + 4, v + 2, v + 2, n + 5))
        k += 1
    out.append("usemtl model")
    out.extend(faces)
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
