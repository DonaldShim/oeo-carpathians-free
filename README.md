# OEO Карпати · Полісся 3.1 Free

Free-hosting profile of OEO for Render Free Web Service.

## What it does
- Ukrainian Carpathian AOI presets: Chornohora/Yaremche, Borzhava, Skole Beskids, Rakhiv/Marmarosy, Gorgany, Synevyr.
- Task modes: forest/windthrow, flood/water, fire/thermal anomaly, landslide/erosion screening.
- Live Sentinel-1 and Sentinel-2 metadata/footprints from Element 84 Earth Search.
- NISAR GCOV provisional metadata from NASA ASF.
- FIRMS VIIRS fire points when `FIRMS_MAP_KEY` is configured; degrades gracefully without it.
- Free EOX/OSM basemaps.
- No C-Lab VM heartbeat and no persistent server cache.

## Render
`render.yaml` is included. Choose Blueprint / Render web service, free plan.

Start command:
`uvicorn app:app --host 0.0.0.0 --port $PORT`

Health: `/health`

## Interpretation
New scenes are not automatically alerts. SAR change is not thermal data or GMTI/vehicle detection. The landslide mode is screening for structural change, not a geological diagnosis.
