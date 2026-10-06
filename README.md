# DoomsDay Atlas

An interactive map of disaster survivability. Every US county, Canadian province and Mexican state, and every country in Europe, Asia-Pacific, Africa and the world, scored for up to 14 scenarios: nuclear war, nuclear winter, regional war, climate 2050, mega-drought, grid collapse, solar superstorm / EMP, pandemic, societal breakdown, Yellowstone and supervolcano winter, Cascadia, New Madrid, reactor disasters and everyday natural hazards.

- **North America:** all 3,142 US counties from FEMA's National Risk Index, plus Canada's 13 provinces and territories and Mexico's 32 states (estimated profiles), with modeled threat zones on the same zoomable terrain map as the other tabs.
- **Europe · Asia-Pacific · Africa · World:** country scores from the EU's INFORM Risk Index and World Bank data, with threat zones (blast, fallout, reactors, volcanoes, flashpoints) drawn point by point on a zoomable terrain map.
- **Scenario playback:** watch a scenario unfold phase by phase; the map re-scores at each stage.
- **Your location:** compare your county or country with the best match, with radar and timeline charts, a preparedness checklist and a supplies calculator.
- **Live layer:** this week's earthquakes (USGS) and active wildfires, volcanoes and storms (NASA EONET) pulse on the maps, with a live ticker and the current Doomsday Clock. Live data loads on the public site; the claude.ai viewer blocks it.
- **Plan my escape:** the safest reachable places within about 2, 6 and 12 hours of home (6 h, 12 h and a day between countries), drawn on the map, with real road routes where available (OSRM) and a warning when the route passes near a likely target.
- **Fallout winds:** plumes follow a year-round, winter, spring, summer or fall jet stream, or today's 500 hPa forecast from Open-Meteo.
- **Built for phones:** map-first layout, swipeable tabs and toggles, tap the map for details with Set as home / Compare buttons.
- **Now:** current wars, outbreaks, disasters, outages and space weather from news RSS and official alerts (GDACS, USGS, NOAA, NWS, WHO), sorted by scenario. A GitHub Action refreshes `data/news.json` every 2 hours.
- **Your household:** people, pets, health needs, car, home type and water source tailor the plan, supplies and escape routes. Stored only in your browser.
- **Printable plan with radio frequencies:** a one-page PDF with your threats, where to go, meeting points, contacts, supplies, and emergency frequencies, including your county's own NOAA Weather Radio transmitter and SAME code.
- **Safest place on Earth:** ranks every country of 1M+ people across all 12 global scenarios.

## Run it

The page loads its data from `data/na-bundle.json` and `data/world-bundle.json`, so it needs a web server (browsers block those requests from a file on disk). Use GitHub Pages, any static host, or locally:

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000. Live events, live winds, road routes and street-level maps need an internet connection.

## Rebuild the data

`index.html` is generated from `atlas.template.html`. Run the steps in this order:

```bash
python3 build_world.py --fetch      # countries: INFORM + World Bank -> data/world.json
python3 build_terrain.py SRC SRC7 --fetch # terrain tiles -> tiles/ (+ sharper tiles/5 for North America, Europe, SE Asia, Africa); needs numpy, Pillow
python3 build_na.py --fetch          # Canada + Mexico: USGS quakes, NOAA hurricanes, Smithsonian volcanoes, census -> data/na-units.json
python3 build_us_extra.py --fetch    # county growing season, climate trend, water stress, outages, NOAA Weather Radio -> data/us-extra.json
python3 build.py --fetch             # US counties from FEMA; writes index.html and the data bundles
python3 tools/fetch_news.py          # Now tab (the GitHub Action runs this every 2 hours)
```

`data/na-admin1.json` (Canada and Mexico boundaries) is made once with `node tools/make_na_admin.js can.geojson mex.geojson` from geoBoundaries files.

`build_world.py` reads `data/raw/inform_2026.json`, extracted from the INFORM Mid-2026 spreadsheet in `data/raw/`. `--fetch` refreshes the online sources; without it the scripts use the files already in `data/raw/`.

## Data sources

- [FEMA National Risk Index](https://resilience.climate.gov/datasets/FEMA::national-risk-index-counties): county hazards, population, farm output, social vulnerability, community resilience
- [INFORM Risk Index Mid-2026](https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Results-and-data), EU Joint Research Centre: country hazards, conflict, governance, health care
- [World Bank Open Data](https://data.worldbank.org/): farmland, grain output, water stress, electricity access
- [NOAA nClimDiv](https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/) county temperature, precipitation and drought; [USGS county water use 2015](https://www.sciencebase.gov/catalog/item/5af3311be4b0da30c1b245d8); [EIA-861 2024](https://www.eia.gov/electricity/data/eia861/) utility reliability and service territories; [NOAA Weather Radio](https://www.weather.gov/nwr/) transmitter and county coverage data
- News and alerts: BBC, Al Jazeera, NPR, The Guardian, DW and WHO RSS; [GDACS](https://www.gdacs.org/); USGS significant earthquakes; [NOAA SWPC](https://www.swpc.noaa.gov/); [NWS alerts](https://www.weather.gov/documentation/services-web-api)
- [USGS earthquake feed](https://earthquake.usgs.gov/earthquakes/feed/) and [NASA EONET](https://eonet.gsfc.nasa.gov/): live events
- [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (SRTM, GMTED, ETOPO1): elevation for the shaded relief
- [world-atlas](https://github.com/topojson/world-atlas) and [us-atlas](https://github.com/topojson/us-atlas): map boundaries (Natural Earth, US Census)
- [USGS ComCat](https://earthquake.usgs.gov/fdsnws/event/1/), [NOAA HURDAT2](https://www.nhc.noaa.gov/data/#hurdat), [Smithsonian GVP](https://volcano.si.edu/), Statistics Canada 2021 Census, INEGI 2020 Census: Canada and Mexico hazards and population
- [Open-Meteo](https://open-meteo.com/) (live winds) and [OSRM](https://project-osrm.org/) (road routes)
- [geoBoundaries](https://www.geoboundaries.org/): Canadian province (Statistics Canada Open Licence) and Mexican state boundaries
- Research behind the scenarios: Xia et al. 2022 (nuclear famine), Mastin et al. 2014 (Yellowstone ash), Love et al. 2018 (geoelectric hazards), FEMA 2019 National THIRA, NRC emergency planning zones

## Limits

Threat zones (nuclear targets, fallout, reactors, ash, fault zones, geomagnetic exposure) are simple distance models built from public sources, not simulations; real fallout depends on the weather that day. US grid reliability, water stress, growing season and climate trend are now measured per county (NOAA, USGS, EIA); the climate factor is the observed trend since 1951–80, not a projection. Alaska and Hawaii fall back to statewide estimates where NOAA has no county series. Canadian and Mexican earthquake, hurricane and volcano scores are measured from USGS, NOAA and Smithsonian catalogs and calibrated to FEMA's US scale; their other hazard and resource factors are still estimates per province or state; threat zones there are modeled from each area's main population center. Outside the US, hazard and resource data are national averages. Taiwan is estimated (INFORM does not cover it) and small territories borrow their governing country's scores. The Now tab sorts headlines by keyword, so some items will be off-topic. Use this to frame decisions, then check local sources before you move.
