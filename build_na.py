"""Canada and Mexico hazard data for the North America tab -> data/na-units.json

Measured from open catalogs, then put on FEMA's US scale:
  earthquakes  USGS ComCat, M4.5+ since 1975
  hurricanes   NOAA NHC HURDAT2 (Atlantic + NE/Central Pacific), hurricane-force fixes since 1980
  volcanoes    Smithsonian Global Volcanism Program, Holocene volcanoes
  population   Statistics Canada 2021 Census, INEGI 2020 Census

The same raw measure is computed for every US state and regressed against that state's
population-weighted FEMA score, so a Canadian province or Mexican state lands on the same
0-10 scale as a US county. Other factors stay as estimates in atlas.template.html (NA_EST).

    python3 build_na.py [--fetch]     needs numpy; raw downloads cached in data/raw/
"""
import json, math, sys, urllib.request
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
YEARS_EQ, YEARS_HU = 2025 - 1975 + 1, 2025 - 1980 + 1

# Official census counts
POP = {"CA-ON": 14223942, "CA-QC": 8501833, "CA-BC": 5000879, "CA-AB": 4262635, "CA-MB": 1342153, "CA-SK": 1132505,
       "CA-NS": 969383, "CA-NB": 775610, "CA-NL": 510550, "CA-PE": 154331, "CA-NT": 41070, "CA-YT": 40232, "CA-NU": 36858,
       "MX-AGU": 1425607, "MX-BCN": 3769020, "MX-BCS": 798447, "MX-CAM": 928363, "MX-CHP": 5543828, "MX-CHH": 3741869,
       "MX-CMX": 9209944, "MX-COA": 3146771, "MX-COL": 731391, "MX-DUR": 1832650, "MX-GUA": 6166934, "MX-GRO": 3540685,
       "MX-HID": 3082841, "MX-JAL": 8348151, "MX-MEX": 16992418, "MX-MIC": 4748846, "MX-MOR": 1971520, "MX-NAY": 1235456,
       "MX-NLE": 5784442, "MX-OAX": 4132148, "MX-PUE": 6583278, "MX-QUE": 2368467, "MX-ROO": 1857985, "MX-SLP": 2822255,
       "MX-SIN": 3026943, "MX-SON": 2944840, "MX-TAB": 2402598, "MX-TAM": 3527735, "MX-TLA": 1342977, "MX-VER": 8062579,
       "MX-YUC": 2320898, "MX-ZAC": 1622138}

SOURCES = {
    "quakes": ("usgs_quakes.json", [f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime={a}-01-01&endtime={b}-12-31&minmagnitude=4.5&minlatitude=10&maxlatitude=84&minlongitude=-180&maxlongitude=-45&orderby=time-asc"
                                    for a, b in ((1975, 1999), (2000, 2025))]),
    "hurdat_atl": ("hurdat2_atlantic.txt", ["https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-092326.txt"]),
    "hurdat_pac": ("hurdat2_nepac.txt", ["https://www.nhc.noaa.gov/data/hurdat/hurdat2-nepac-1949-2025-092926.txt"]),
    "volcanoes": ("gvp_holocene.json", ["https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=application/json"]),
}


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, (fn, urls) in SOURCES.items():
        if name == "quakes":
            feats = []
            for u in urls:
                feats += json.load(urllib.request.urlopen(u, timeout=120))["features"]
            (RAW / fn).write_text(json.dumps([[f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], f["properties"]["mag"]] for f in feats]))
        elif name == "volcanoes":
            d = json.load(urllib.request.urlopen(urls[0], timeout=120))
            (RAW / fn).write_text(json.dumps([[f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], f["properties"].get("Last_Eruption_Year")]
                                              for f in d["features"] if f.get("geometry")]))
        else:
            (RAW / fn).write_bytes(urllib.request.urlopen(urls[0], timeout=120).read())
        print("fetched", fn)


def hurdat_points():
    pts = []
    for fn in ("hurdat2_atlantic.txt", "hurdat2_nepac.txt"):
        for line in (RAW / fn).read_text().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) < 8 or not p[0][:4].isdigit() or int(p[0][:4]) < 1980:
                continue
            if int(p[6]) < 64:  # hurricane force (kt)
                continue
            lat = float(p[4][:-1]) * (1 if p[4][-1] == "N" else -1)
            lon = float(p[5][:-1]) * (-1 if p[5][-1] == "W" else 1)
            pts.append((lon, lat))
    return np.array(pts)


def decode(topo, obj):
    tr = topo.get("transform")
    arcs = []
    for a in topo["arcs"]:
        x = y = 0; pts = []
        for p in a:
            if tr:
                x += p[0]; y += p[1]
                pts.append((x * tr["scale"][0] + tr["translate"][0], y * tr["scale"][1] + tr["translate"][1]))
            else:
                pts.append(tuple(p))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(seg if not out else seg[1:])
        return np.array(out)
    shapes = {}
    for g in topo["objects"][obj]["geometries"]:
        polys = [g["arcs"]] if g["type"] == "Polygon" else g.get("arcs", []) if g["type"] == "MultiPolygon" else []
        shapes[g.get("id") or g["properties"]["name"]] = (g.get("properties", {}).get("name"), [[ring(r) for r in p] for p in polys])
    return shapes


def inside(lon, lat, r):
    """vectorised even-odd test of points (lon, lat arrays) against one ring"""
    x, y = r[:, 0], r[:, 1]
    hit = np.zeros(lon.shape, bool)
    j = len(r) - 1
    for i in range(len(r)):
        c = ((y[i] > lat) != (y[j] > lat)) & (lon < (x[j] - x[i]) * (lat - y[i]) / (y[j] - y[i] + 1e-12) + x[i])
        hit ^= c
        j = i
    return hit


def samples(polys):
    rings = [p[0] for p in polys if len(p[0]) > 3]
    allp = np.vstack(rings)
    w, e, s, n = allp[:, 0].min(), allp[:, 0].max(), allp[:, 1].min(), allp[:, 1].max()
    span = (e - w) * (n - s)
    step = 1.0 if span > 400 else 0.5 if span > 30 else 0.2
    gx, gy = np.meshgrid(np.arange(w + step / 2, e, step), np.arange(s + step / 2, n, step))
    lon, lat = gx.ravel(), gy.ravel()
    m = np.zeros(lon.shape, bool)
    for p in polys:
        if len(p[0]) < 4:
            continue
        a = inside(lon, lat, p[0])
        for h in p[1:]:
            a &= ~inside(lon, lat, h)
        m |= a
    if not m.any():
        big = max(rings, key=len)
        return np.array([big[:, 0].mean()]), np.array([big[:, 1].mean()])
    return lon[m], lat[m]


def km(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dl = np.radians(lon2[None, :] - lon1[:, None])
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def raw_measures(lon, lat, Q, H, V):
    """per-sample raw hazard measures, averaged over the area"""
    out = {}
    d = km(lon, lat, Q[:, 0], Q[:, 1])
    out["eq"] = float(np.mean(np.sum(np.where(d < 150, 10 ** (0.75 * (Q[None, :, 2] - 4.5)) * np.exp(-d / 60), 0), axis=1))) / YEARS_EQ
    d = km(lon, lat, H[:, 0], H[:, 1])
    out["hu"] = float(np.mean(np.sum(np.exp(-d / 80) * (d < 300), axis=1))) / YEARS_HU
    d = km(lon, lat, V[:, 0], V[:, 1])
    out["vo"] = float(np.mean(np.sum(V[None, :, 2] * np.exp(-d / 60) * (d < 250), axis=1)))
    return out


def calibrate(us_raw, us_fema, x):
    """least-squares fit of FEMA state score on log10(raw) over US states with any exposure"""
    pairs = [(math.log10(r), f) for r, f in zip(us_raw, us_fema) if r > 0]
    zero = [f for r, f in zip(us_raw, us_fema) if r <= 0]
    floor = float(np.mean(zero)) if zero else 0.0  # what FEMA gives states with nothing in the catalog
    if len(pairs) < 3:
        return floor
    X = np.array([p[0] for p in pairs]); Y = np.array([p[1] for p in pairs])
    b, a = np.polyfit(X, Y, 1)
    if x <= 0:
        return floor
    return float(np.clip(a + b * math.log10(x), 0.3, 10))


def build():
    import build as us  # FEMA county scores
    counties = us.county_scores()
    Q = np.array(json.loads((RAW / "usgs_quakes.json").read_text()), float)
    H = hurdat_points()
    vraw = json.loads((RAW / "gvp_holocene.json").read_text())
    V = np.array([[v[0], v[1], 2.0 if (v[2] or -99999) >= 1900 else 1.0 if (v[2] or -99999) >= -10000 else 0.5] for v in vraw], float)
    print(f"{len(Q)} quakes, {len(H)} hurricane fixes, {len(V)} volcanoes")

    us_topo = json.loads((ROOT / "data" / "counties-10m.json").read_text())
    states = decode(us_topo, "states")
    fema = {}  # population-weighted FEMA score per state FIPS
    for fips, (st, nm, pop, area, v) in counties.items():
        a = fema.setdefault(fips[:2], {"p": 0, "eq": 0, "hu": 0, "vo": 0})
        a["p"] += pop
        for k in ("eq", "hu", "vo"):
            a[k] += v[k] * pop
    us_raw, us_f = {k: [] for k in ("eq", "hu", "vo")}, {k: [] for k in ("eq", "hu", "vo")}
    for sid, (name, polys) in states.items():
        if sid not in fema or not polys:
            continue
        lon, lat = samples(polys)
        r = raw_measures(lon, lat, Q, H, V)
        for k in r:
            us_raw[k].append(r[k]); us_f[k].append(fema[sid][k] / max(fema[sid]["p"], 1))
    print("calibrated on", len(us_raw["eq"]), "states")

    admin = decode(json.loads((ROOT / "data" / "na-admin1.json").read_text()), "admin")
    out = {}
    for code, (name, polys) in admin.items():
        # geoBoundaries rings use the opposite winding; even-odd test does not care
        lon, lat = samples(polys)
        r = raw_measures(lon, lat, Q, H, V)
        out[code] = {"pop": POP.get(code), "eq": round(calibrate(us_raw["eq"], us_f["eq"], r["eq"]), 1),
                     "hu": round(calibrate(us_raw["hu"], us_f["hu"], r["hu"]), 1), "vo": round(calibrate(us_raw["vo"], us_f["vo"], r["vo"]), 1)}
    (ROOT / "data" / "na-units.json").write_text(json.dumps(out, separators=(",", ":")))
    for code in ("CA-BC", "CA-ON", "CA-NS", "CA-QC", "MX-GRO", "MX-OAX", "MX-CMX", "MX-ROO", "MX-YUC", "MX-NLE", "MX-COL", "MX-BCN"):
        print(code, out[code])


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    build()
