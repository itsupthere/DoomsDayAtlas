"""Build the DoomsDay Atlas page.

Reads FEMA National Risk Index county data (data/raw/), turns per-county loss
rates into 0-10 hazard scores, and inlines them with the county map into
index.html from atlas.template.html.

Refresh the raw data with:  python3 build.py --fetch
Europe / Asia-Pacific / World data comes from build_world.py (run it first if data/world.json is missing).
"""
import json, math, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
NRI_URL = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0"

# NRI hazard codes -> atlas factor keys
HAZ = {
    "eq": ["ERQK"], "hu": ["HRCN"], "to": ["TRND"], "st": ["SWND", "HAIL", "LTNG"],
    "wf": ["WFIR"], "fl": ["IFLD"], "cf": ["CFLD"], "dr": ["DRGT"], "ht": ["HWAV"],
    "ws": ["CWAV", "WNTW", "ISTM", "AVLN"], "vo": ["VLCN"], "ts": ["TSUN"], "ls": ["LNDS"],
}
BASE_FIELDS = ["STCOFIPS", "STATEABBRV", "COUNTY", "POPULATION", "AREA", "AGRIVALUE", "SOVI_SCORE", "RESL_SCORE"]


def fetch():
    meta = json.load(urllib.request.urlopen(NRI_URL + "?f=json"))
    names = {f["name"] for f in meta["fields"]}
    codes = sorted({c for cs in HAZ.values() for c in cs})
    loss = [c + s for c in codes for s in ("_ALRB", "_ALRP", "_ALRA", "_AFREQ") if c + s in names]
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "outFields": ",".join(BASE_FIELDS + loss), "returnGeometry": "false",
                                    "f": "json", "resultOffset": off, "resultRecordCount": 2000, "orderByFields": "OBJECTID"})
        page = [f["attributes"] for f in json.load(urllib.request.urlopen(NRI_URL + "/query?" + q))["features"]]
        rows += page
        off += len(page)
        if len(page) < 2000:
            break
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "nri.json").write_text(json.dumps(rows))
    print(f"fetched {len(rows)} counties")


def load():
    p = RAW / "nri.json"
    if p.exists():
        return json.loads(p.read_text())
    # first-run files: base fields and loss rates were pulled separately
    base = {r["STCOFIPS"]: r for r in json.loads((RAW / "nri_counties.json").read_text())}
    for r in json.loads((RAW / "nri_loss_rates.json").read_text()):
        base[r["STCOFIPS"]].update(r)
    return list(base.values())


def pct(sorted_vals, q):
    i = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def clamp(x, a=0.0, b=10.0):
    return max(a, min(b, x))


def build():
    rows = [r for r in load() if r["STCOFIPS"][:2] not in ("60", "66", "69", "72", "78")]
    by = {r["STCOFIPS"]: r for r in rows}

    # hazard loss rate per county, log-scaled to 0-10 against the national range
    raw = {k: {} for k in HAZ}
    for r in rows:
        for k, codes in HAZ.items():
            v = sum((r.get(c + s) or 0) for c in codes for s in ("_ALRB", "_ALRP", "_ALRA"))
            raw[k][r["STCOFIPS"]] = v
    freq = {k: {r["STCOFIPS"]: sum((r.get(c + "_AFREQ") or 0) for c in codes) for r in rows} for k, codes in HAZ.items()}

    def logscale(d):
        logs = sorted(math.log10(v) for v in d.values() if v > 0)
        lo, hi = pct(logs, 0.03), pct(logs, 0.995)
        return {f: 0 if v <= 0 else clamp(0.5 + 9.5 * (math.log10(v) - lo) / (hi - lo), 0.5) for f, v in d.items()}

    # half loss rate (how bad it is when it hits), half frequency (how often it hits)
    score = {}
    for k in HAZ:
        a, b = logscale(raw[k]), logscale(freq[k])
        score[k] = {f: (a[f] + b[f]) / 2 if a[f] and b[f] else 0 for f in a}

    def county_vec(r):
        f = r["STCOFIPS"]
        pop, area = r["POPULATION"] or 0, r["AREA"] or 1
        dens = pop / area
        apc = (r["AGRIVALUE"] or 0) / max(pop, 1)
        v = {k: score[k][f] for k in HAZ}
        v["pd"] = clamp(10 * math.log10(max(dens, 1)) / 4)                    # 1/sq mi -> 0, 10k/sq mi -> 10
        v["fd"] = clamp(10 - 10 * (math.log10(apc + 1) - 1.5) / (4.5 - 1.5))    # farm output per resident
        v["sv"] = (r["SOVI_SCORE"] or 50) / 10
        v["cr"] = (100 - (r["RESL_SCORE"] or 50)) / 10
        return pop, area, v

    out = {}
    for r in rows:
        pop, area, v = county_vec(r)
        out[r["STCOFIPS"]] = (r["STATEABBRV"], r["COUNTY"], pop, area, v)

    # map boundaries in us-atlas predate two changes: Valdez-Cordova (AK) split, CT planning regions
    def blend(fips_list, w=None):
        w = w or [by[f]["POPULATION"] for f in fips_list]
        tot = sum(w) or 1
        return {k: sum(out[f][4][k] * wi for f, wi in zip(fips_list, w)) / tot for k in out[fips_list[0]][4]}

    out["02261"] = ("AK", "Valdez-Cordova", by["02063"]["POPULATION"] + by["02066"]["POPULATION"],
                    by["02063"]["AREA"] + by["02066"]["AREA"], blend(["02063", "02066"]))
    ct = {  # old county: (name, pop 2020, sq mi, planning regions it mostly overlaps)
        "09001": ("Fairfield", 957419, 626, ["09120", "09190"]), "09003": ("Hartford", 899498, 735, ["09110"]),
        "09005": ("Litchfield", 185186, 920, ["09160"]), "09007": ("Middlesex", 164245, 369, ["09130"]),
        "09009": ("New Haven", 864835, 605, ["09170", "09140"]), "09011": ("New London", 268555, 665, ["09180"]),
        "09013": ("Tolland", 149788, 410, ["09110", "09150"]), "09015": ("Windham", 116418, 513, ["09150"]),
    }
    for f, (nm, pop, area, regs) in ct.items():
        v = blend(regs)
        v["pd"] = clamp(10 * math.log10(pop / area) / 4)
        out[f] = ("CT", nm, pop, area, v)
    for f in [f for f in out if f in ("02063", "02066") or (f.startswith("09") and f[2:] >= "110")]:
        del out[f]

    keys = list(HAZ) + ["pd", "fd", "sv", "cr"]
    data = {"keys": keys, "c": {f: [st, nm, int(pop), round(area, 1)] + [int(round(v[k] * 10)) for k in keys]
                                for f, (st, nm, pop, area, v) in sorted(out.items())}}

    topo = (ROOT / "data" / "counties-10m.json").read_text()  # unprojected US counties (us-atlas)
    tpl = (ROOT / "atlas.template.html").read_text()
    world_topo = (ROOT / "data" / "countries-10m.json").read_text()  # high-res borders for the region maps
    world = (ROOT / "data" / "world.json").read_text()  # from build_world.py
    html = (tpl.replace("__TOPO__", topo).replace("__COUNTIES__", json.dumps(data, separators=(",", ":")))
               .replace("__WORLDTOPO__", world_topo).replace("__WORLD__", world)
               .replace("__NAADMIN__", (ROOT / "data" / "na-admin1.json").read_text()))  # Canada + Mexico, from tools/make_na_admin.js
    (ROOT / "index.html").write_text(html)
    print(f"index.html: {len(out)} counties, {len(html) / 1e6:.2f} MB")
    for f in ("06037", "06075", "53033", "41005", "29143", "48201", "12086", "22071", "30049", "50023", "56029", "38101"):
        st, nm, pop, area, v = out[f]
        print(f, st, nm.ljust(14), " ".join(f"{k}={v[k]:.0f}" for k in keys))


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    build()
