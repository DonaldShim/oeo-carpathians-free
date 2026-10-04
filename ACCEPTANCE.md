# Free deployment acceptance

- `/health` => HTTP 200 and version `3.1.0-free`.
- Root UI => HTTP 200 and contains `OEO Карпати · Полісся 3.1`.
- `/api/config` => 6 Carpathian presets + 4 scenarios.
- `/api/v3/providers` => Earth Search, NASA ASF, FIRMS, GFW evidence mode.
- Carpathian replay: Sentinel-1/Sentinel-2 endpoints must return HTTP 200 or a provider error surfaced as an explicit response.
- NISAR endpoint must return HTTP 200 with results or `ok=false` reason; it must not crash the service.
- FIRMS without key => HTTP 200, `configured=false`.
- No server-side heartbeat that prevents Render free sleep.
