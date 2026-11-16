#!/usr/bin/env python3
"""Make the AI judge excited — ai-excited-01.

A program that draws ONE image, deterministically, with the Python standard
library only (no network, no randomness, no clock), and writes it to
/output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png).

The image: a golden koi leaps out of dark water and becomes a dragon
mid-leap, its head a dark silhouette backlit by a huge gold moon, one glowing
slit-pupil eye. One big arcing body, one huge moon disc: the idea reads at
300px. The twist is the transformation itself (fish -> dragon, lit body ->
shadow head), the momentum is the leap, and the style is clean flat vector
with a dark outline — no anatomy to break, no text at all.

Determinism: fixed constants only; the PNG encoder writes no timestamp
chunk; running twice produces identical bytes.

R8 (recorded polish pass, 2026-11-16): scale rows + dorsal fin along the
body, layered mane flames, bigger eye / jaw rim-light / attached mouth
flame, bigger forked tail fin with a splash crown, fewer spray droplets
in a clean arc, thicker motion streaks, softer moon halo (no disc edge),
shooting star + more stars in the empty left sky.
"""
import os
import struct
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, r, g, b):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = r
            self.px[i + 1] = g
            self.px[i + 2] = b

    def blend(self, x, y, r, g, b, a):
        """Blend colour over pixel with alpha a (0..255)."""
        if 0 <= x < self.w and 0 <= y < self.h and a > 0:
            i = (y * self.w + x) * 3
            ia = 255 - a
            self.px[i] = (r * a + self.px[i] * ia) // 255
            self.px[i + 1] = (g * a + self.px[i + 1] * ia) // 255
            self.px[i + 2] = (b * a + self.px[i + 2] * ia) // 255

    def disc(self, cx, cy, rad, color, alpha=255):
        r0, g0, b0 = color
        x0 = max(0, int(cx - rad))
        x1 = min(self.w - 1, int(cx + rad) + 1)
        y0 = max(0, int(cy - rad))
        y1 = min(self.h - 1, int(cy + rad) + 1)
        r2 = rad * rad
        for y in range(y0, y1 + 1):
            dy = y - cy
            for x in range(x0, x1 + 1):
                dx = x - cx
                if dx * dx + dy * dy <= r2:
                    if alpha == 255:
                        self.set(x, y, r0, g0, b0)
                    else:
                        self.blend(x, y, r0, g0, b0, alpha)

    def radial(self, cx, cy, rad, inner, outer):
        """Radial gradient disc: inner colour at centre -> outer at edge."""
        x0 = max(0, int(cx - rad))
        x1 = min(self.w - 1, int(cx + rad) + 1)
        y0 = max(0, int(cy - rad))
        y1 = min(self.h - 1, int(cy + rad) + 1)
        for y in range(y0, y1 + 1):
            dy = (y - cy) / rad
            for x in range(x0, x1 + 1):
                dx = (x - cx) / rad
                d = (dx * dx + dy * dy) ** 0.5
                if d <= 1.0:
                    t = d
                    r = int(inner[0] + (outer[0] - inner[0]) * t)
                    g = int(inner[1] + (outer[1] - inner[1]) * t)
                    b = int(inner[2] + (outer[2] - inner[2]) * t)
                    self.set(x, y, r, g, b)

    def vgrad(self, y0, y1, top, bottom):
        for y in range(y0, y1):
            t = (y - y0) / max(1, y1 - y0 - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            base = (y * self.w) * 3
            for x in range(self.w):
                i = base + x * 3
                self.px[i] = r
                self.px[i + 1] = g
                self.px[i + 2] = b

    def poly(self, pts, color, alpha=255):
        """Scanline polygon fill."""
        if len(pts) < 3:
            return
        r0, g0, b0 = color
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(self.h - 1, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    t = (y - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa = max(0, int(xs[k]))
                xb = min(self.w - 1, int(xs[k + 1]) + 1)
                for x in range(xa, xb + 1):
                    if alpha == 255:
                        self.set(x, y, r0, g0, b0)
                    else:
                        self.blend(x, y, r0, g0, b0, alpha)

    def thick_line(self, x0, y0, x1, y1, width, color, alpha=255):
        """Line drawn as a chain of discs (round caps)."""
        import math
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(dist / max(1.0, width * 0.45)))
        for i in range(steps + 1):
            t = i / steps
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t,
                      width / 2.0, color, alpha)

    def quad(self, x0, y0, cx, cy, x1, y1, width, color, alpha=255):
        """Quadratic bezier as thick line segments."""
        import math
        steps = 24
        px, py = x0, y0
        for i in range(1, steps + 1):
            t = i / steps
            mt = 1 - t
            x = mt * mt * x0 + 2 * mt * t * cx + t * t * x1
            y = mt * mt * y0 + 2 * mt * t * cy + t * t * y1
            self.thick_line(px, py, x, y, width, color, alpha)
            px, py = x, y


def catmull_rom(points, samples):
    """Sample a Catmull-Rom spline through points; returns list of (x, y)."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        for j in range(samples):
            t = j / samples
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


# ------------------------------------------------------------------ scene
def lerp(a, b, t):
    return a + (b - a) * t


def draw_scene():
    cv = Canvas(W, H)
    # --- sky: deep indigo -> violet horizon, water below (soft blend)
    cv.vgrad(0, 700, (10, 14, 46), (26, 48, 92))
    cv.vgrad(700, H, (26, 48, 92), (5, 30, 46))

    # --- stars (fixed positions, deterministic)
    stars = [(60, 80, 2), (180, 50, 1), (320, 110, 2), (430, 60, 1), (540, 90, 2),
             (880, 70, 2), (960, 150, 1), (120, 200, 1), (250, 260, 1), (40, 320, 2),
             (920, 260, 2), (980, 380, 1), (80, 430, 1), (350, 180, 1), (640, 60, 1),
             (760, 120, 1), (500, 200, 1), (200, 380, 2), (60, 540, 1), (940, 480, 2)]
    for (x, y, r) in stars:
        cv.disc(x, y, r, (255, 244, 214), 200)
    # a few more stars in the empty left half, plus one shooting star for
    # energy in the dark sky (R7: ~40% of the frame was empty darkness)
    for (x, y, r) in [(150, 120, 2), (90, 260, 1), (300, 320, 2), (420, 140, 1),
                      (60, 640, 2), (880, 420, 1), (960, 560, 2), (480, 120, 1)]:
        cv.disc(x, y, r, (255, 244, 214), 200)
    cv.thick_line(120, 100, 210, 165, 4, (255, 244, 214), 200)
    cv.thick_line(210, 165, 235, 183, 2, (255, 244, 214), 120)
    cv.disc(118, 98, 4, (255, 255, 255), 230)

    # --- gold moon, upper right: halo fades into the local sky colour.
    # Outer colour matches the sky gradient at this height (~16,26,63) so
    # the halo has no visible disc edge (R7 flaw); a second, wider, fainter
    # ring softens it further.
    cv.radial(650, 250, 380, (34, 44, 86), (13, 21, 56))
    cv.radial(650, 250, 290, (255, 200, 90), (16, 26, 63))
    cv.radial(650, 250, 150, (255, 233, 168), (245, 158, 44))
    for (x, y, r) in [(605, 210, 13), (695, 285, 10), (650, 300, 8)]:
        cv.disc(x, y, r, (232, 148, 40), 80)

    # --- moon reflection: three small gold dashes on the water, nothing more
    for (x, y, w, a) in [(610, 900, 80, 200), (625, 930, 55, 220), (600, 960, 100, 180)]:
        cv.poly([(x, y), (x + w, y), (x + w - 10, y + 5), (x + 10, y + 5)],
                (255, 201, 94), a)

    # --- body spline: a real leap arc — steep rise from the water, flattening
    # into the head at the apex. Tail (in water, bottom-left) -> head (top-right).
    spine = [(170, 905), (205, 800), (280, 680), (390, 565), (520, 465),
             (645, 375), (740, 305), (795, 265)]
    pts = catmull_rom(spine, 14)

    def radius_at(t):
        if t < 0.45:
            return lerp(22, 80, t / 0.45)
        return lerp(80, 48, (t - 0.45) / 0.55)

    def color_at(t):
        if t < 0.30:
            u = t / 0.30
            return (255, int(lerp(107, 160, u)), int(lerp(26, 60, u)))
        u = (t - 0.30) / 0.70
        return (255, int(lerp(160, 181, u)), int(lerp(60, 46, u)))

    n = len(pts)
    # --- dark outline pass: slightly larger discs first, so the creature pops
    # off the moon and sky like a clean sticker (flat-vector style).
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        cv.disc(x - 3, y - 4, radius_at(t) + 6, (16, 20, 50))
    # --- tail fin: two flowing lobes (curved, not angular), bigger and
    # clearly forked (R7: small lobes lost in the spray clutter)
    cv.quad(170, 905, 90, 850, 45, 875, 28, (255, 122, 31))
    cv.quad(170, 905, 95, 888, 50, 908, 18, (255, 244, 224))
    cv.quad(170, 905, 100, 965, 60, 990, 28, (255, 122, 31))
    cv.quad(170, 905, 110, 955, 75, 985, 16, (255, 244, 224))
    # splash crown where the tail leaves the water: three white arcs
    for (sx, sy, ex, ey) in [(130, 905, 165, 880), (150, 920, 190, 900),
                             (120, 930, 160, 915)]:
        cv.quad(sx, sy, (sx + ex) // 2, min(sy, ey) - 12, ex, ey, 5,
                (255, 255, 255), 200)
    # --- body: overlapping discs along the spline
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        cv.disc(x, y, radius_at(t), color_at(t))
    # belly: soft pale wash on the lower side (subtle, not a cream stripe)
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        if 0.2 < t < 0.8:
            cv.disc(x - radius_at(t) * 0.15, y + radius_at(t) * 0.45,
                    radius_at(t) * 0.30, (255, 233, 168), 25)
    # koi patches on the tail third: white blotches + black spots
    for (x, y, r, c, a) in [(235, 830, 30, (255, 244, 224), 215),
                            (305, 725, 24, (255, 244, 224), 195),
                            (275, 775, 12, (26, 22, 46), 235),
                            (345, 685, 10, (26, 22, 46), 235),
                            (215, 865, 9, (26, 22, 46), 210),
                            (255, 860, 8, (26, 22, 46), 210)]:
        cv.disc(x, y, r, c, a)
    # scale rows along the whole gold body (R7: the body was a smooth tube).
    # Scallop arcs follow the spine; a second, offset row lower down gives
    # real koi texture without any anatomy to break.
    for i in range(8, n - 6, 7):
        x, y = pts[i]
        t = i / (n - 1)
        r = radius_at(t)
        cv.quad(x - r * 0.55, y - r * 0.1, x, y + r * 0.5, x + r * 0.55, y - r * 0.1,
                5, (200, 110, 10), 130)
    for i in range(12, n - 6, 7):
        x, y = pts[i]
        t = i / (n - 1)
        r = radius_at(t)
        cv.quad(x - r * 0.45, y + r * 0.15, x, y + r * 0.65, x + r * 0.45, y + r * 0.15,
                4, (214, 130, 20), 110)
    # dorsal fin: small flame tufts along the upper edge of the spine, tips
    # sweeping back. The spine runs up-right, so the upper-left normal is
    # about (-0.62, -0.78); fins grow out along it.
    for i in range(10, 62, 9):
        x, y = pts[i]
        t = i / (n - 1)
        r = radius_at(t)
        bx, by = x - 0.62 * r * 0.75, y - 0.78 * r * 0.75
        tipx, tipy = x - 0.62 * r * 1.55, y - 0.78 * r * 1.55
        cv.poly([(bx - r * 0.30, by + r * 0.18), (tipx, tipy),
                 (bx + r * 0.30, by + r * 0.10)], (200, 110, 10))
        cv.poly([(bx - r * 0.18, by + r * 0.12), (tipx + r * 0.06, tipy + r * 0.08),
                 (bx + r * 0.18, by + r * 0.06)], (255, 181, 50))

    # --- mane: three big flame tufts on the neck, sweeping back.
    # Layered now (R7: flat paper triangles) — dark outline, gold body,
    # pale inner flame — so each tuft reads as a flame, not a cutout.
    for (bx, by, tipx, tipy, wdt) in [(655, 395, 600, 300, 46),
                                      (700, 350, 660, 255, 52),
                                      (745, 315, 720, 225, 44)]:
        cv.poly([(bx - wdt // 2 - 6, by + 26), (tipx - 4, tipy - 6),
                 (bx + wdt // 2 + 6, by + 20)], (200, 110, 10))
        cv.poly([(bx - wdt // 2, by + 20), (tipx, tipy),
                 (bx + wdt // 2, by + 14)], (232, 138, 20))
        cv.poly([(bx - wdt // 4, by + 12), (tipx + 8, tipy + 12),
                 (bx + wdt // 4, by + 8)], (255, 201, 60))
        cv.poly([(bx - wdt // 8, by + 6), (tipx + 12, tipy + 22),
                 (bx + wdt // 8, by + 4)], (255, 233, 168))

    # --- head: a dark silhouette BACKLIT by the moon (inside the moon disc).
    # One clean profile polygon with an open-mouth notch; a glowing eye and a
    # gold rim-light are the only details — nothing anatomical to break.
    hx, hy = 720, 290
    cv.poly([(660, 335), (680, 260), (700, 232), (625, 150), (690, 195),
             (745, 218), (800, 205), (852, 225), (862, 242), (848, 258),
             (795, 264), (845, 286), (830, 302), (775, 312), (720, 335)],
            (18, 16, 44))
    # second horn silhouette behind the first
    cv.poly([(700, 225), (655, 140), (700, 195), (725, 215)], (18, 16, 44))
    # gold rim-light along the top edge of the silhouette
    cv.thick_line(680, 258, 700, 232, 5, (255, 201, 60), 220)
    cv.thick_line(700, 232, 745, 218, 5, (255, 201, 60), 220)
    cv.thick_line(745, 218, 800, 205, 5, (255, 201, 60), 220)
    # glowing dragon eye: bigger and brighter (R7: small and easy to miss)
    cv.disc(762, 248, 16, (255, 201, 60))
    cv.disc(762, 248, 10, (255, 233, 168))
    cv.poly([(762, 238), (767, 248), (762, 258), (757, 248)], (20, 16, 40))
    cv.disc(766, 244, 3, (255, 255, 255), 230)
    # nostril dot on the snout + gold rim-light along the lower jaw, so the
    # silhouette reads as a head, not a bird/shark blob
    cv.disc(842, 238, 4, (255, 201, 60), 220)
    cv.thick_line(720, 335, 775, 312, 5, (255, 201, 60), 200)
    cv.thick_line(775, 312, 830, 302, 5, (255, 201, 60), 200)
    # fire inside the open mouth: a teardrop polygon that touches the mouth
    # edges on both sides (R7: two floating discs, detached from the snout)
    cv.poly([(812, 260), (838, 256), (846, 272), (828, 286), (812, 278)],
            (255, 170, 30))
    cv.poly([(820, 264), (836, 262), (840, 272), (828, 280)], (255, 233, 168))
    # whiskers trailing back from the snout
    cv.quad(830, 268, 780, 320, 720, 335, 5, (255, 233, 168))
    cv.quad(825, 278, 775, 335, 715, 350, 4, (255, 201, 60))

    # --- spray: fewer, larger droplets in a clear rising arc (R7: twelve
    # random dots + a stray cyan streak read as clutter, not spray)
    spray = [(150, 885, 8), (120, 850, 6), (200, 860, 7), (230, 820, 6),
             (265, 780, 7), (300, 730, 5), (335, 670, 5), (115, 940, 7)]
    for (x, y, r) in spray:
        cv.disc(x, y, r, (255, 255, 255), 210)
        cv.disc(x, y, max(1, r - 2), (255, 233, 168), 220)
    # motion streaks behind the leap: thicker and brighter (R7: thin/faint)
    for (x0, y0, x1, y1, w) in [(310, 790, 390, 715, 10), (430, 700, 505, 630, 9),
                                (520, 580, 590, 515, 9), (250, 840, 320, 775, 8)]:
        cv.thick_line(x0, y0, x1, y1, w, (255, 201, 60), 200)
    return cv


# ------------------------------------------------------------------- png
def chunk(typ, data):
    c = struct.pack(">I", len(data)) + typ + data
    c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return c


def write_png(cv, path):
    raw = bytearray()
    w = cv.w
    for y in range(cv.h):
        raw.append(0)  # filter: None
        base = y * w * 3
        raw += cv.px[base:base + w * 3]
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", w, cv.h, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    cv = draw_scene()
    n = write_png(cv, os.path.join(out_dir, "entry.png"))
    print(f"wrote entry.png ({n} bytes, {W}x{H})")


if __name__ == "__main__":
    main()
