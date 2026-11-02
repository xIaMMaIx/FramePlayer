"""
Builds the final F-Play icon kit from one geometry definition.

The F's top bar and stem are a picture-frame corner; its middle arm is a play triangle.
Run: python build_fplay.py   (writes SVGs into final/)
"""
import math
from pathlib import Path

OUT = Path(__file__).parent / "final"
INK = "#0D0E12"   # app background, also the dark ink
WHITE = "#FFFFFF"
RED = "#FF0033"   # app accent


def rounded_polygon(points, radii):
    """Polygon whose corners are rounded by quadratic curves; radius 0 keeps a corner sharp."""
    out = []
    for i, (p1, r) in enumerate(zip(points, radii)):
        p0, p2 = points[i - 1], points[(i + 1) % len(points)]

        def toward(a, b, d):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            return a[0] + dx / length * d, a[1] + dy / length * d

        cmd = "M" if i == 0 else "L"
        if r == 0:
            out.append(f"{cmd}{p1[0]:.2f} {p1[1]:.2f}")
            continue
        a, b = toward(p1, p0, r), toward(p1, p2, r)
        out.append(f"{cmd}{a[0]:.2f} {a[1]:.2f} Q{p1[0]:.2f} {p1[1]:.2f} {b[0]:.2f} {b[1]:.2f}")
    return " ".join(out) + " Z"


def f_play(stem=40, gap_scale=1.0):
    """Returns (frame_path, play_path) on a 256 grid, centred optically."""
    x0, top, bottom = 70, 40, 216
    x1 = x0 + stem
    frame = (f"M{x0} {bottom} V{top + 44} A44 44 0 0 1 {x0 + 44} {top} H186 "
             f"A20 20 0 0 1 186 {top + 40} H{x1} V{bottom} A{stem / 2} {stem / 2} 0 0 1 {x0} {bottom} Z")
    # The base sits flush on the stem's right edge (sharp corners there, so a second colour
    # meets the stem in a clean line); only the tip is rounded and lines up with the top bar's end.
    tip, mid = 200, 141
    half = 46 * gap_scale * (tip - x1) / (tip - (x0 + 24))  # same slope as the original triangle
    play = rounded_polygon([(x1, mid - half), (tip, mid), (x1, mid + half)], [0, 12, 0])
    return frame, play


def write(name, body, viewbox="0 0 256 256", bg=None):
    rect = f'<rect width="100%" height="100%" fill="{bg}"/>' if bg else ""
    (OUT / name).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}"><title>Frame Player</title>{rect}{body}</svg>\n',
        encoding="utf-8",
    )


def mark(frame_fill, play_fill, frame, play, transform):
    return (f'<g transform="{transform}"><path fill="{frame_fill}" d="{frame}"/>'
            f'<path fill="{play_fill}" d="{play}"/></g>')


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    frame, play = f_play()
    centre = "translate(-8 -12)"  # bbox 70..206 x 40..236: centred, lifted ~2 px and nudged right for the heavy stem

    write("fplay-black.svg", mark(INK, INK, frame, play, centre))
    write("fplay-white.svg", mark(WHITE, WHITE, frame, play, centre))
    write("fplay-color-on-dark.svg", mark(WHITE, RED, frame, play, centre), bg=INK)
    write("fplay-color-on-light.svg", mark(INK, RED, frame, play, centre), bg=WHITE)

    # Small-size cut (32 px and below): wider gap above the play arm, bigger triangle
    s_frame, s_play = f_play(stem=44, gap_scale=0.9)
    write("fplay-small.svg", mark(WHITE, RED, s_frame, s_play, centre), bg=INK)

    # Android adaptive-icon foreground: transparent 1024 canvas, mark inside the 66/108 safe circle.
    # Mark bbox is 136 x 196 (diagonal ~239); scale 2.45 keeps it within a 600 px circle.
    scale = 2.45
    fg = f"translate(512 512) scale({scale}) translate(-134 -140)"
    write("android-foreground.svg", mark(WHITE, RED, frame, play, fg), viewbox="0 0 1024 1024")
    print("wrote", sorted(p.name for p in OUT.glob("*.svg")))
