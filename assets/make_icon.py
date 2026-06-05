#!/usr/bin/env python3
"""
Generatore dell'icona di FormulaDeck.

Disegno: superellisse (squircle) in stile macOS Big Sur con gradiente blu del
brand e, al centro, il glifo integrale (U+222B) preso da Latin Modern Math —
il font matematico di LaTeX. L'icona "parla" lo stesso alfabeto dell'app.

Produce:
  - icon.png            master raster 1024x1024
  - icon.svg            master vettoriale (squircle + path reale del glifo)
  - icon.iconset/*.png  le 10 risoluzioni canoniche Apple (16..512 + @2x)
  - icon.icns           bundle completo (icp4..ic14), comprese le taglie piccole
"""
import os
import struct
import math
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

HERE = os.path.dirname(os.path.abspath(__file__))
LM_MATH = "/usr/share/texmf/fonts/opentype/public/lm-math/latinmodern-math.otf"
GLYPH_CP = 0x222B  # ∫

# Palette del brand
TOP = (59, 130, 246)     # #3B82F6
BOTTOM = (29, 78, 216)   # #1D4ED8
HILITE = (118, 169, 250) # tocco di luce in alto
WHITE = (255, 255, 255)

SS = 4  # supersampling


def squircle_mask(size, n=5.0, inset_ratio=0.0):
    """Maschera (alpha) di una superellisse |x|^n + |y|^n = 1 centrata."""
    m = Image.new("L", (size, size), 0)
    px = m.load()
    a = size / 2.0
    cx = cy = a
    inset = size * inset_ratio
    a_eff = a - inset
    for y in range(size):
        ny = (y + 0.5 - cy) / a_eff
        for x in range(size):
            nx = (x + 0.5 - cx) / a_eff
            v = abs(nx) ** n + abs(ny) ** n
            if v <= 1.0:
                px[x, y] = 255
            elif v <= 1.15:  # bordo morbido
                px[x, y] = int(255 * (1.0 - (v - 1.0) / 0.15))
    return m


def vertical_gradient(size, top, bottom):
    g = Image.new("RGB", (size, size))
    px = g.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        gg = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, gg, b)
    return g


def render_master(px=1024):
    S = px * SS
    # sfondo trasparente
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # corpo: gradiente mascherato dallo squircle
    grad = vertical_gradient(S, TOP, BOTTOM).convert("RGBA")
    mask = squircle_mask(S, n=5.0, inset_ratio=0.045)
    base.paste(grad, (0, 0), mask)

    # leggera luce radiale in alto (volume)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gr = int(S * 0.62)
    gx, gy = S // 2, int(S * 0.34)
    for i in range(gr, 0, -1):
        a = int(46 * (i / gr) ** 2)
        gd.ellipse([gx - i, gy - i, gx + i, gy + i],
                   fill=(HILITE[0], HILITE[1], HILITE[2], 255 - a if False else a))
    glow.putalpha(Image.composite(glow.split()[3], Image.new("L", (S, S), 0), mask))
    base = Image.alpha_composite(base, glow)

    # glifo integrale al centro
    font = ImageFont.truetype(LM_MATH, int(S * 0.74))
    ch = chr(GLYPH_CP)
    tmp = ImageDraw.Draw(base)
    bbox = tmp.textbbox((0, 0), ch, font=font)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (S - gw) / 2 - bbox[0]
    ty = (S - gh) / 2 - bbox[1]

    glyph_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gdl = ImageDraw.Draw(glyph_layer)
    # ombra sottile per stacco
    gdl.text((tx, ty + S * 0.006), ch, font=font, fill=(13, 42, 110, 90))
    gdl.text((tx, ty), ch, font=font, fill=WHITE + (255,))
    glyph_layer.putalpha(Image.composite(glyph_layer.split()[3],
                                         Image.new("L", (S, S), 0), mask))
    base = Image.alpha_composite(base, glyph_layer)

    return base.resize((px, px), Image.LANCZOS)


def build_svg(out, px=1024):
    """Master vettoriale: squircle + path reale del glifo integrale."""
    n = 5.0
    a = px / 2.0
    inset = px * 0.045
    a_eff = a - inset
    pts = []
    steps = 220
    for i in range(steps + 1):
        th = 2 * math.pi * i / steps
        ct, st = math.cos(th), math.sin(th)
        x = a + a_eff * math.copysign(abs(ct) ** (2.0 / n), ct)
        y = a + a_eff * math.copysign(abs(st) ** (2.0 / n), st)
        pts.append((x, y))
    sq = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"

    # path del glifo dalla font
    tt = TTFont(LM_MATH)
    upem = tt["head"].unitsPerEm
    cmap = tt.getBestCmap()
    gname = cmap[GLYPH_CP]
    gset = tt.getGlyphSet()
    pen = SVGPathPen(gset)
    gset[gname].draw(pen)
    glyph_path = pen.getCommands()
    g = gset[gname]
    adv = g.width
    # bounding box approssimato via glyf/charstring: uso scala su altezza em
    target_h = px * 0.74
    scale = target_h / upem
    gw = adv * scale
    # centramento orizzontale; verticale: baseline ~ 0.70*px
    tx = (px - gw) / 2.0
    baseline = px * 0.705
    transform = f"translate({tx:.2f},{baseline:.2f}) scale({scale:.5f},{-scale:.5f})"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" viewBox="0 0 {px} {px}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="rgb{TOP}"/>
      <stop offset="1" stop-color="rgb{BOTTOM}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.34" r="0.62">
      <stop offset="0" stop-color="rgb{HILITE}" stop-opacity="0.30"/>
      <stop offset="1" stop-color="rgb{HILITE}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <path d="{sq}" fill="url(#bg)"/>
  <path d="{sq}" fill="url(#glow)"/>
  <path d="{glyph_path}" transform="{transform}" fill="#ffffff"/>
</svg>
'''
    with open(out, "w") as f:
        f.write(svg)


def write_icns(iconset_dir, out):
    """Costruisce un .icns completo dai PNG dell'iconset."""
    # mappa: tipo icns -> (file png, lato px)
    mapping = [
        (b"icp4", "icon_16x16.png", 16),
        (b"icp5", "icon_32x32.png", 32),
        (b"ic07", "icon_128x128.png", 128),
        (b"ic08", "icon_256x256.png", 256),
        (b"ic09", "icon_512x512.png", 512),
        (b"ic10", "icon_512x512@2x.png", 1024),
        (b"ic11", "icon_16x16@2x.png", 32),
        (b"ic12", "icon_32x32@2x.png", 64),
        (b"ic13", "icon_128x128@2x.png", 256),
        (b"ic14", "icon_256x256@2x.png", 512),
    ]
    chunks = []
    for typ, fname, _ in mapping:
        with open(os.path.join(iconset_dir, fname), "rb") as f:
            data = f.read()
        chunks.append(typ + struct.pack(">I", len(data) + 8) + data)
    body = b"".join(chunks)
    total = len(body) + 8
    with open(out, "wb") as f:
        f.write(b"icns" + struct.pack(">I", total) + body)


def main():
    os.makedirs(os.path.join(HERE, "icon.iconset"), exist_ok=True)
    master = render_master(1024)
    master.save(os.path.join(HERE, "icon.png"))

    iconset = os.path.join(HERE, "icon.iconset")
    sizes = {
        "icon_16x16.png": 16, "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32, "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256, "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512, "icon_512x512@2x.png": 1024,
    }
    for fname, s in sizes.items():
        master.resize((s, s), Image.LANCZOS).save(os.path.join(iconset, fname))

    write_icns(iconset, os.path.join(HERE, "icon.icns"))
    build_svg(os.path.join(HERE, "icon.svg"), 1024)
    print("Icona generata: icon.png, icon.svg, icon.iconset/, icon.icns")


if __name__ == "__main__":
    main()
