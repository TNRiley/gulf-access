# Rebuilding Gulf Access

## 1. What this is

One self-contained page that maps every residential canal on Florida's Gulf coast **from
lidar alone**, classifies each by the height of its water, and tests one published figure
against the result.

The finding: the City of Cape Coral states that its "freshwater canal system is comprised
of 300 miles of freshwater canals" (of a 400-mile system). The lidar finds 368 miles of canal
in the city and only **114 miles** of it stands more than 0.6 m above sea level. The Florida
DEP waterbody map, independently, classes **135 miles** of the same canals as fresh. The two
agree on 92% of the city's canal length. Neither can find the other half of the 300.

The page does not say the city is wrong. It says the figure cannot be reproduced, and that
the city does not publish how it counts.

## 2. Data

| source | URL | notes |
|---|---|---|
| USGS 3DEP 1 m DEM | `https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage` | `format=tiff&pixelType=F32&interpolation=RSP_NearestNeighbor&bboxSR=26917&imageSR=26917`, 2120 x 2120 px per request (10 km + 300 m collar at 5 m). About 9 s a tile alone, 2.5 s a tile with 8 workers. 512 tiles, 2.3 GB stored as int16 mm. Service max is 8000 x 8000. |
| OSM Florida | `https://download.geofabrik.de/north-america/us/florida-latest.osm.pbf` | 661 MB (the 2026-11-10 file). `with_locations()` is fine at this size. |
| DEP WBIDs | `https://ca.dep.state.fl.us/arcgis/rest/services/OpenData/WBIDS/MapServer/0/query` | 6,894 polygons, 1,000 a page, one page will 500 and succeed on retry. `WATER_TYPE` ESTUARY/COASTAL/BEACH is marine; STREAM/LAKE/SPRING is fresh. |
| Census places and counties | TIGERweb `Places_CouSub_ConCity_SubMCD/MapServer` layers 4 and 5; `State_County/MapServer/1` | 958 Florida places. |
| Cape Coral | `https://www.capecoral.gov/departments/utilities/water_reclamation.php` | the quoted sentence. The city's water quality page says "400-mile canal system". |

Things that will bite:

- **Overpass will not serve this.** The public endpoint returned 406 without a user agent and
  502 with one. Use the Geofabrik extract.
- **UTM 17N is used for the whole coast**, including the Panhandle, which is really zone 16.
  The distortion is under a fifth of a percent and one grid is worth it.
- **`getSamples` is slow** (about 25 points a second). Do not sample points; pull rasters.
- Tidal water in the DEM is **not the tide**. See section 3.

## 3. Method, and why

**Water is whatever is flat.** A USGS lidar DEM is hydro-flattened: the contractor draws a
breakline round each water body and sets the cells inside to one elevation. A pixel is water
if its 3 x 3 neighbourhood (15 m) has a range of 3 cm or less; the flat core is then grown
over neighbours within 3 cm of it.

**Then trenches at the same level.** Water under roughly 30 m wide is often not flattened.
Those canals read as a noisy trench (0.53, 0.61, 0.63 m between 3 m banks). A pixel also
counts if it is at least 1.2 m below the 95 m grey closing of the surface AND within 0.3 m of
the level of flattened water inside 800 m. The second condition is what keeps streets out.

**Skeleton, width, level, bank, ruler.** The mask is skeletonised; width is twice the
distance transform; pixels 7.5 to 110 m wide are "narrow". Level is the 7 x 7 minimum of the
3 x 3 median inside the mask. Bank is the mean land elevation in a 95 m box. Ruler is the
orientation coherence of the mask boundary in a 30 m Gaussian window.

**Pieces.** Skeleton pixels within 2 px of each other are joined across tiles on a global
5 m grid. A piece is kept if length >= 150 m, length/width >= 6, bank minus level >= 0.3 m.

**Residential** means half the piece's length is within 120 m of an OSM `highway=residential`
vertex (streets densified to 30 m). Pieces within 40 m of an OSM river or stream line for
half their length are set aside (329 km).

**Canal**, default rule: residential, and either a network of 2 km or more or ruled-straight
for half its length (ruler >= 0.75).

**Class.** Held: level above 0.6 m. At tide height: 0.6 m or below. The page splits the low
class by the DEP water type of the polygon the piece sits in, and shows "low but DEP says
fresh" as its own colour.

**Second freeboard measure.** Besides bank minus level, the DEM is sampled at the nearest
residential street vertex to each skeleton pixel. Never averaged with the first.

## 4. The page

Fraunces display, IBM Plex text. Blue for water at tide height, orange for held, violet for
disputed. Sections: the Cape Coral claim (three bars and a level histogram coloured by the
state's class); eight topographic plates (canvas, elevation tint, 1 m contours, hover readout);
the coast with a selectable canal rule that recomputes every table; freeboard; instruments;
methods. Every figure in the prose is a `data-v` span filled by script from the arrays.

`stats.py` recomputes the same figures in Python. Run it and compare.

## 5. Expected values

| check | value |
|---|---|
| tiles | 512 |
| narrow water of every kind in the tiles | 33,834 km |
| skeleton pixels | 5,904,189 |
| pieces passing the shape test | 17,360 (16,495 in Gulf counties) |
| residential narrow water, natural-labelled removed | 5,991 km |
| canal, default rule | 3,376 km: 1,793 tidal, 243 disputed, 1,340 held |
| lidar and DEP agree, coast-wide | 89% of canal length |
| share at tide height across the five rules | 48% to 72% |
| Cape Coral, residential narrow water | 623 km (387 mi; the city says 400 mi) |
| Cape Coral, canal by default rule | 593 km (368 mi) |
| Cape Coral, held above 0.6 m | 183 km (114 mi) |
| Cape Coral, DEP fresh | 217 km (135 mi) |
| Cape Coral, both say held and fresh / both say tide | 176 km / 369 km |
| Cape Coral, between 0.55 and 1.05 m | 15 km |
| Lehigh Acres / Golden Gate | 189 km / 53 km, none of it below 0.6 m |
| Marco Island | 76 km, all at tide height, 1% in OSM |
| Rotonda | 42 km, 41 of it below 0.6 m, DEP type STREAM |
| freeboard, tidal canals | 1.71 m by lots, 1.44 m by street (medians, length-weighted) |
| freeboard, held canals | 1.92 m by lots, 1.69 m by street |
| freeboard, unbuilt narrow water at tide height | 0.58 m |
| tiles with a sea reading / reading 0.00 m | 181 / 130 |
| highest held canal | 12.1 m (the detector ignores water above 12 m) |
| one test tile, Cape Coral (E 398-408 km, N 2941-2951 km) | about 225 km of canal |

A recognisable checkpoint: on the Cape Coral plate the south and west rim is blue, the centre
and north-east is orange, and the level histogram is empty between about 0.6 and 1.0 m.

## 6. Controls and what they showed

- **Length.** Cape Coral's 400 miles was the check on the detector: 387 miles found. Pass.
- **Two classifications.** Lidar level against DEP type: 89% agreement coast-wide, 92% in
  Cape Coral. The disagreements are informative both ways: Rotonda is fresh water held at
  0.17 to 0.45 m (the lidar's "low" is wrong about it), Apollo Beach is tidal and sits in a
  DEP STREAM polygon (the state's map is wrong about it).
- **Unbuilt creeks.** Bank-minus-level for narrow water with no residential street nearby:
  0.58 m at tide height against 1.71 m for canals. So the detector does not manufacture 1.7 m.
- **A correlation that was thrown out.** Level against bank height for held canals gives
  r = 0.97, slope 1.0. It gives r = 0.97 for wild water too. It is a property of water
  sitting in terrain and is not on the page as a finding.
- **Canal towns and lake suburbs.** The default rule keeps 87% of residential narrow water in
  twelve canal towns and 30% in ten lake suburbs (lists in `template.html`).

## 7. What failed, with the wrong answers

- **OSM as the geometry.** Canal centrelines: 446 km in Cape Coral, 24 km on Marco Island,
  0 in Apollo Beach, 42 km in Port Charlotte. NHD has the same hole: tidal finger canals are
  "coastline". Dropped.
- **Flat to 5 mm.** 141 km in the test tile. Narrow canals have a centimetre of slope.
- **Any trench 1.2 m deep.** 366 km in the test tile, and at 1.0 m, 590 km: it finds streets,
  because lots are filled above roads. The first version (0.6 m, with smoothing) found 953 km.
- **The ruler as the canal test.** Share of length in pieces at least half ruled: Cape Coral
  94%, Port Charlotte 96%, Golden Gate 99%, but Punta Gorda 6%, Hudson 19%, Marco Island 21%,
  Hernando Beach 1%. It would have deleted the tidal finger canals and biased every share.
- **Level <= 0.6 m means tidal.** Wrong for Rotonda and for 41 km of Cape Coral.
- **A coast-wide tidal share as the headline.** 48% to 72% by rule. Reported as a range.
- **Sea level from the DEM.** Open water reads exactly 0.00 m in 130 of 181 tiles: a
  contractor's constant. Canals inside towns were flattened individually at their stage on
  the day, anywhere from 0.00 to about 0.5 m, so "same level as the sea" does not work either.

## 8. What the page must say about itself

Only "held above 0.6 m" is certain. It does not count saltwater canals, says nothing about
whether a boat can reach the Gulf, excludes water wider than 110 m, misses canals under about
15 m wide, uses the stage on the day of the flight, leaves out Monroe County, and its metre
of difference between canal lots and creek banks is not all fill.
