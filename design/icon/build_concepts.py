"""Builds the three icon concepts as black-on-transparent 256x256 SVGs."""
import math

def rounded_polygon(points, r):
    """Path for a polygon with each corner rounded by a quadratic curve of reach r."""
    n = len(points); out = []
    for i in range(n):
        p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
        def toward(a, b, d):
            dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy); return (a[0] + dx / L * d, a[1] + dy / L * d)
        a = toward(p1, p0, r); b = toward(p1, p2, r)
        out.append(("M" if i == 0 else "L") + f"{a[0]:.2f} {a[1]:.2f} Q{p1[0]:.2f} {p1[1]:.2f} {b[0]:.2f} {b[1]:.2f}")
    return " ".join(out) + " Z"

def rrect(x, y, w, h, r):
    return (f"M{x+r} {y} H{x+w-r} A{r} {r} 0 0 1 {x+w} {y+r} V{y+h-r} A{r} {r} 0 0 1 {x+w-r} {y+h} "
            f"H{x+r} A{r} {r} 0 0 1 {x} {y+h-r} V{y+r} A{r} {r} 0 0 1 {x+r} {y} Z")

def circle(cx, cy, r):
    return f"M{cx+r} {cy} A{r} {r} 0 1 0 {cx-r} {cy} A{r} {r} 0 1 0 {cx+r} {cy} Z"

def svg(name, d, extra="", shift=(0, 0)):
    g = f'<g transform="translate({shift[0]} {shift[1]})">' if shift != (0, 0) else "<g>"
    open(name, "w", encoding="utf-8").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><title>{name[:-4]}</title>'
        f'{g}<path fill="#000" fill-rule="evenodd" d="{d}"/>{extra}</g></svg>\n')

# A - Crossfade: a photo (square) and a record (circle) overlap; the overlap is cut out.
svg("a-crossfade.svg", rrect(34, 34, 128, 128, 30) + " " + circle(158, 158, 64))

# B - Sound Horizon: level bars form a hill skyline under a sun.
bars = []
heights = [60, 96, 128, 100, 64]
for i, h in enumerate(heights):
    x = 44 + i * 36
    bars.append(rrect(x, 216 - h, 24, h, 12))
svg("b-horizon.svg", " ".join(bars) + " " + circle(184, 70, 28))

# C - F-Play: an F whose top bar + stem are a frame corner and whose middle arm is a play triangle.
stem_top = "M70 216 V84 A44 44 0 0 1 114 40 H186 A20 20 0 0 1 186 80 H110 V216 A20 20 0 0 1 70 216 Z"
# Left corners sit inside the stem, so only the pointing part shows (separate path: no evenodd hole)
play = rounded_polygon([(94, 100), (180, 141), (94, 182)], 12)
# Bounding box 70..206 x 40..236: centre it, then lift ~2 px for the optical centre
svg("c-fplay.svg", stem_top, f'<path fill="#000" d="{play}"/>', shift=(-10, -12))
print("built")
