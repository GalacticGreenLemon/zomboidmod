"""What each material looks like: worn, grimy and muted, to sit in Project Zomboid's world.

A painter takes bake.Texels (position, normal, openness, nearness to an edge, the material's
parameters) and returns RGB 0..255 for each texel. Positions are authored: Y up, Z the
model's front, the tile's centre at the origin.
"""

import numpy as np

from bake import fbm, vnoise


def C(r, g, b):
    return np.array([r, g, b], float)


def mix(a, b, t):
    t = np.clip(t, 0, 1)[:, None]
    return a * (1 - t) + b * t


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def stretch(P, sx, sy, sz):
    return np.stack([P[:, 0] * sx, P[:, 1] * sy, P[:, 2] * sz], 1)


def vertical(tx):
    return 1 - np.abs(tx.N[:, 1])


def facing_up(tx):
    return np.clip(tx.N[:, 1], 0, 1)


GRIME = C(88, 78, 62)
DUST = C(146, 136, 116)
STAIN = C(152, 126, 82)
RUST = C(118, 68, 36)


def finish(c, tx):
    """Shade what is enclosed; Viewpoint lights the rest."""
    return c * (0.64 + 0.36 * tx.ao)[:, None]


def weathered(tx, base, warm, seed, dirt=1.0, floor=True):
    """Shared wear: tint, grime in crevices, floor dirt, drips, dust, specks, chipped edges."""
    P = tx.P
    c = mix(base, warm, fbm(P * 3.0, 3, seed) * 1.5 - 0.45)
    c = c + ((fbm(P * 22, 3, seed + 1) - 0.5) * 16)[:, None]
    c = mix(c, GRIME, (1 - tx.ao) ** 1.3 * 0.9 * dirt)
    if floor:
        c = mix(c, GRIME, smooth(0.18, 0.0, tx.y) * 0.6 * dirt)
    drip = fbm(stretch(P, 13, 1.6, 13), 4, seed + 2) * (0.6 + 0.4 * fbm(P * 4, 2, seed + 6))
    c = mix(c, DUST * 0.82, smooth(0.5, 0.7, drip) * vertical(tx) * 0.38 * dirt)
    c = mix(c, DUST, facing_up(tx) ** 2 * fbm(P * 9, 2, seed + 3) * 0.4 * dirt)
    speck = vnoise(P * 150, seed + 4)
    c = mix(c, GRIME * 0.8, smooth(0.93, 0.99, speck) * 0.45 * dirt)
    chips = smooth(0.55, 0.75, vnoise(P * 45, seed + 5))
    c = mix(c, GRIME, tx.edge * chips * 0.5 * dirt)
    return c


# --- porcelain and plumbing -----------------------------------------------------------------

PORCELAIN = C(202, 197, 182)
PORCELAIN_WARM = C(192, 180, 150)


def porcelain(tx):
    return finish(weathered(tx, PORCELAIN, PORCELAIN_WARM, 11), tx)


def seat(tx):
    return finish(weathered(tx, C(204, 197, 178), C(190, 176, 140), 21), tx)


def inner(tx):
    """The inside of a urinal: stained from the top down, worst at the bottom."""
    P = tx.P
    c = weathered(tx, C(194, 189, 172), C(182, 166, 126), 61, floor=False)
    streak = fbm(stretch(P, 32, 1.6, 32), 3, 62)
    low = smooth(0.96, 0.66, tx.y)
    c = mix(c, STAIN, smooth(0.42, 0.68, streak) * 0.6 + low * 0.35)
    return finish(c, tx)


def basin(tx):
    """A bowl seen from above: rim, the bowl falling into shade, water, stains and the drain.

    prm: cx, cz, rx, rz the bowl's ellipse; water: radius of the water (fraction), if any;
    drain: (x, z) if not the centre; tap: (x, z) of a tap that drips rust towards the drain."""
    p = tx.prm
    P = tx.P
    dx, dz = (tx.x - p["cx"]) / p["rx"], (tx.z - p["cz"]) / p["rz"]
    d = np.sqrt(dx * dx + dz * dz)
    c = weathered(tx, PORCELAIN, PORCELAIN_WARM, 31, floor=False)
    inside = smooth(0.94, 0.84, d)
    c = mix(c, C(136, 132, 116), inside * (1 - d / 0.92) * 0.6)
    if "water" in p:
        w = p["water"]
        c = mix(c, C(112, 110, 88), smooth(w + 0.03, w - 0.05, d) * 0.85)
        tide = np.exp(-((d - w) / 0.06) ** 2) * (0.55 + 0.45 * fbm(P * 20, 2, 32))
        c = mix(c, STAIN * 0.85, tide * 0.8)
    c = mix(c, STAIN, inside * smooth(0.5, 0.72, fbm(P * 9, 3, 33)) * 0.45)
    drain = p.get("drain", (p["cx"], p["cz"]))
    dd = np.hypot(tx.x - drain[0], tx.z - drain[1])
    c = mix(c, RUST, smooth(0.07, 0.035, dd) * 0.6)
    c = mix(c, C(44, 40, 36), smooth(0.034, 0.024, dd))
    if "tap" in p:
        # a rust trail from where the tap drips down to the drain
        a, b = np.array(p["tap"]), np.array(drain)
        ab = b - a
        q = np.stack([tx.x, tx.z], 1)
        t = np.clip((q - a) @ ab / (ab @ ab), 0, 1)
        off = np.linalg.norm(q - (a + t[:, None] * ab), axis=1)
        wobble = (fbm(P * 30, 2, 34) - 0.5) * 0.02
        c = mix(c, RUST, smooth(0.028, 0.008, off + wobble) * (0.35 + 0.4 * t))
    return finish(c, tx)


def chrome(tx):
    P = tx.P
    brushed = vnoise(stretch(P, 140, 5, 140), 71)
    c = C(146, 147, 142) + ((brushed - 0.5) * 34)[:, None]
    c = mix(c, C(110, 106, 92), smooth(0.48, 0.74, fbm(P * 14, 3, 72)) * 0.65)
    rust = smooth(0.6, 0.8, fbm(P * 24, 3, 73)) * (0.45 + 0.55 * (1 - tx.ao))
    c = mix(c, RUST, rust * 0.8)
    c = mix(c, C(196, 196, 188), tx.edge * 0.3)
    c = mix(c, GRIME, (1 - tx.ao) ** 1.4 * 0.7)
    return finish(c, tx)


def drain(tx):
    return finish(C(46, 43, 40) + ((vnoise(tx.P * 80, 81) - 0.5) * 12)[:, None], tx)


# --- furniture ------------------------------------------------------------------------------

def wood(tx):
    """prm grain: the axis the grain runs along (0 x, 1 y, 2 z)."""
    P = tx.P
    a = tx.prm.get("grain", 2)
    o0, o1 = [i for i in range(3) if i != a]
    warp = fbm(stretch(P, *[2 if i == a else 7 for i in range(3)]), 3, 91) * 5
    rings = 0.5 + 0.5 * np.sin((P[:, o0] + 0.6 * P[:, o1]) * 70 + warp)
    fine = vnoise(stretch(P, *[5 if i == a else 180 for i in range(3)]), 92)
    c = mix(C(88, 58, 36), C(134, 92, 56), rings * 0.55 + fine * 0.45)
    c = mix(c, C(166, 126, 84), tx.edge * smooth(0.35, 0.65, vnoise(P * 28, 93)) * 0.7)
    scratch = vnoise(stretch(P, *[300 if i == a else 9 for i in range(3)]), 94)
    c = mix(c, C(150, 112, 74), smooth(0.9, 0.97, scratch) * 0.5)
    c = mix(c, GRIME, (1 - tx.ao) ** 1.3 * 0.75)
    c = mix(c, GRIME, smooth(0.14, 0.0, tx.y) * 0.45)
    return finish(c, tx)


def blanket(colour, seed):
    base = C(*colour)

    def paint(tx):
        P = tx.P
        c = base + ((vnoise(P * 240, seed) - 0.5) * 16)[:, None]
        folds = fbm(stretch(P, 4.0, 3.0, 2.2), 4, seed + 1)
        c = c * (0.78 + 0.36 * folds)[:, None]
        stain = smooth(0.64, 0.8, fbm(P * 5, 3, seed + 2))
        c = mix(c, c * 0.68 + C(34, 26, 12), stain * 0.6)
        pill = smooth(0.8, 0.92, vnoise(P * 120, seed + 3))
        c = mix(c, c * 1.12, pill * 0.5)
        hem = smooth(0.40, 0.34, tx.y) * vertical(tx)
        c = mix(c, c * 0.72, hem)
        c = mix(c, GRIME, (1 - tx.ao) ** 1.3 * 0.6)
        return finish(c, tx)
    return paint


def mattress(tx):
    P = tx.P
    c = C(192, 186, 166) + ((vnoise(P * 200, 101) - 0.5) * 10)[:, None]
    c = mix(c, STAIN, smooth(0.6, 0.78, fbm(P * 6, 3, 102)) * 0.55)
    c = mix(c, GRIME, (1 - tx.ao) ** 1.2 * 0.7)
    return finish(c, tx)


def darkmetal(tx):
    P = tx.P
    c = C(66, 70, 66) + ((fbm(P * 12, 3, 111) - 0.5) * 18)[:, None]
    scratch = vnoise(stretch(P, 9, 320, 320), 112)
    c = mix(c, C(128, 128, 120), smooth(0.92, 0.98, scratch) * 0.6)
    c = mix(c, C(124, 122, 114), tx.edge * smooth(0.4, 0.7, vnoise(P * 30, 113)) * 0.7)
    rust = smooth(0.58, 0.78, fbm(P * 10, 3, 114)) * (smooth(0.5, 0.0, tx.y) * 0.7 + (1 - tx.ao))
    c = mix(c, RUST, rust * 0.8)
    c = mix(c, GRIME, (1 - tx.ao) ** 1.3 * 0.6)
    return finish(c, tx)


def cardboard(tx):
    P = tx.P
    c = C(160, 122, 78) + ((vnoise(P * 220, 121) - 0.5) * 18)[:, None]
    c = mix(c, C(118, 88, 56), tx.edge * 0.7)
    wet = fbm(P * 5, 3, 122)
    c = mix(c, C(128, 94, 58), smooth(0.56, 0.68, wet) * 0.55)
    c = mix(c, GRIME, smooth(0.1, 0.0, tx.y) * 0.5 + (1 - tx.ao) ** 1.3 * 0.6)
    return finish(c, tx)


def tape(tx):
    c = C(190, 166, 114) + ((vnoise(tx.P * 160, 131) - 0.5) * 14)[:, None]
    c = mix(c, GRIME, tx.edge * 0.5 + (1 - tx.ao) * 0.5)
    return finish(c, tx)


# --- wall fittings --------------------------------------------------------------------------

def plastic(tx):
    """prm touched: (x, y) where hands go, left grubby."""
    c = weathered(tx, C(196, 188, 164), C(180, 166, 124), 141, dirt=0.8, floor=False)
    if "touched" in tx.prm:
        x, y = tx.prm["touched"]
        near = np.hypot(tx.x - x, tx.y - y)
        c = mix(c, GRIME, smooth(0.06, 0.0, near) * 0.45)
    return finish(c, tx)


def glass(tx):
    """A mirror reflecting a dim room. prm rect: (x0, x1, y0, y1) of the glass."""
    P = tx.P
    c = mix(C(72, 76, 76), C(128, 134, 132), smooth(1.0, 1.85, tx.y))
    band = np.abs(((tx.x * 1.2 + tx.y * 0.9) % 0.7) - 0.35)
    c = mix(c, C(150, 156, 152), smooth(0.07, 0.0, band - 0.02) * 0.3)
    c = mix(c, C(140, 134, 116), smooth(0.48, 0.8, fbm(P * 7, 4, 151)) * 0.4)
    x0, x1, y0, y1 = tx.prm["rect"]
    border = np.minimum(np.minimum(tx.x - x0, x1 - tx.x), np.minimum(tx.y - y0, y1 - tx.y))
    creep = border + (fbm(P * 12, 3, 152) - 0.5) * 0.12
    c = mix(c, C(32, 28, 24), smooth(0.07, 0.0, creep) * smooth(0.4, 0.62, fbm(P * 26, 3, 153)))
    speck = smooth(0.9, 0.97, vnoise(P * 140, 154))
    c = mix(c, C(36, 32, 28), speck * 0.7)
    return finish(c, tx)


PAINTERS = {
    "porcelain": porcelain,
    "seat": seat,
    "inner": inner,
    "basin": basin,
    "chrome": chrome,
    "drain": drain,
    "wood": wood,
    "mattress": mattress,
    "blanket": blanket((170, 154, 124), 161),
    "blanket_blue": blanket((80, 100, 136), 171),
    "blanket_red": blanket((140, 60, 56), 181),
    "blanket_green": blanket((80, 106, 72), 191),
    "darkmetal": darkmetal,
    "cardboard": cardboard,
    "tape": tape,
    "plastic": plastic,
    "glass": glass,
}
