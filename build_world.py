"""Country-level data for the Europe, Asia-Pacific and World tabs.

Inputs (data/raw/):
  inform_2026.json   INFORM Risk Mid-2026 (EU JRC), extracted from the official xlsx
  worldbank.json     World Bank indicators (latest year per country)
  iso3166.json       ISO numeric <-> alpha-3 codes and UN regions
Map: data/countries-50m.json (world-atlas)

Threat zones (nuclear targets, fallout, reactors, volcanoes, flashpoints, geomagnetic
latitude, growing-season cooling) are computed on a 1-degree land grid and averaged over
each country's area, so a big country is scored on all of its territory, not one point.

Writes data/world.json. Run: python3 build_world.py --fetch  (refreshes World Bank data)
"""
import json, math, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
WB = {"arable": "AG.LND.ARBL.HA.PC", "cereal": "AG.PRD.CREL.MT", "pop": "SP.POP.TOTL", "water": "ER.H2O.FWST.ZS",
      "elec": "EG.ELC.ACCS.ZS", "gdppc": "NY.GDP.PCAP.PP.KD", "renewh2o": "ER.H2O.INTR.PC"}

# ---- threat points (approximate, open-source) ----
SILO, BASE, CITY = "silo", "base", "city"
TARGETS = [
    # United States
    *[(SILO, la, lo) for la, lo in [(47.5, -111.3), (47.1, -109.9), (47.9, -110.2), (48.3, -101.3), (48.0, -100.6), (47.8, -101.9), (41.4, -104.3), (41.0, -103.8), (41.6, -104.9), (41.3, -103.4)]],
    *[(BASE, la, lo) for la, lo in [(38.73, -93.55), (32.5, -93.66), (44.15, -103.1), (41.12, -95.91), (30.8, -81.56), (47.72, -122.71), (38.74, -104.85), (35.04, -106.6), (36.95, -76.3), (32.68, -117.12), (21.35, -157.95), (13.58, 144.93), (61.25, -149.8), (63.98, -145.7)]],
    *[(CITY, la, lo) for la, lo in [(38.9, -77.04), (40.71, -74.0), (34.05, -118.24), (41.88, -87.63), (29.76, -95.37), (37.8, -122.27), (47.6, -122.33), (42.36, -71.06), (32.8, -96.9), (33.75, -84.39)]],
    # Russia
    *[(SILO, la, lo) for la, lo in [(54.0, 35.8), (51.7, 45.6), (51.1, 59.8), (55.3, 89.8), (55.3, 83.0), (53.4, 84.0), (52.5, 104.3), (56.6, 47.9), (58.0, 60.0), (56.9, 40.5), (57.8, 33.7)]],
    *[(BASE, la, lo) for la, lo in [(69.25, 33.3), (52.9, 158.4), (51.5, 46.2), (51.2, 128.4), (54.7, 20.5), (44.6, 33.5)]],
    *[(CITY, la, lo) for la, lo in [(55.75, 37.62), (59.94, 30.31), (55.03, 82.92), (56.84, 60.6), (43.12, 131.89), (68.97, 33.08)]],
    # China
    *[(SILO, la, lo) for la, lo in [(40.1, 96.5), (42.0, 92.5), (40.5, 107.9), (37.4, 97.4)]],
    *[(BASE, la, lo) for la, lo in [(18.2, 109.6), (36.1, 120.4), (34.4, 108.9)]],
    *[(CITY, la, lo) for la, lo in [(39.9, 116.4), (31.23, 121.47), (23.13, 113.26), (22.54, 114.06), (29.56, 106.55), (30.59, 114.3), (30.66, 104.07), (39.13, 117.2)]],
    # UK, France, NATO Europe
    *[(BASE, la, lo) for la, lo in [(56.07, -4.82), (51.36, -1.15), (52.41, 0.56), (48.3, -4.5), (48.64, 4.9), (43.52, 4.92), (51.17, 5.47), (50.17, 7.06), (51.66, 5.71), (46.03, 12.6), (45.43, 10.27), (37.0, 35.43), (49.44, 7.6), (50.11, 22.02), (54.48, 17.1), (44.08, 24.1)]],
    *[(CITY, la, lo) for la, lo in [(51.51, -0.13), (48.86, 2.35), (52.52, 13.4), (50.85, 4.35), (52.23, 21.01), (41.9, 12.5)]],
    # Asia-Pacific and others
    *[(BASE, la, lo) for la, lo in [(26.35, 127.77), (35.29, 139.67), (40.7, 141.37), (37.09, 127.03), (39.8, 125.75), (-7.3, 72.4), (-23.8, 133.74), (-21.8, 114.17), (31.0, 35.15)]],
    *[(CITY, la, lo) for la, lo in [(35.68, 139.69), (37.57, 126.98), (39.02, 125.75), (25.03, 121.57), (28.61, 77.21), (19.08, 72.88), (33.68, 73.05), (24.86, 67.0), (31.55, 74.34), (32.08, 34.78)]],
]
TW = {SILO: (1.0, 220, 10), BASE: (0.9, 160, 3), CITY: (0.85, 160, 1.2)}  # proximity weight, decay km (country scale), fallout weight

REACTORS = [(51.01, 2.13), (49.86, .63), (49.54, -1.88), (47.23, .17), (45.8, 5.27), (44.33, 4.73), (49.41, 6.22), (45.26, -.69), (44.1, .85), (44.63, 4.76), (47.51, 2.87), (47.73, 2.52), (48.52, 3.52), (45.4, 4.75), (47.72, 1.58), (46.46, .65), (49.98, 1.21), (50.09, 4.79),
    (51.21, -3.13), (54.03, -2.92), (55.97, -2.4), (52.21, 1.62), (54.63, -1.18), (51.32, 4.26), (50.53, 5.27), (51.43, 3.72), (39.81, -5.7), (41.2, .57), (39.21, -1.05), (40.95, .87), (40.7, -2.62),
    (47.37, 7.97), (47.6, 8.18), (47.55, 8.23), (57.26, 12.11), (60.4, 18.17), (57.42, 16.67), (61.24, 21.44), (60.37, 26.35), (49.18, 14.38), (49.09, 16.15), (48.26, 18.46), (48.49, 17.68), (46.57, 18.85),
    (45.94, 15.52), (44.32, 28.06), (43.75, 23.77), (47.51, 34.59), (51.33, 25.89), (50.3, 26.65), (47.81, 31.22), (51.39, 30.1), (54.76, 26.09), (59.85, 29.05), (67.47, 32.47), (57.9, 35.06), (54.17, 33.25),
    (51.67, 35.6), (51.27, 39.2), (47.6, 42.37), (52.09, 47.95), (56.84, 61.32), (68.05, 166.54), (40.18, 44.15), (36.14, 33.54),
    (22.6, 114.55), (21.71, 112.26), (21.92, 112.98), (21.67, 108.56), (19.46, 108.9), (27.04, 120.28), (25.45, 119.45), (29.1, 121.64), (30.43, 120.95), (34.69, 119.46), (36.71, 121.38), (36.97, 122.5), (39.8, 121.47), (40.4, 120.6), (23.9, 117.5),
    (37.43, 138.6), (35.54, 135.65), (35.52, 135.5), (33.52, 129.84), (31.83, 130.19), (33.49, 132.31), (43.04, 140.51), (38.4, 141.5), (36.47, 140.6), (37.42, 141.03), (34.62, 138.14), (35.7, 135.96),
    (35.32, 129.29), (35.41, 126.42), (37.09, 129.38), (35.71, 129.48), (19.83, 72.65), (24.87, 75.61), (8.17, 77.71), (14.86, 74.44), (21.24, 73.35), (28.16, 78.41), (12.56, 80.17), (32.39, 71.46), (24.85, 66.79),
    (28.83, 50.89), (23.96, 52.26), (-33.68, 18.43), (-23.01, -44.46), (-33.97, -59.2), (-32.23, -64.44), (19.72, -96.41), (43.81, -79.07), (43.87, -78.72), (44.33, -81.6), (45.07, -66.45), (24.07, 89.05),
    (33.39, -112.86), (35.21, -120.85), (35.31, -93.23), (41.31, -72.17), (27.35, -80.25), (25.43, -80.33), (33.14, -81.76), (31.93, -82.34), (42.07, -89.28), (41.24, -88.23), (41.25, -88.67), (41.39, -88.27), (41.73, -90.31),
    (38.24, -95.69), (30.76, -91.33), (29.99, -90.47), (38.43, -76.44), (41.96, -83.26), (41.98, -86.57), (45.33, -93.85), (44.62, -92.63), (32.01, -91.05), (38.76, -91.78), (40.36, -95.64), (42.9, -70.85), (39.46, -75.54),
    (43.52, -76.41), (33.96, -78.01), (35.63, -78.96), (35.43, -80.95), (41.6, -83.09), (41.8, -81.14), (40.62, -80.43), (40.22, -75.59), (39.76, -76.27), (41.09, -76.15), (35.05, -81.07), (34.79, -82.9), (35.23, -85.09),
    (35.6, -84.79), (32.3, -97.79), (28.8, -96.05), (38.06, -77.79), (37.17, -76.7), (46.47, -119.33), (44.28, -87.54), (34.7, -87.12), (31.22, -85.11)]
VOLCANOES = [(35.36, 138.73), (31.58, 130.66), (32.88, 131.1), (15.13, 120.35), (14.0, 121.0), (13.26, 123.69), (-7.54, 110.45), (-6.1, 105.42), (-8.25, 118.0), (2.68, 98.88), (-8.34, 115.51), (-39.28, 175.57),
    (-38.82, 175.9), (37.75, 14.99), (40.82, 14.43), (40.83, 14.14), (63.98, -19.7), (63.63, -19.05), (36.4, 25.4), (56.06, 160.64), (19.02, -98.62), (46.85, -121.76), (46.19, -122.18), (44.43, -110.67),
    (19.41, -155.29), (-0.68, -78.44), (-1.52, 29.25), (41.99, 128.08), (-4.27, 152.2), (-4.08, 145.04), (-19.53, 169.44), (-20.55, -175.39), (37.7, -118.9), (14.47, -90.88), (-15.79, -71.86)]
FLASHPOINTS = [(24.5, 119.5), (38.0, 127.0), (48.0, 37.5), (34.0, 74.5), (32.0, 35.0), (27.0, 56.0), (10.0, 114.0), (54.3, 23.0), (15.0, 43.0)]
GEOMAG_POLE = (80.8, -72.7)  # IGRF-14 dipole pole, 2025


def fetch_wb():
    out = {}
    for k, code in WB.items():
        url = f"https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&per_page=20000&date=2012:2025"
        best = {}
        for r in json.load(urllib.request.urlopen(url))[1] or []:
            iso, v = r["countryiso3code"], r["value"]
            if iso and v is not None and (iso not in best or int(r["date"]) > best[iso][0]):
                best[iso] = (int(r["date"]), v)
        out[k] = {i: v for i, (_, v) in best.items()}
    (RAW / "worldbank.json").write_text(json.dumps(out))


def km(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 12742 * math.asin(min(1, math.sqrt(a)))


def decode(topo):
    """TopoJSON -> {id or name: [polygon rings as (lon, lat) lists]}"""
    tr = topo.get("transform")
    arcs = []
    for a in topo["arcs"]:
        x = y = 0
        pts = []
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
        return out

    shapes = {}
    for g in topo["objects"]["countries"]["geometries"]:
        polys = [g["arcs"]] if g["type"] == "Polygon" else g.get("arcs", []) if g["type"] == "MultiPolygon" else []
        shapes[(g.get("id") or "", g["properties"]["name"])] = [[ring(r) for r in p] for p in polys]
    return shapes


def inside(lon, lat, r):
    hit = False
    j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i]; xj, yj = r[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def cell_values(la, lo):
    nk = fo = 0.0
    for t, tla, tlo in TARGETS:
        p, tau, fw = TW[t]
        d = km(la, lo, tla, tlo)
        nk = max(nk, p * math.exp(-max(0, d - 10) / tau))
        if d < 2500 and fw:
            # local wind: westerlies 25-65 deg, easterlies in the tropics
            dirx = 1 if abs(tla) >= 25 else -1
            dy = (la - tla) * 111.2
            dx = ((lo - tlo + 540) % 360 - 180) * 111.2 * math.cos(math.radians((la + tla) / 2))
            a, c = dx * dirx, dy
            if a > -40:
                aa = max(a, 0); s = 25 + 0.09 * aa
                fo += fw * math.exp(-aa / 600) * math.exp(-(c * c) / (2 * s * s))
    np_ = max((10 if (d := km(la, lo, a, b)) < 16 else 10 * math.exp(-(d - 16) / 110)) for a, b in REACTORS)
    vo = max(10 * math.exp(-km(la, lo, a, b) / 160) for a, b in VOLCANOES)
    fp = max(10 * math.exp(-km(la, lo, a, b) / 550) for a, b in FLASHPOINTS)
    # magnetic latitude from a centered dipole
    p0, l0 = map(math.radians, GEOMAG_POLE)
    s = math.sin(math.radians(la)) * math.sin(p0) + math.cos(math.radians(la)) * math.cos(p0) * math.cos(math.radians(lo) - l0)
    mlat = math.degrees(math.asin(max(-1, min(1, s))))
    gm = max(0, min(10, (abs(mlat) - 25) / 35 * 10))
    # nuclear/volcanic winter cooling: strongest in northern mid-high latitudes, milder south of the equator
    gs = max(0, min(10, (abs(la) - 12) / 45 * 10)) * (1 if la >= 0 else 0.65)
    return {"nk": 10 * nk, "fo": fo, "np": np_, "vo": vo, "fp": fp, "gm": gm, "gs": gs}


def clamp(x, a=0, b=10):
    return max(a, min(b, x))


def logscale(v, lo, hi, invert=False):
    if v is None or v <= 0:
        return None
    s = clamp(10 * (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))
    return 10 - s if invert else s


def build():
    inform = json.loads((RAW / "inform_2026.json").read_text())
    wb = json.loads((RAW / "worldbank.json").read_text())
    iso = {r["country-code"]: r for r in json.loads((RAW / "iso3166.json").read_text())}
    shapes = decode(json.loads((ROOT / "data" / "countries-50m.json").read_text()))
    by_name = {"Kosovo": ("XKX", "Europe", "Southern Europe"), "N. Cyprus": ("CYP", "Asia", "Western Asia"), "Somaliland": ("SOM", "Africa", "Sub-Saharan Africa")}

    out = {}
    for (fid, name), polys in shapes.items():
        if name in ("Antarctica", "Fr. S. Antarctic Lands", "Indian Ocean Ter.", "Siachen Glacier", "Ashmore and Cartier Is."):
            continue
        if fid in iso:
            r = iso[fid]; a3, reg, sub = r["alpha-3"], r["region"], r["sub-region"]
        elif name in by_name:
            a3, reg, sub = by_name[name]
        else:
            continue
        rings = [r for p in polys for r in p]
        if not rings:
            continue
        lons = [p[0] for r in rings for p in r]; lats = [p[1] for r in rings for p in r]
        # sample a 1-degree grid (0.25 for small countries) inside the shape
        span = (max(lons) - min(lons)) * (max(lats) - min(lats))
        step = 1.0 if span > 60 else 0.5 if span > 6 else 0.25
        cells = []
        la = math.floor(min(lats) / step) * step + step / 2
        while la < max(lats):
            lo = math.floor(min(lons) / step) * step + step / 2
            while lo < max(lons):
                if any(inside(lo, la, p[0]) and not any(inside(lo, la, h) for h in p[1:]) for p in polys):
                    cells.append((la, lo))
                lo += step
            la += step
        if not cells:
            big = max(rings, key=len)
            cells = [(sum(p[1] for p in big) / len(big), sum(p[0] for p in big) / len(big))]
        vals = [(math.cos(math.radians(la)), cell_values(la, lo)) for la, lo in cells]
        wsum = sum(w for w, _ in vals)
        mod = {}
        for k in vals[0][1]:
            mean = sum(w * v[k] for w, v in vals) / wsum
            if k in ("gm", "gs"):
                mod[k] = mean
            else:  # point threats: blend the average with the worst 10% so a big country still shows its hot spots
                srt = sorted(v[k] for _, v in vals)
                mod[k] = 0.4 * mean + 0.6 * srt[int(0.9 * (len(srt) - 1))]
        clat = sum(c[0] for c in cells) / len(cells); clon = sum(c[1] for c in cells) / len(cells)
        entry = out.setdefault(a3, {"name": name, "ids": [], "reg": reg, "sub": sub, "lat": clat, "lon": clon, "mod": mod, "n": len(cells)})
        if fid not in entry["ids"]:
            entry["ids"].append(fid)

    # Taiwan is not in INFORM; estimate from Japan / South Korea profiles and Taiwan's own hazard record
    inform["TWN"] = {"COUNTRY": "Taiwan", "Earthquake": 8.5, "River Flood": 6.5, "Tsunami": 6, "Tropical Cyclone": 9, "Coastal flood": 7,
                     "Drought": 2, "Epidemic": 3, "Projected Conflict Probability": 4, "Current Conflict Intensity": 1, "Socio-Economic Vulnerability": 0.5,
                     "Food Security": 0.5, "Governance": 1.5, "Infrastructure": 0.5, "Access to health care": 0.5, "Physical infrastructure": 0.5,
                     "density": 650, "_est": "Estimated: Taiwan is not covered by INFORM"}
    # territories without their own INFORM entry borrow their governing country's scores
    PARENT = {"PRI": "USA", "GUM": "USA", "VIR": "USA", "ASM": "USA", "MNP": "USA", "GRL": "DNK", "FRO": "DNK", "HKG": "CHN", "MAC": "CHN",
              "NCL": "FRA", "PYF": "FRA", "WLF": "FRA", "SPM": "FRA", "MAF": "FRA", "BLM": "FRA", "MCO": "FRA", "AND": "ESP", "SMR": "ITA", "VAT": "ITA",
              "JEY": "GBR", "GGY": "GBR", "IMN": "GBR", "BMU": "GBR", "CYM": "GBR", "VGB": "GBR", "TCA": "GBR", "MSR": "GBR", "AIA": "GBR", "FLK": "GBR",
              "SHN": "GBR", "PCN": "GBR", "IOT": "GBR", "SGS": "GBR", "ALA": "FIN", "ABW": "NLD", "CUW": "NLD", "SXM": "NLD", "XKX": "SRB", "ESH": "MAR",
              "COK": "NZL", "NIU": "NZL", "NFK": "AUS", "HMD": "AUS"}
    for a3, par in PARENT.items():
        if a3 not in inform and par in inform:
            inform[a3] = dict(inform[par], COUNTRY=out[a3]["name"] if a3 in out else a3, _est=f"Approximated from {inform[par]['COUNTRY']}")
            inform[a3].pop("density", None)
    fo_max = max(e["mod"]["fo"] for e in out.values())
    nk_max = max(e["mod"]["nk"] for e in out.values())
    keys = ["eq", "fl", "ts", "tc", "cf", "dr", "ep", "cp", "ci", "sev", "fs", "gov", "inf", "hc",
            "pd", "fd", "wa", "gr", "nk", "fo", "np", "vo", "fp", "gm", "gs"]
    rows = {}
    for a3, e in out.items():
        I = inform.get(a3)
        g = lambda k: (wb[k].get(a3) if k in wb else None)
        pop = g("pop")
        cereal_pc = (g("cereal") or 0) * 1000 / pop if pop else None  # kg per person
        arable = g("arable")
        food_parts = [x for x in [logscale(cereal_pc, 20, 1500, invert=True), logscale(arable, 0.01, 1.0, invert=True),
                                  I and I.get("Food Security")] if x is not None]
        water = g("water")
        water_parts = [x for x in [logscale(water, 5, 400), logscale(g("renewh2o"), 100, 20000, invert=True)] if x is not None]
        elec = g("elec")
        grid_parts = [x for x in [I and I.get("Physical infrastructure"), None if elec is None else (100 - elec) / 10] if x is not None]
        dens = (I or {}).get("density")
        if dens is None and pop:
            dens = None
        m = e["mod"]
        v = {
            "eq": I and I.get("Earthquake"), "fl": I and I.get("River Flood"), "ts": I and I.get("Tsunami"),
            "tc": I and I.get("Tropical Cyclone"), "cf": I and I.get("Coastal flood"), "dr": I and I.get("Drought"),
            "ep": I and I.get("Epidemic"), "cp": I and I.get("Projected Conflict Probability"), "ci": I and I.get("Current Conflict Intensity"),
            "sev": I and I.get("Socio-Economic Vulnerability"), "fs": I and I.get("Food Security"), "gov": I and I.get("Governance"),
            "inf": I and I.get("Infrastructure"), "hc": I and I.get("Access to health care"),
            "pd": logscale(dens, 2, 3000) if dens else None,
            "fd": sum(food_parts) / len(food_parts) if food_parts else None,
            "wa": sum(water_parts) / len(water_parts) if water_parts else None,
            "gr": sum(grid_parts) / len(grid_parts) if grid_parts else None,
            "nk": 10 * m["nk"] / nk_max, "fo": 10 * math.log(1 + m["fo"] / 0.05) / math.log(1 + fo_max / 0.05),
            "np": m["np"], "vo": m["vo"], "fp": m["fp"], "gm": m["gm"], "gs": m["gs"],
        }
        if a3 == "TWN" and v["wa"] is None:
            v["wa"] = 5
        has_inform = 0 if I is None else 2 if I.get("_est") else 1
        rows[a3] = [e["name"] if not I else I["COUNTRY"], e["reg"], e["sub"], e["ids"], round(e["lat"], 2), round(e["lon"], 2),
                    int(pop or 0), has_inform, (I or {}).get("_est", "")] + [(-1 if v[k] is None else int(round(float(v[k]) * 10))) for k in keys]
    data = {"keys": keys, "c": rows,
            "targets": [[t, la, lo] for t, la, lo in TARGETS], "reactors": REACTORS, "volcanoes": VOLCANOES, "flash": FLASHPOINTS}
    (ROOT / "data" / "world.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"world.json: {len(rows)} countries ({sum(r[7] == 1 for r in rows.values())} with INFORM, {sum(r[7] == 2 for r in rows.values())} estimated)")
    for a3 in ("NZL", "AUS", "ISL", "IRL", "CHE", "DEU", "POL", "UKR", "CHN", "JPN", "TWN", "KOR", "FJI", "ARG", "USA", "RUS"):
        if a3 in rows:
            r = rows[a3]
            print(a3, r[0][:14].ljust(14), " ".join(f"{k}={'-' if x < 0 else x // 10}" for k, x in zip(keys, r[9:])))


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch_wb()
    build()
