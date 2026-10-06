"""Shaded-relief terrain tiles for the zoomable maps.

Source: AWS Terrain Tiles (Terrarium encoding, open data, zoom 6) — elevation and ocean depth.
Output: tiles/{z}/{x}/{y}.jpg — Web Mercator, 1024 px tiles, z0..z4 (341 files, the
          equivalent of standard zoom 2..6), plus data/us-terrain.jpg for the US county map.

    python3 build_terrain.py SRC_DIR [SRC7_DIR] [--fetch]
      SRC_DIR holds the zoom-6 elevation tiles as {x}_{y}.png (~4096 files with --fetch).
      SRC7_DIR (optional) holds zoom-7 tiles for the extra-detail regions in DETAIL and adds
      tiles/5/ (Europe, Southeast Asia, Africa at ~1.2 km/px).
Needs numpy and Pillow.
"""
import math, sys, os, urllib.request, concurrent.futures as cf
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).parent
OUT = ROOT / "tiles"
N6 = 64  # zoom-6 tiles per side


def fetch(src):
    src.mkdir(parents=True, exist_ok=True)

    def get(xy):
        x, y = xy
        p = src / f"{x}_{y}.png"
        if p.exists() and p.stat().st_size > 100:
            return
        p.write_bytes(urllib.request.urlopen(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/6/{x}/{y}.png", timeout=30).read())
    with cf.ThreadPoolExecutor(32) as ex:
        list(ex.map(get, [(x, y) for x in range(N6) for y in range(N6)]))


def elev_tile(src, x, y):
    x %= N6
    if y < 0 or y >= N6:
        return np.full((256, 256), -4000, np.float32)
    a = np.asarray(Image.open(src / f"{x}_{y}.png").convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


# hypsometric tints: muted so a risk overlay still reads on top
LAND = [(-1, (176, 196, 160)), (0, (168, 192, 150)), (200, (186, 202, 158)), (600, (210, 208, 168)), (1200, (214, 196, 160)),
        (2000, (196, 174, 146)), (3000, (182, 166, 152)), (4200, (214, 210, 206)), (6000, (246, 246, 246))]
SEA = [(-6000, (150, 182, 200)), (-2000, (170, 198, 212)), (-200, (192, 214, 222)), (0, (206, 224, 228))]


def ramp(e, stops):
    xs = np.array([s[0] for s in stops], np.float32)
    out = np.zeros(e.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(e, xs, np.array([s[1][c] for s in stops], np.float32))
    return out


def render(e, lat_top, lat_bot, z_px_m, mercator=True):
    """e: elevation with a 1px border. z_px_m: ground meters per pixel at the equator."""
    h = e.shape[0] - 2
    lats = np.linspace(lat_top, lat_bot, h + 2)[:, None]
    px = z_px_m * np.cos(np.radians(lats)) if mercator else np.full_like(lats, z_px_m)
    land = np.maximum(e, 0)
    dzdx = (land[1:-1, 2:] - land[1:-1, :-2]) / (2 * px[1:-1])
    dzdy = (land[2:, 1:-1] - land[:-2, 1:-1]) / (2 * px[1:-1])
    ex = 2.2  # vertical exaggeration so hills read at continental scale
    slope = np.arctan(ex * np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    az, alt = math.radians(315), math.radians(45)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip(hs, 0, 1)
    c = e[1:-1, 1:-1]
    col = np.where((c > 0)[..., None], ramp(c, LAND), ramp(c, SEA))
    shade = np.where(c > 0, 0.50 + 0.62 * hs, 0.92 + 0.08 * hs)[..., None]
    return np.clip(col * shade, 0, 255).astype(np.uint8)


def tile_lat(y, n):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def build(src):
    z_out = 4  # 16x16 tiles of 1024 px == 64x64 zoom-6 source tiles
    m_per_px = 40075016.686 / (256 * N6)
    (OUT / str(z_out)).mkdir(parents=True, exist_ok=True)
    for tx in range(16):
        (OUT / str(z_out) / str(tx)).mkdir(exist_ok=True)
        for ty in range(16):
            p = OUT / str(z_out) / str(tx) / f"{ty}.jpg"
            if p.exists():
                continue
            # 6x6 source mosaic around the 4x4 block, then crop a 1px border
            mos = np.vstack([np.hstack([elev_tile(src, tx * 4 + i, ty * 4 + j) for i in range(-1, 5)]) for j in range(-1, 5)])
            e = mos[255:255 + 1026, 255:255 + 1026]
            n = 16 * 1024
            lat_top = tile_lat(ty * 1024 - 1, n)
            lat_bot = tile_lat(ty * 1024 + 1024 + 1, n)
            Image.fromarray(render(e, lat_top, lat_bot, m_per_px)).save(p, quality=74, optimize=True, progressive=True)
        print("z4 column", tx, flush=True)
    for z in range(z_out - 1, -1, -1):
        for tx in range(2 ** z):
            (OUT / str(z) / str(tx)).mkdir(parents=True, exist_ok=True)
            for ty in range(2 ** z):
                big = Image.new("RGB", (2048, 2048))
                for i in range(2):
                    for j in range(2):
                        big.paste(Image.open(OUT / str(z + 1) / str(tx * 2 + i) / f"{ty * 2 + j}.jpg"), (i * 1024, j * 1024))
                big.resize((1024, 1024), Image.LANCZOS).save(OUT / str(z) / str(tx) / f"{ty}.jpg", quality=76, optimize=True, progressive=True)
    print("tiles done")


def us_terrain(src, w=2925, h=1830):
    """Terrain under the US county map, reprojected to d3.geoAlbersUsa's lower-48 Albers (scale 1300 * 3)."""
    k = 1300 * w / 975
    tx, ty = w / 2, h / 2
    phi1, phi2 = math.radians(29.5), math.radians(45.5)
    nn = (math.sin(phi1) + math.sin(phi2)) / 2
    C = math.cos(phi1) ** 2 + 2 * nn * math.sin(phi1)
    r0 = math.sqrt(C) / nn
    # d3: geoAlbers rotate [96,0], center [-0.6,38.7]; translate (scaled) offsets the projected center
    def fwd(lam, phi):
        r = math.sqrt(C - 2 * nn * math.sin(phi)) / nn
        return r * math.sin(nn * lam), r0 - r * math.cos(nn * lam)
    cx, cy = fwd(math.radians(-0.6), math.radians(38.7))
    X, Y = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    x = (X - tx) / k + cx
    y = -((Y - ty) / k) + cy
    r0y = r0 - y
    rho = np.sign(nn) * np.hypot(x, r0y)
    lam = np.arctan2(x, r0y) / nn
    phi = np.arcsin(np.clip((C - (rho * nn) ** 2) / (2 * nn), -1, 1))
    lon = np.degrees(lam) - 96
    lat = np.degrees(phi)
    # sample elevation from the zoom-6 mosaic covering the lower 48
    n = 256 * N6
    gx = (lon + 180) / 360 * n
    gy = (1 - np.log(np.tan(np.radians(lat)) + 1 / np.cos(np.radians(lat))) / math.pi) / 2 * n
    x0, x1 = int(gx.min()) // 256 - 1, int(gx.max()) // 256 + 2
    y0, y1 = int(gy.min()) // 256 - 1, int(gy.max()) // 256 + 2
    mos = np.vstack([np.hstack([elev_tile(src, i, j) for i in range(x0, x1)]) for j in range(y0, y1)])
    ix = np.clip((gx - x0 * 256).astype(int), 1, mos.shape[1] - 2)
    iy = np.clip((gy - y0 * 256).astype(int), 1, mos.shape[0] - 2)
    e = np.pad(mos[iy, ix], 1, mode="edge")
    m_per_px = 1 / k * 6371000  # Albers is equal-area; near-constant ground scale
    img = render(e, 50, 24, m_per_px, mercator=False)
    Image.fromarray(img).save(ROOT / "data" / "us-terrain.jpg", quality=72, optimize=True, progressive=True)
    print("us-terrain.jpg", img.shape)


# Extra-detail regions: 1024 px tiles at z5 (standard zoom 7, ~1.2 km/px), built from zoom-7 elevation.
DETAIL = {"europe": (-25, 34, 45, 71.5), "seasia": (92, -12, 153, 28), "africa": (-20, -36, 55, 38)}


def detail_tiles():
    """Output z5 tiles covering each DETAIL box (lon/lat -> 32x32 grid)."""
    n = 32
    out = set()
    for w, s, e, nlat in DETAIL.values():
        def ty(lat):
            return int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
        for tx in range(int((w + 180) / 360 * n), int((e + 180) / 360 * n) + 1):
            for t in range(ty(nlat), ty(s) + 1):
                out.add((tx, t))
    return sorted(out)


def fetch7(src7, tiles):
    src7.mkdir(parents=True, exist_ok=True)
    need = {(tx * 4 + i, ty * 4 + j) for tx, ty in tiles for i in range(-1, 5) for j in range(-1, 5) if 0 <= ty * 4 + j < 128}

    def get(xy):
        x, y = xy
        x %= 128
        p = src7 / f"{x}_{y}.png"
        if p.exists() and p.stat().st_size > 100:
            return
        for a in range(4):
            try:
                p.write_bytes(urllib.request.urlopen(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/7/{x}/{y}.png", timeout=30).read())
                return
            except Exception:
                pass
    with cf.ThreadPoolExecutor(48) as ex:
        list(ex.map(get, need))


def build_detail(src7):
    tiles = detail_tiles()
    n7 = 128
    m_per_px = 40075016.686 / (256 * n7)

    def et(x, y):
        x %= n7
        if y < 0 or y >= n7:
            return np.full((256, 256), -4000, np.float32)
        a = np.asarray(Image.open(src7 / f"{x}_{y}.png").convert("RGB"), dtype=np.float32)
        return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    for tx, ty in tiles:
        d = OUT / "5" / str(tx)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{ty}.jpg"
        if p.exists():
            continue
        mos = np.vstack([np.hstack([et(tx * 4 + i, ty * 4 + j) for i in range(-1, 5)]) for j in range(-1, 5)])
        e = mos[255:255 + 1026, 255:255 + 1026]
        n = 32 * 1024
        Image.fromarray(render(e, tile_lat(ty * 1024 - 1, n), tile_lat(ty * 1024 + 1025, n), m_per_px)).save(p, quality=72, optimize=True, progressive=True)
    print("detail tiles:", len(tiles))


if __name__ == "__main__":
    src = Path(sys.argv[1])
    if "--fetch" in sys.argv:
        fetch(src)
    build(src)
    us_terrain(src)
    if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):  # optional second dir for zoom-7 detail
        src7 = Path(sys.argv[2])
        if "--fetch" in sys.argv:
            fetch7(src7, detail_tiles())
        build_detail(src7)
