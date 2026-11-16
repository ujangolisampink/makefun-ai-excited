#!/usr/bin/env python3
"""Koi to Dragon — a golden koi leaps out of dark water and becomes a dragon
mid-leap, silhouetted against a huge gold moon.

Drawn from scratch with the Python standard library only. The scene is
rasterised on a 2x supersampled canvas, downsampled to 1024x1024, given a
soft glow pass, and written out as a deterministic PNG: running this program
twice produces byte-identical output.

Usage: python3 main.py  ->  writes /output/entry.png
       OUT=/some/path.png python3 main.py  ->  writes there instead.
"""

import binascii
import math
import os
import struct
import zlib

# ---------------------------------------------------------------------------
# PNG encoding (stdlib only)
# ---------------------------------------------------------------------------

def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    return out


def encode_png(rgb, width, height):
    """Encode a flat RGB bytes buffer (row-major, 3 bytes per pixel)."""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter: none
        raw += rgb[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# Canvas: a supersampled RGB buffer with flat-vector drawing primitives.
# Design coordinates are 0..1024; SS scales them to the backing buffer.
# ---------------------------------------------------------------------------

SS = 2            # supersample factor
SIZE = 1024       # design size (output is SIZE x SIZE)
W = SIZE * SS     # backing buffer width/height in pixels


class Canvas:
    def __init__(self):
        self.buf = bytearray(W * W * 3)

    # -- low level ------------------------------------------------------
    def _off(self, x, y):
        return (y * W + x) * 3

    def blend_px(self, x, y, rgb, alpha):
        """Blend one backing-buffer pixel towards rgb by alpha (0..1)."""
        if x < 0 or y < 0 or x >= W or y >= W:
            return
        o = self._off(x, y)
        ia = 1.0 - alpha
        self.buf[o] = int(self.buf[o] * ia + rgb[0] * alpha + 0.5)
        self.buf[o + 1] = int(self.buf[o + 1] * ia + rgb[1] * alpha + 0.5)
        self.buf[o + 2] = int(self.buf[o + 2] * ia + rgb[2] * alpha + 0.5)

    def span(self, y, x0, x1, rgb, alpha=1.0):
        """Fill backing-buffer row y from x0 to x1 (inclusive) solid."""
        if y < 0 or y >= W:
            return
        x0 = max(0, int(math.floor(x0)))
        x1 = min(W - 1, int(math.ceil(x1)))
        if x1 < x0:
            return
        if alpha >= 1.0:
            pat = bytes(rgb) * (x1 - x0 + 1)
            o = self._off(x0, y)
            self.buf[o:o + len(pat)] = pat
        else:
            for x in range(x0, x1 + 1):
                self.blend_px(x, y, rgb, alpha)

    # -- shapes (design coordinates) ------------------------------------
    def poly(self, pts, rgb, alpha=1.0):
        """Scanline-fill a polygon given in design coordinates."""
        if len(pts) < 3:
            return
        p = [(x * SS, y * SS) for x, y in pts]
        n = len(p)
        ymin = max(0, int(math.floor(min(q[1] for q in p))))
        ymax = min(W - 1, int(math.ceil(max(q[1] for q in p))))
        edges = []
        for i in range(n):
            x0, y0 = p[i]
            x1, y1 = p[(i + 1) % n]
            if y0 == y1:
                continue
            edges.append((x0, y0, x1, y1))
        for y in range(ymin, ymax + 1):
            yc = y + 0.5
            xs = []
            for x0, y0, x1, y1 in edges:
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.span(y, xs[i], xs[i + 1], rgb, alpha)

    def disc(self, cx, cy, r, rgb, alpha=1.0):
        """Filled circle, design coordinates."""
        cx *= SS
        cy *= SS
        r *= SS
        y0 = max(0, int(math.floor(cy - r)))
        y1 = min(W - 1, int(math.ceil(cy + r)))
        for y in range(y0, y1 + 1):
            dy = (y + 0.5) - cy
            h2 = r * r - dy * dy
            if h2 <= 0:
                continue
            h = math.sqrt(h2)
            self.span(y, cx - h, cx + h, rgb, alpha)

    def ellipse(self, cx, cy, rx, ry, rgb, alpha=1.0):
        cx *= SS
        cy *= SS
        rx *= SS
        ry *= SS
        y0 = max(0, int(math.floor(cy - ry)))
        y1 = min(W - 1, int(math.ceil(cy + ry)))
        for y in range(y0, y1 + 1):
            dy = ((y + 0.5) - cy) / ry
            h2 = 1.0 - dy * dy
            if h2 <= 0:
                continue
            h = math.sqrt(h2) * rx
            self.span(y, cx - h, cx + h, rgb, alpha)

    def stroke(self, pts, width, rgb, alpha=1.0):
        """Thick polyline through design-coordinate points."""
        if len(pts) < 2:
            return
        w = width * SS / 2.0
        for i in range(len(pts) - 1):
            x0, y0 = pts[i][0] * SS, pts[i][1] * SS
            x1, y1 = pts[i + 1][0] * SS, pts[i + 1][1] * SS
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy)
            if ln == 0:
                continue
            nx, ny = -dy / ln * w, dx / ln * w
            self.poly(
                [
                    ((x0 + nx) / SS, (y0 + ny) / SS),
                    ((x1 + nx) / SS, (y1 + ny) / SS),
                    ((x1 - nx) / SS, (y1 - ny) / SS),
                    ((x0 - nx) / SS, (y0 - ny) / SS),
                ],
                rgb,
                alpha,
            )
            self.disc(pts[i][0], pts[i][1], width / 2.0, rgb, alpha)
        self.disc(pts[-1][0], pts[-1][1], width / 2.0, rgb, alpha)

    def arc_stroke(self, cx, cy, rx, ry, a0, a1, width, rgb, alpha=1.0, steps=48):
        """Stroke an elliptical arc (angles in radians)."""
        pts = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
        self.stroke(pts, width, rgb, alpha)

    def vgrad(self, stops):
        """Vertical gradient. stops: list of (y_design, (r,g,b))."""
        for y in range(W):
            yd = y / SS
            col = stops[-1][1]
            for i in range(len(stops) - 1):
                y0, c0 = stops[i]
                y1, c1 = stops[i + 1]
                if y0 <= yd <= y1:
                    t = 0.0 if y1 == y0 else (yd - y0) / (y1 - y0)
                    col = (
                        int(c0[0] + (c1[0] - c0[0]) * t + 0.5),
                        int(c0[1] + (c1[1] - c0[1]) * t + 0.5),
                        int(c0[2] + (c1[2] - c0[2]) * t + 0.5),
                    )
                    break
            self.span(y, 0, W - 1, col)


def cubic(p0, p1, p2, p3, t):
    """Point on a cubic bezier at t, plus the tangent angle."""
    mt = 1.0 - t
    x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
    dx = 3 * mt * mt * (p1[0] - p0[0]) + 6 * mt * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
    dy = 3 * mt * mt * (p1[1] - p0[1]) + 6 * mt * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
    return (x, y), math.atan2(dy, dx)


def lcg(seed, count):
    """Deterministic pseudo-random numbers in [0, 1)."""
    out = []
    s = seed & 0xFFFFFFFF
    for _ in range(count):
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        out.append(s / 4294967296.0)
    return out

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
INK = (10, 15, 46)        # deep indigo sky top
SKY_MID = (19, 27, 76)
WATER = (7, 11, 32)       # dark water bottom
GOLD = (233, 168, 59)     # body gold
GOLD_LT = (248, 220, 126) # belly / highlight gold
GOLD_DK = (168, 110, 18)  # scale lines
FLAME = (232, 93, 26)     # mane flame orange
EMBER = (242, 169, 59)
DRAGON_DK = (23, 18, 51)  # dragon silhouette
MOON = (246, 196, 69)
MOON_DK = (232, 163, 31)
FOAM = (234, 242, 255)
EYE = (255, 243, 196)

WATERLINE = 800.0
MOON_C = (690.0, 290.0)
MOON_R = 215.0


def draw_sky(c):
    c.vgrad(
        [
            (0, INK),
            (480, SKY_MID),
            (WATERLINE, (11, 16, 48)),
            (SIZE, WATER),
        ]
    )
    # stars: fixed LCG positions, kept clear of the moon disc
    rnd = lcg(20261117, 260)
    for i in range(86):
        x = rnd[i * 3] * SIZE
        y = rnd[i * 3 + 1] * 690.0
        r = 0.8 + rnd[i * 3 + 2] * 1.8
        dx, dy = x - MOON_C[0], y - MOON_C[1]
        if dx * dx + dy * dy < (MOON_R + 34) ** 2:
            continue
        a = 0.30 + 0.55 * rnd[(i * 7 + 5) % 260]
        c.disc(x, y, r, (207, 224, 255), a)


def draw_moon(c):
    # the halo itself is added in the post pass (smooth radial glow);
    # here only the flat disc, a few quiet craters and a bright upper rim
    c.disc(MOON_C[0], MOON_C[1], MOON_R, MOON, 1.0)
    for (x, y, r) in [(612, 218, 26), (742, 350, 18), (668, 372, 12), (776, 236, 14)]:
        c.disc(x, y, r, (226, 156, 30), 0.22)
    c.arc_stroke(MOON_C[0], MOON_C[1], MOON_R - 4, MOON_R - 4,
                math.pi * 1.08, math.pi * 1.92, 7, (255, 226, 140), 0.9)


def draw_water(c):
    # moon reflection: short horizontal dashes under the moon
    rnd = lcg(777, 90)
    for i in range(26):
        y = WATERLINE + 14 + rnd[i * 3] * 190
        wdt = 26 + rnd[i * 3 + 1] * 120
        x = MOON_C[0] - wdt / 2 + (rnd[i * 3 + 2] - 0.5) * 70
        a = 0.10 + 0.22 * (1.0 - (y - WATERLINE) / 210.0)
        c.stroke([(x, y), (x + wdt, y)], 3.0, (246, 196, 69), max(0.0, a))
    # faint distant ridge line on the horizon
    c.stroke([(0, WATERLINE), (SIZE, WATERLINE)], 2.0, (30, 40, 92), 0.8)


# -- the koi-dragon ---------------------------------------------------------
# Spine: cubic bezier from the tail in the water up to the head at the moon.
SPINE = ((165.0, 885.0), (275.0, 655.0), (505.0, 468.0), (722.0, 372.0))


def spine_points(n=46):
    pts = []
    for i in range(n + 1):
        t = i / n
        pt, ang = cubic(*SPINE, t)
        pts.append((t, pt, ang))
    return pts


def half_width(t):
    """Body half-width along the spine (design px)."""
    if t < 0.12:
        return 13.0 + 90.0 * t
    if t < 0.45:
        return 23.8 + 34.0 * (t - 0.12)
    # gentle taper through the dragon half so the neck stays thick
    return 35.0 - 11.0 * ((t - 0.45) / 0.55)


def body_outline(pts, shrink=0.0):
    left, right = [], []
    for t, (x, y), ang in pts:
        hw = max(2.0, half_width(t) - shrink)
        nx, ny = -math.sin(ang), math.cos(ang)
        left.append((x + nx * hw, y + ny * hw))
        right.append((x - nx * hw, y - ny * hw))
    return left + right[::-1]


def horn(c, base, ctrl, tip, w0, w1, col, steps=16):
    """A tapered curved horn: a quadratic bezier swept with shrinking width."""
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = mt * mt * base[0] + 2 * mt * t * ctrl[0] + t * t * tip[0]
        y = mt * mt * base[1] + 2 * mt * t * ctrl[1] + t * t * tip[1]
        dx = 2 * mt * (ctrl[0] - base[0]) + 2 * t * (tip[0] - ctrl[0])
        dy = 2 * mt * (ctrl[1] - base[1]) + 2 * t * (tip[1] - ctrl[1])
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        w = w0 + (w1 - w0) * t
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    c.poly(left + right[::-1], col)


def flame_tuft(c, base, ang, length, width, col, bend=0.0):
    """A flame-shaped tuft: a tapered, slightly curved triangle from base.
    bend bows the tip sideways (perpendicular) for a licking-flame look."""
    dx, dy = math.cos(ang), math.sin(ang)
    px, py = -dy, dx
    tip = (base[0] + dx * length + px * bend * length,
           base[1] + dy * length + py * bend * length)
    mid = (base[0] + dx * length * 0.55 + px * (width * 0.55 + bend * length * 0.5),
           base[1] + dy * length * 0.55 + py * (width * 0.55 + bend * length * 0.5))
    c.poly(
        [
            (base[0] + px * width, base[1] + py * width),
            mid,
            tip,
            (base[0] - px * width, base[1] - py * width),
        ],
        col,
    )


def draw_koi_dragon(c):
    pts = spine_points()

    # tail fin: a broad flowing fan sweeping back from the tail base,
    # two lobes with ray lines, trailing in the leap's wake
    t0, p0, a0 = pts[0]
    back = a0 + math.pi
    def lobe(ang_off, length, spread, col):
        edge = []
        for i in range(15):
            s = i / 14.0
            bow = math.sin(s * math.pi) * spread
            edge.append((p0[0] + math.cos(back + ang_off) * length * s
                         - math.sin(back + ang_off) * bow,
                         p0[1] + math.sin(back + ang_off) * length * s
                         + math.cos(back + ang_off) * bow))
        c.poly([p0] + edge, col, 0.92)
        # ray lines fanning out inside the lobe
        for f in (0.35, 0.6, 0.85):
            ex = p0[0] + math.cos(back + ang_off) * length * f
            ey = p0[1] + math.sin(back + ang_off) * length * f
            c.stroke([p0, (ex, ey)], 3.0, GOLD_DK, 0.8)
        c.stroke(edge, 3.0, (248, 220, 126), 0.7)
    lobe(0.30, 168, 46, (232, 138, 32))
    lobe(-0.34, 138, 36, GOLD)

    # body: gold base, then a soft light belly on the lower side
    c.poly(body_outline(pts), GOLD)
    inner = []
    for t, (x, y), ang in pts:
        hw = half_width(t)
        nx, ny = -math.sin(ang), math.cos(ang)
        inner.append((x - nx * hw * 0.35 + nx * 3, y - ny * hw * 0.35 + ny * 3))
    inner += [(x - (-math.sin(a)) * (half_width(t) * 1.0),
               y - (math.cos(a)) * (half_width(t) * 1.0)) for t, (x, y), a in pts[::-1]]
    c.poly(inner, GOLD_LT, 0.45)
    # moonlit rim along the upper (moon-facing) edge of the body
    rim = []
    for t, (x, y), ang in pts:
        hw = half_width(t)
        nx, ny = -math.sin(ang), math.cos(ang)
        rim.append((x - nx * (hw - 1), y - ny * (hw - 1)))
    c.stroke(rim, 3.0, (255, 232, 160), 0.85)

    # scales on the fish half (t < 0.45): a few large scallop arcs
    for i in range(0, 13):
        t = 0.07 + i * 0.03
        pt, ang = cubic(*SPINE, t)
        hw = half_width(t)
        nx, ny = -math.sin(ang), math.cos(ang)
        for k in (-0.5, 0.05, 0.55):
            cx = pt[0] + nx * hw * k
            cy = pt[1] + ny * hw * k
            c.arc_stroke(cx, cy, 15, 15, ang - 0.4, ang + math.pi + 0.4,
                         2.6, GOLD_DK, 0.75, steps=14)

    # dorsal fin: a low serrated gold ridge on the upper edge
    ridge = []
    for i in range(13):
        t = 0.08 + i * 0.032
        pt, ang = cubic(*SPINE, t)
        hw = half_width(t)
        nx, ny = -math.sin(ang), math.cos(ang)
        ridge.append((pt[0] - nx * (hw + 3), pt[1] - ny * (hw + 3)))
        ridge.append((pt[0] - nx * (hw + 15 + 6 * math.sin(i * 2.1)),
                      pt[1] - ny * (hw + 15 + 6 * math.sin(i * 2.1))))
    c.poly(ridge, (232, 138, 32), 0.95)

    # mane: large layered flames streaming back along the upper edge,
    # growing out of the dorsal ridge as the fish becomes a dragon
    for i, t in enumerate((0.52, 0.60, 0.68, 0.76, 0.84, 0.92)):
        pt, ang = cubic(*SPINE, t)
        hw = half_width(t)
        nx, ny = -math.sin(ang), math.cos(ang)
        base = (pt[0] - nx * (hw - 2), pt[1] - ny * (hw - 2))
        a = ang + math.pi + 0.15
        ln = 74 - 5 * i
        flame_tuft(c, base, a, ln, 18, FLAME if i % 2 == 0 else EMBER,
                   bend=0.6)
        flame_tuft(c, base, a, ln * 0.62, 10, GOLD_LT, bend=0.6)

    # pectoral fin near the transition, swept back
    pt, ang = cubic(*SPINE, 0.48)
    hw = half_width(0.48)
    nx, ny = -math.sin(ang), math.cos(ang)
    base = (pt[0] - nx * hw, pt[1] - ny * hw)
    c.poly(
        [base,
         (base[0] - 52, base[1] + 44),
         (base[0] - 30, base[1] + 52),
         (base[0] - 6, base[1] + 18)],
        (232, 138, 32), 0.95,
    )

    # ---- head: a large dark dragon head against the moon, gold rim ----
    # Upper jaw, lower jaw, open mouth, horns, frill, streaming whiskers.
    head_base, head_ang = cubic(*SPINE, 1.0)
    hx, hy = head_base
    # upper jaw: crown -> brow -> nose bridge -> hooked nose tip -> lip
    c.poly([(hx - 20, hy - 72), (hx + 28, hy - 94), (hx + 92, hy - 76),
            (hx + 112, hy - 58), (hx + 88, hy - 44), (hx + 40, hy - 38),
            (hx + 4, hy - 20)], DRAGON_DK)
    # lower jaw: hinge -> chin, hanging open below the upper jaw
    c.poly([(hx + 4, hy - 20), (hx + 52, hy - 28), (hx + 84, hy - 34),
            (hx + 58, hy - 10), (hx + 10, hy + 4), (hx - 16, hy - 8)],
           (35, 28, 70))
    # gold rim light along the nose bridge and crown
    c.stroke([(hx - 20, hy - 72), (hx + 28, hy - 94), (hx + 92, hy - 76),
              (hx + 112, hy - 58)], 4.0, GOLD_LT, 0.95)
    # horns: thick tapered curves sweeping back from the crown
    horn(c, (hx - 12, hy - 70), (hx - 66, hy - 128), (hx - 132, hy - 142),
         13, 3, GOLD)
    horn(c, (hx + 2, hy - 78), (hx - 42, hy - 138), (hx - 92, hy - 166),
         10, 2.5, GOLD_LT)
    # frill: three spikes behind the jaw
    for k, (ang, ln) in enumerate(((2.6, 34), (2.85, 42), (3.1, 30))):
        flame_tuft(c, (hx - 18, hy - 6), ang, ln, 8,
                   DRAGON_DK if k % 2 == 0 else (35, 28, 70), bend=0.25)
    # whiskers trailing back from the snout, streaming with the leap
    c.stroke([(hx + 100, hy - 52), (hx + 62, hy - 8), (hx + 12, hy + 16),
              (hx - 46, hy + 12)], 3.0, GOLD_LT, 0.9)
    c.stroke([(hx + 94, hy - 42), (hx + 64, hy + 2), (hx + 26, hy + 24)],
             2.5, GOLD, 0.85)
    # the eye: big and bright, almond with a vertical slit pupil
    ex, ey = hx + 40, hy - 60
    c.ellipse(ex, ey, 18, 11, EYE)
    c.ellipse(ex, ey, 6, 10, (26, 18, 6))
    c.disc(ex - 5, ey - 4, 3.2, (255, 255, 255), 0.95)
    # brow ridge over the eye
    c.stroke([(hx + 16, hy - 76), (hx + 40, hy - 78), (hx + 62, hy - 70)],
             3.5, GOLD_LT, 0.9)
    # mouth flame: a clear jet from the open jaw
    flame_tuft(c, (hx + 72, hy - 32), math.pi * 0.22, 52, 13, FLAME, bend=0.2)
    flame_tuft(c, (hx + 72, hy - 32), math.pi * 0.22, 32, 8, GOLD_LT, bend=0.2)
    flame_tuft(c, (hx + 70, hy - 26), math.pi * 0.30, 26, 7, GOLD_LT, bend=0.2)


def draw_splash(c):
    # where the spine crosses the waterline
    sx, sy = 200.0, WATERLINE
    # foam ring where the body breaks the surface
    c.arc_stroke(sx, sy, 74, 15, math.pi, 2 * math.pi, 6, FOAM, 0.95, steps=36)
    c.arc_stroke(sx, sy, 74, 15, 0, math.pi, 4, FOAM, 0.35, steps=36)
    # droplet crown: round-headed droplets fanning up from the crossing
    for i, (ang, ln, sz) in enumerate([
        (-2.75, 62, 13), (-2.35, 88, 16), (-1.95, 104, 19),
        (-1.57, 92, 15), (-1.18, 80, 16), (-0.75, 58, 12),
        (-0.35, 38, 10),
    ]):
        bx, by = sx + math.cos(ang) * 18, sy + math.sin(ang) * 10
        tipx, tipy = bx + math.cos(ang) * ln, by + math.sin(ang) * ln
        c.stroke([(bx, by), (tipx, tipy)], sz * 0.9,
                 FOAM if i % 2 == 0 else GOLD_LT, 0.95)
        c.disc(tipx, tipy, sz * 0.62, FOAM if i % 2 == 0 else GOLD_LT, 0.95)
    # spray arcs above the crown
    c.arc_stroke(sx - 30, sy - 66, 46, 30, math.pi * 1.15, math.pi * 1.85,
                 2.5, FOAM, 0.6, steps=24)
    c.arc_stroke(sx + 34, sy - 52, 36, 24, math.pi * 1.1, math.pi * 1.8,
                 2.0, FOAM, 0.5, steps=24)
    # expanding ripples on the water
    for rx, ry, a in [(98, 13, 0.75), (138, 19, 0.5), (182, 25, 0.32)]:
        c.arc_stroke(sx, sy, rx, ry, 0, math.pi, 3.0, (246, 220, 140), a,
                     steps=40)


def draw_sparks(c):
    # gold spark diamonds along the leap arc and near the head
    rnd = lcg(4242, 60)
    for i in range(14):
        t = 0.15 + rnd[i * 2] * 0.75
        pt, ang = cubic(*SPINE, t)
        hw = half_width(t)
        side = 1 if rnd[i * 2 + 1] > 0.5 else -1
        off = hw + 16 + rnd[(i * 3 + 1) % 60] * 46
        nx, ny = -math.sin(ang), math.cos(ang)
        x, y = pt[0] + nx * off * side, pt[1] + ny * off * side
        s = 3.5 + rnd[(i * 5 + 2) % 60] * 5.5
        c.poly([(x, y - s), (x + s * 0.36, y), (x, y + s),
                (x - s * 0.36, y)], GOLD_LT, 0.9)


# ---------------------------------------------------------------------------
# Post pass at output resolution: glows, vignette, downsample
# ---------------------------------------------------------------------------

def downsample(src, size=SIZE):
    """Box-average the 2x buffer down to size x size RGB bytes."""
    out = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            r = g = b = 0
            for dy in (0, 1):
                base = ((2 * y + dy) * W + 2 * x) * 3
                for dx in (0, 1):
                    o = base + dx * 3
                    r += src[o]
                    g += src[o + 1]
                    b += src[o + 2]
            o = (y * size + x) * 3
            out[o] = (r + 2) >> 2
            out[o + 1] = (g + 2) >> 2
            out[o + 2] = (b + 2) >> 2
    return out


def glow(rgb, size, cx, cy, radius, col, peak):
    """Additive radial glow, strongest at the centre."""
    x0 = max(0, int(cx - radius))
    x1 = min(size - 1, int(cx + radius))
    y0 = max(0, int(cy - radius))
    y1 = min(size - 1, int(cy + radius))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            d = math.hypot(x - cx, y - cy) / radius
            if d >= 1.0:
                continue
            a = peak * (1.0 - d) * (1.0 - d)
            o = (y * size + x) * 3
            rgb[o] = min(255, int(rgb[o] + col[0] * a))
            rgb[o + 1] = min(255, int(rgb[o + 1] + col[1] * a))
            rgb[o + 2] = min(255, int(rgb[o + 2] + col[2] * a))


def vignette(rgb, size, strength=0.16):
    cx = cy = size / 2.0
    maxd = math.hypot(cx, cy)
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / maxd
            if d <= 0.62:
                continue
            f = 1.0 - strength * ((d - 0.62) / 0.38) ** 2
            o = (y * size + x) * 3
            rgb[o] = int(rgb[o] * f)
            rgb[o + 1] = int(rgb[o + 1] * f)
            rgb[o + 2] = int(rgb[o + 2] * f)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render():
    c = Canvas()
    draw_sky(c)
    draw_moon(c)
    draw_water(c)
    draw_koi_dragon(c)
    draw_splash(c)
    draw_sparks(c)
    rgb = downsample(c.buf)
    # glow pass: moon halo, the dragon's eye, the mouth flame
    glow(rgb, SIZE, MOON_C[0], MOON_C[1], 345, (246, 196, 69), 0.38)
    hx, hy = cubic(*SPINE, 1.0)[0]
    glow(rgb, SIZE, hx + 40, hy - 60, 62, (255, 230, 150), 0.7)
    glow(rgb, SIZE, hx + 72, hy - 32, 44, (232, 120, 40), 0.45)
    vignette(rgb, SIZE)
    return bytes(rgb)


def main():
    out_path = os.environ.get("OUT", "/output/entry.png")
    png = encode_png(render(), SIZE, SIZE)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(png)


if __name__ == "__main__":
    main()
