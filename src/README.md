# src - the Gulf Access pipeline

Nothing here needs an API key. Raw downloads go under `raw/` (about 3.5 GB, not committed).
On Windows the interpreter is `python`, not `python3`.

```bash
pip install numpy scipy scikit-image shapely pyproj tifffile osmium

mkdir -p raw
curl -L -o raw/florida-261110.osm.pbf https://download.geofabrik.de/north-america/us/florida-latest.osm.pbf
curl -o raw/fl_counties.geojson "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query?where=STATE%3D%2712%27&outFields=NAME,GEOID&outSR=4326&maxAllowableOffset=0.0005&geometryPrecision=4&f=geojson"

python extract.py raw/florida-261110.osm.pbf   # raw/osm_extract.pkl        ~3 min
python fetch_wbid.py        # raw/wbid.geojson, 6,894 DEP polygons          ~1 min
python fetch_places.py      # raw/fl_places.geojson, 958 Census places      ~1 min
python pick_tiles.py        # raw/tiles.json, 512 tiles
python fetch_dem.py         # raw/dem/*.npz, 2.3 GB                         ~25 min
python process_tiles.py     # raw/skel/*.npz                                ~8 min
python analyse.py           # raw/components.npz, raw/pixels.npz            ~3 min
python build_payload.py     # payload.json (23 MB)
python stats.py             # stats.json: the numbers the page should show
python inject.py            # ../index.html, wrapped and breadcrumbed
```

| file | what it does |
|---|---|
| `extract.py` | residential streets, canals, rivers, coastline out of the OSM extract |
| `fetch_wbid.py`, `fetch_places.py` | the state's waterbody polygons; Census place boundaries |
| `pick_tiles.py` | which 10 km tiles: Gulf counties with at least ~9 km of residential street |
| `fetch_dem.py` | the lidar surface, 5 m pixels, from the USGS image service |
| `canalmap.py` | the detector: flat water, trenches at its level, skeleton, width, level, bank, ruler |
| `process_tiles.py` | runs the detector over every tile |
| `analyse.py` | joins skeleton pixels into pieces, applies the residential test, joins county, place and DEP class |
| `plates.py` | cuts the eight map plates |
| `build_payload.py`, `stats.py`, `inject.py` | payload, the check on the page's numbers, the page |

The reasoning, the traps and the expected values are in `../REBUILD.md`.
