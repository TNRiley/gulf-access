# 🛥️ Gulf Access

**Cape Coral says it has 300 miles of freshwater canal; one-metre lidar finds 368 miles of canal in the city with only 114 of them standing above the tide, and the state's own waterbody map counts 135 as fresh.**

→ **[Open it](https://tnriley.github.io/gulf-access/)**

Every residential canal on Florida's Gulf coast, found without a map: 512 ten-kilometre tiles of USGS lidar across 22 counties, searched for narrow flat water with houses on it and sorted by how high the water stands. It finds 3,376 km of canal, 1,340 km of it held more than 0.6 m above the sea behind weirs, and draws eight canal towns as topographic plates with the water coloured by class. Cape Coral's published 300 miles of freshwater canal cannot be recovered from the ground or from the state's map, which agree with each other on 92% of the city. OpenStreetMap, the first choice for the geometry, turned out to hold a centreline for a third of these canals and 1% of Marco Island's, and the coast-wide share of canal at tide height moves from 48% to 72% with the definition of a canal, so the page reports it as a range.

## Running it

One self-contained HTML file. No build step, no server, no network access at runtime — open `index.html` in a browser, or serve the directory with any static host.

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## Rebuilding it from scratch

[REBUILD.md](REBUILD.md) is written for an LLM with a shell and nothing else: the data sources and their quirks, the processing decisions, the page's structure and interactions, and a table of expected values to check the result against.

## Source

The full build pipeline is in [`src/`](src/), with a README describing how to regenerate the page from scratch.

## Data

- **[USGS 3D Elevation Program 1 m lidar DEM, read through The National Map 3DEPElevation image service (512 tiles of 10 km at 5 m, downloaded 2026-11-11)](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer)** — US Government work, public domain
- **[OpenStreetMap, Florida extract from Geofabrik (florida-261110.osm.pbf, 661 MB): residential streets, river and stream labels, canal lines and coastline. © OpenStreetMap contributors.](https://download.geofabrik.de/north-america/us/florida.html)** — ODbL 1.0
- **[Florida DEP Waterbody IDs (WBIDs), 6,894 assessment polygons with water type](https://ca.dep.state.fl.us/arcgis/rest/services/OpenData/WBIDS/MapServer/0)** — Florida public record, credit FDEP Division of Environmental Assessment and Restoration
- **[US Census Bureau TIGERweb county and place boundaries](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb)** — US Government work, public domain
- **[City of Cape Coral, Utilities, Water Reclamation page (the quoted 300 miles of freshwater canals), read 2026-11-11](https://www.capecoral.gov/departments/utilities/water_reclamation.php)** — quoted figure only

Every figure on the page is computed from the data shipped with it. Check the page's own methods panel for how each number is derived and where it should not be pushed.

## Built with

Python, NumPy and SciPy image morphology, scikit-image skeletons, pyosmium, Shapely, vanilla JS, canvas, gzip + base64 payload.

## Licence

Code is MIT (see [LICENSE](LICENSE)). Data keeps the licence of its source, listed above.

---

Part of [Quick Projects](https://github.com/TNRiley/quick-projects) — one self-contained thing, built in one session. First published 2026-11-11.
