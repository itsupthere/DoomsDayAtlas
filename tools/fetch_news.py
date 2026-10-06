"""Collect current events for the "Now" tab -> data/news.json

Reads official alert feeds and world-news RSS (headlines and links only), keeps items that
match a DoomsDay scenario, places them on the map, and scores how active each scenario is.
Run by .github/workflows/news.yml every 2 hours; standard library only.

    python3 tools/fetch_news.py
"""
import json, re, time, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "DoomsDayAtlas/1.0 (https://github.com/itsupthere/DoomsDayAtlas)"}
KEEP_HOURS = 72

NEWS_FEEDS = {
    "BBC": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR": "https://feeds.npr.org/1004/rss.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "DW": "https://rss.dw.com/rdf/rss-en-world",
    "WHO": "https://www.who.int/rss-feeds/news-english.xml",
}

# scenario ids match the atlas: keyword patterns are matched against headline + summary
CATS = {
    "nuclear": r"\bnuclear (weapon|warhead|strike|attack|threat|test|arsenal|doctrine|war)|\bicbm|ballistic missile|\bwarheads?\b|new start|hypersonic",
    "war": r"\b(invasion|invade[sd]?|airstrikes?|air strikes?|missile (strike|attack)s?|shelling|drone (attack|strike)s?|troops|ground offensive|ceasefire|front ?line|military escalation|war (in|on|with|between|zone|live)|at war|warplanes?|naval blockade|mobiliz\w+|\w+ war\b)",
    "pandemic": r"\b(outbreak|epidemic|pandemic|h5n1|bird flu|avian influenza|ebola|marburg|mpox|cholera|measles|dengue|novel virus|disease x|plague)\b",
    "climate": r"\b(heatwave|heat wave|record heat|flood(s|ing)?|hurricane|typhoon|cyclone|tropical storm|monsoon|extreme weather|storm surge)\b",
    "drought": r"\b(drought|water shortage|water crisis|wildfires?|bushfires?|crop failure|dry spell)\b",
    "grid": r"\b(blackout|power outage|power cut|grid failure|cyber ?attack|ransomware|hack(ed|ers)? .{0,30}(infrastructure|grid|utility|water system)|undersea cable)\b",
    "solar": r"\b(geomagnetic|solar storm|solar flare|coronal mass ejection|\bcme\b|aurora warning)",
    "collapse": r"\b(famine|food crisis|hunger crisis|riots?|civil unrest|coup|martial law|state of emergency|mass protests|hyperinflation|bank run|refugee crisis)\b",
    "ring": r"\b(earthquake|quake|tremor|tsunami|volcan(o|ic)|eruption|aftershock)s?\b",
    "meltdown": r"\b(nuclear (plant|power plant|reactor|facility)|reactor|radiation leak|radioactive|zaporizhzhia|chernobyl|fukushima)\b",
}

COUNTRY_ALIASES = {"US": "United States of America", "USA": "United States of America", "U.S.": "United States of America", "America": "United States of America",
                   "UK": "United Kingdom", "Britain": "United Kingdom", "Russia": "Russian Federation", "Iran": "Iran", "Syria": "Syria", "Korea": "Korea Republic",
                   "South Korea": "Korea Republic", "North Korea": "Korea DPR", "Gaza": "Palestine", "West Bank": "Palestine", "Congo": "Congo DR", "DR Congo": "Congo DR",
                   "Vietnam": "Viet Nam", "Laos": "Lao PDR", "Taiwan": "Taiwan", "Czech": "Czech Republic", "Turkey": "Türkiye", "Ivory Coast": "Côte d'Ivoire"}


def get(url, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def when(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def clean(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


def load_places():
    w = json.loads((ROOT / "data" / "world.json").read_text())
    places = {}
    for iso, r in w["c"].items():
        places[r[0]] = (r[4], r[5])
    for alias, name in COUNTRY_ALIASES.items():
        if name in places:
            places[alias] = places[name]
    # longest names first so "South Sudan" wins over "Sudan"
    names = sorted(places, key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names if len(n) > 3 or n in ("US", "UK", "USA")) + r")\b")
    return places, rx


def classify(text):
    t = text.lower()
    t = re.sub(r"world war (one|two|i{1,2}|1|2)|war crimes?|culture war|trade war|price war|war of words|war chest", " ", t)  # not active conflict
    return [c for c, p in CATS.items() if re.search(p, t)]


def news_items(places, rx):
    out = []
    for src, url in NEWS_FEEDS.items():
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            print("skip", src, e)
            continue
        items = root.iter("item") if root.find(".//item") is not None else root.iter("{http://purl.org/rss/1.0/}item")
        for it in items:
            g = lambda tag: (it.findtext(tag) or it.findtext("{http://purl.org/rss/1.0/}" + tag) or it.findtext("{http://purl.org/dc/elements/1.1/}date") if tag == "pubDate" else it.findtext(tag) or it.findtext("{http://purl.org/rss/1.0/}" + tag))
            title, desc, link = clean(g("title")), clean(g("description")), (g("link") or "").strip()
            cats = classify(title + " " + desc)
            if not cats:
                continue
            m = rx.search(title) or rx.search(desc)
            place = m.group(1) if m else None
            ll = places.get(place) if place else None
            out.append({"t": when(g("pubDate")) or int(time.time() * 1000), "title": title, "link": link, "src": src, "cats": cats,
                        "place": COUNTRY_ALIASES.get(place, place), "lat": ll[0] if ll else None, "lon": ll[1] if ll else None, "sev": 1 + ("nuclear" in cats) + ("war" in cats and "killed" in (title + desc).lower())})
    return out


def gdacs_items():
    out = []
    try:
        root = ET.fromstring(get("https://www.gdacs.org/xml/rss.xml"))
    except Exception as e:
        print("skip GDACS", e)
        return out
    ns = {"geo": "http://www.w3.org/2003/01/geo/wgs84_pos#", "gdacs": "http://www.gdacs.org"}
    kind = {"EQ": ["ring"], "TC": ["climate"], "FL": ["climate"], "VO": ["ring"], "DR": ["drought"], "WF": ["drought"], "TS": ["ring"]}
    for it in root.iter("item"):
        lvl = (it.findtext("gdacs:alertlevel", namespaces=ns) or "").lower()
        typ = it.findtext("gdacs:eventtype", namespaces=ns) or ""
        if lvl not in ("orange", "red") or typ not in kind:
            continue
        lat, lon = it.findtext("geo:Point/geo:lat", namespaces=ns), it.findtext("geo:Point/geo:long", namespaces=ns)
        out.append({"t": when(it.findtext("pubDate")), "title": clean(it.findtext("title")), "link": (it.findtext("link") or "").strip(), "src": "GDACS",
                    "cats": kind[typ], "place": clean(it.findtext("gdacs:country", namespaces=ns)) or None,
                    "lat": float(lat) if lat else None, "lon": float(lon) if lon else None, "sev": 3 if lvl == "red" else 2})
    return out


def usgs_items():
    out = []
    try:
        d = json.loads(get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"))
    except Exception as e:
        print("skip USGS", e)
        return out
    for f in d["features"]:
        p, c = f["properties"], f["geometry"]["coordinates"]
        out.append({"t": p["time"], "title": p["title"], "link": p["url"], "src": "USGS", "cats": ["ring"] + (["meltdown"] if False else []),
                    "place": p.get("place"), "lat": c[1], "lon": c[0], "sev": 3 if (p.get("mag") or 0) >= 7 else 2})
    return out


def swpc_items():
    out = []
    try:
        d = json.loads(get("https://services.swpc.noaa.gov/products/alerts.json"))
    except Exception as e:
        print("skip SWPC", e)
        return out
    for a in d[:40]:
        msg = a.get("message", "")
        m = re.search(r"(WARNING|ALERT|WATCH): (Geomagnetic [^\r\n]*|Solar Radiation[^\r\n]*|Radio Blackout[^\r\n]*)", msg)
        if not m or not re.search(r"G[3-5]|S[3-5]|R[3-5]|Kp index of [7-9]", msg):
            continue
        out.append({"t": when(a.get("issue_datetime", "").replace(" ", "T") + "Z"), "title": "NOAA space weather " + m.group(1).lower() + ": " + m.group(2)[:120],
                    "link": "https://www.swpc.noaa.gov/", "src": "NOAA SWPC", "cats": ["solar"], "place": None, "lat": None, "lon": None, "sev": 2})
    return out


def nws_items():
    out = []
    try:
        d = json.loads(get("https://api.weather.gov/alerts/active?severity=Extreme&status=actual"))
    except Exception as e:
        print("skip NWS", e)
        return out
    for f in d.get("features", [])[:40]:
        p = f["properties"]
        ev = p.get("event", "")
        cats = classify(ev + " " + (p.get("headline") or "")) or ["climate"]
        lat = lon = None
        g = f.get("geometry")
        if g and g.get("type") == "Polygon":
            pts = g["coordinates"][0]
            lon, lat = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
        out.append({"t": when(p.get("sent")), "title": f"{ev}: {p.get('areaDesc', '')[:120]}", "link": p.get("@id") or "https://alerts.weather.gov/", "src": "NWS",
                    "cats": cats, "place": p.get("areaDesc", "")[:60], "lat": lat, "lon": lon, "sev": 2})
    return out


def main():
    places, rx = load_places()
    items = news_items(places, rx) + gdacs_items() + usgs_items() + swpc_items() + nws_items()
    now = int(time.time() * 1000)
    cutoff = now - KEEP_HOURS * 3600 * 1000
    seen, keep = set(), []
    for it in sorted((i for i in items if i["t"] and i["t"] >= cutoff), key=lambda i: -i["t"]):
        k = re.sub(r"\W+", "", it["title"].lower())[:70]
        if k in seen:
            continue
        seen.add(k)
        keep.append(it)
    keep = keep[:160]
    # how active each scenario is: severity, discounted by age (half-life 24 h)
    pressure = {c: 0.0 for c in CATS}
    for it in keep:
        w = it["sev"] * 0.5 ** ((now - it["t"]) / 86400000)
        for c in it["cats"]:
            pressure[c] += w
    out = {"updated": now, "hours": KEEP_HOURS, "items": keep, "pressure": {k: round(v, 2) for k, v in pressure.items()},
           "sources": sorted({i["src"] for i in keep})}
    (ROOT / "data" / "news.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(keep)} items;", {k: round(v, 1) for k, v in pressure.items()})


if __name__ == "__main__":
    main()
