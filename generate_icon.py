#!/usr/bin/env python3
"""Generate atmospheric iOS App Icon — lonely highway at dusk with radio tower."""

from PIL import Image, ImageDraw, ImageFont
import math, os, random

SIZE = 1024
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LaniakeaRadio", "LaniakeaRadio", "Assets.xcassets", "AppIcon.appiconset")
os.makedirs(ICON_PATH, exist_ok=True)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
pixels = img.load()
horizon_y = int(SIZE * 0.62)
vp_x, vp_y = SIZE // 2, int(horizon_y * 0.85)

# Sky gradient
for y in range(SIZE):
    for x in range(SIZE):
        t = y / SIZE
        if y <= horizon_y:
            r = int(35 + t * 170); g = int(12 + t * 70); b = int(55 + (1 - t) * 130)
        else:
            r = int(80 + (y - horizon_y) / (SIZE - horizon_y) * 15)
            g = int(35 + (y - horizon_y) / (SIZE - horizon_y) * 8)
            b = int(25)
        pixels[x, y] = (min(r, 255), min(g, 255), min(b, 255), 255)

# Sun glow
sun_x, sun_y = SIZE // 2, horizon_y + 25
for y in range(max(0, sun_y - 280), min(SIZE, sun_y + 180)):
    for x in range(max(0, sun_x - 380), min(SIZE, sun_x + 380)):
        dist = math.sqrt((x - sun_x)**2 + ((y - sun_y) * 2.5)**2)
        if dist < 320:
            a_f = max(0, 1 - dist/320) * 0.55
            r, g, b, a = pixels[x, y]
            pixels[x, y] = (int(r*(1-a_f)+248*a_f), int(g*(1-a_f)+170*a_f), int(b*(1-a_f)+70*a_f), a)

# Stars
random.seed(42)
for _ in range(65):
    sx, sy = random.randint(20, SIZE-20), random.randint(8, horizon_y-70)
    sr = random.randint(1, 3)
    br = random.randint(140, 235)
    for dy in range(-sr, sr+1):
        for dx in range(-sr, sr+1):
            if dx*dx + dy*dy <= sr*sr and 0 <= sx+dx < SIZE and 0 <= sy+dy < SIZE:
                r, g, b, a = pixels[sx+dx, sy+dy]
                pixels[sx+dx, sy+dy] = (min(255, r+br), min(255, g+br), min(255, b+br), a)

# Ground
for y in range(horizon_y, SIZE):
    for x in range(SIZE):
        t = (y - horizon_y) / (SIZE - horizon_y)
        pixels[x, y] = (int(22 + t*12), int(16 + t*8), int(18 + t*8), 255)

# Highway
for y in range(horizon_y - 25, SIZE):
    spread = (y - (horizon_y - 25)) * 0.75
    left = max(0, int(vp_x - 28 - spread))
    right = min(SIZE-1, int(vp_x + 28 + spread))
    for x in range(left, right+1):
        pixels[x, y] = (int(52 + (y-horizon_y)/(SIZE-horizon_y)*12), int(42 + (y-horizon_y)/(SIZE-horizon_y)*10), 38, 255)

# Dashed center line
for seg in range(18):
    seg_start = horizon_y + seg * 52
    seg_end = min(seg_start + 22, SIZE)
    seg_spread = max(2, int((seg_start - horizon_y) * 0.012))
    for y in range(seg_start, seg_end):
        if y < SIZE:
            for x in range(vp_x - seg_spread, vp_x + seg_spread + 1):
                if 0 <= x < SIZE:
                    r, g, b, a = pixels[x, y]
                    pixels[x, y] = (min(255, r+155), min(255, g+140), min(255, b+110), a)

# Radio tower silhouette
tx = vp_x + 130
t_top, t_base = horizon_y - 210, horizon_y + 15
for y in range(t_top, t_base+1):
    th = max(2, int((y - t_top) / (t_base - t_top) * 6))
    for x in range(tx - th, tx + th + 1):
        if 0 <= x < SIZE and 0 <= y < SIZE:
            pixels[x, y] = (14, 10, 16, 255)

# Cross beams
for i, by in enumerate([t_top + 55, t_top + 115, t_top + 155]):
    bw = 48 - i * 11
    for x in range(tx - bw, tx + bw + 1):
        for dy in range(-2, 3):
            if 0 <= by+dy < SIZE and 0 <= x < SIZE:
                pixels[x, by+dy] = (14, 10, 16, 255)

# Guy wires
for wy in [t_top + 65, t_top + 105]:
    for y in range(wy, t_base):
        prog = (y - wy) / (t_base - wy)
        sp = int(prog * 75)
        for x in [tx - sp, tx + sp]:
            if 0 <= x < SIZE and 0 <= y < SIZE:
                pixels[x, y] = (18, 14, 20, 180)

# Beacon light
for dy in range(-6, 7):
    for dx in range(-6, 7):
        if dx*dx + dy*dy <= 25:
            px, py = tx + dx, t_top + dy
            if 0 <= px < SIZE and 0 <= py < SIZE:
                pixels[px, py] = (225, 38, 28, 255)

# Beacon glow
for y in range(t_top - 28, t_top + 28):
    for x in range(tx - 28, tx + 28):
        dist = math.sqrt((x - tx)**2 + (y - t_top)**2)
        if 6 < dist < 28:
            alpha = max(0, 1 - dist/28) * 0.35
            r, g, b, a = pixels[x, y]
            pixels[x, y] = (int(r*(1-alpha)+225*alpha), int(g*(1-alpha)+30*alpha), int(b*(1-alpha)+20*alpha), a)

# Rounded mask (iOS icon)
mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE-1, SIZE-1], radius=120, fill=255)
img.putalpha(mask)

# Subtle text
draw = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
except Exception:
    font = ImageFont.load_default()
tag = "BULLSHIT FM"
bbox = draw.textbbox((0, 0), tag, font=font)
draw.text((vp_x - (bbox[2]-bbox[0])//2, horizon_y - 55), tag, fill=(255, 210, 160, 170), font=font)

# Save
output_path = os.path.join(ICON_PATH, "appicon-1024.png")
img.save(output_path, "PNG")
print(f"Saved: {output_path}")
