"""Erzeugt die kachelbaren Texturen in model/textures (Pflaster, Granit, Dachziegel, Putz).
Aufruf: python make_textures.py [ausgabeordner]   (benoetigt numpy und Pillow)
"""
import os
import sys, numpy as np
from PIL import Image, ImageFilter
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'textures')
rng = np.random.default_rng(7)
N = 512

def smooth_noise(cells, n=N, seed=0):
    r = np.random.default_rng(seed).random((cells, cells))
    t = np.tile(r, (3, 3))
    im = Image.fromarray((t * 255).astype(np.uint8)).resize((3 * n, 3 * n), Image.BICUBIC)
    return np.asarray(im)[n:2 * n, n:2 * n].astype(np.float32) / 255

# --- cobblestones (voronoi setts, tileable) ---
G = 14
pts = (np.stack(np.meshgrid(np.arange(G), np.arange(G), indexing='ij'), -1) + 0.15 + 0.7 * rng.random((G, G, 2))) / G
cols = rng.random((G, G))
yy, xx = np.mgrid[0:N, 0:N] / N
F1 = np.full((N, N), 9.0); F2 = np.full((N, N), 9.0); ID = np.zeros((N, N))
for i in range(G):
    for j in range(G):
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                px, py = pts[i, j, 0] + di, pts[i, j, 1] + dj
                d = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
                m1 = d < F1
                F2 = np.where(m1, F1, np.minimum(F2, d))
                ID = np.where(m1, cols[i, j], ID)
                F1 = np.where(m1, d, F1)
edge = (F2 - F1) * G
stone = np.clip(edge / 0.35, 0, 1) ** 0.6
palette = np.array([[0.62, 0.58, 0.54], [0.70, 0.64, 0.57], [0.56, 0.55, 0.57], [0.66, 0.56, 0.50], [0.74, 0.70, 0.62], [0.52, 0.50, 0.50]])
base = palette[(ID * len(palette)).astype(int) % len(palette)]
n1 = smooth_noise(40, seed=1)[..., None]
base = base * (0.88 + 0.2 * n1)
joint = np.array([0.33, 0.30, 0.26])
moss = np.array([0.45, 0.52, 0.25])
mossmask = (smooth_noise(10, seed=2) > 0.68)[..., None]
jc = np.where(mossmask, moss, joint)
img = base * (0.75 + 0.25 * stone[..., None]) * (stone[..., None] > 0.05) + jc * (stone[..., None] <= 0.05)
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.SMOOTH).save(out + "/cobble.png")

# --- granite slabs (basin rim / paving), tileable, light neutral ---
g = 0.80 + 0.08 * smooth_noise(64, seed=3) + 0.05 * (rng.random((N, N)) - 0.5)
gimg = np.stack([g, g * 0.98, g * 0.95], -1)
gimg[:, :3] *= 0.7; gimg[:3, :] *= 0.7  # slab joints
Image.fromarray((np.clip(gimg, 0, 1) * 255).astype(np.uint8)).save(out + "/granite.png")

# --- roof tiles (neutral, tinted by material factor) ---
R, C = 8, 6
img = np.zeros((N, N))
th, tw = N // R, N // C
for r in range(R):
    off = (tw // 2) * (r % 2)
    for c in range(C + 1):
        b = 0.82 + 0.18 * rng.random()
        x0 = c * tw - off
        for y in range(th):
            v = b * (0.62 + 0.38 * (y / th) ** 0.7)  # overlap shadow on top
            row = r * th + y
            xs = np.arange(x0, x0 + tw) % N
            u = (np.arange(tw) - tw / 2) / (tw / 2)
            rounding = 1 - 0.25 * u ** 2
            edge = np.where(np.abs(u) > 0.92, 0.7, 1.0)
            img[row, xs] = v * rounding * edge
        img[r * th + th - 2:r * th + th, :] *= 0.6
img = img * (0.92 + 0.1 * smooth_noise(20, seed=4))
img = np.clip(img, 0, 1)
Image.fromarray((np.stack([img] * 3, -1) * 255).astype(np.uint8)).save(out + "/roof_tiles.png")

# --- plaster (subtle painterly noise, near white) ---
p = 0.90 + 0.07 * smooth_noise(12, seed=5) + 0.04 * smooth_noise(48, seed=6)
Image.fromarray((np.clip(np.stack([p] * 3, -1), 0, 1) * 255).astype(np.uint8)).save(out + "/plaster.png")
print("ok")
