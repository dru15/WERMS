# India pilot: source and integration notes

Verified against primary sources on 17 October 2026. This note motivates a Dehradun, Uttarakhand research pilot; it does not establish operational readiness or government endorsement.

## Why Uttarakhand and Dehradun

FSI's *India State of Forest Report 2023*, Volume 2, Table 10.28.11 records 705 SNPP-VIIRS detections for Dehradun during 2023–24, compared with 230 in 2022–23. Uttarakhand totals are 21,033 and 5,351 respectively. The table explicitly includes large, continuous and repeated fires: these are **satellite detections, not counts of unique incidents or present-day active fires**. [FSI, Uttarakhand chapter](https://fsi.nic.in/uploads/isfr2023/isfr_book_eng-vol-2_2023.pdf)

An IIRS/ISRO article describes Uttarakhand's recurring fire season from approximately mid-February to mid-June and discusses dry conditions and rising temperatures. Its 2024 case study supports weather context as relevant background; it does not validate a fire-spread predictor for this application. [IIRS, 26 April 2024](https://science.iirs.gov.in/satellite-based-observations-of-forest-fires-2024-in-uttarakhand/)

FSI operates a separate forest-fire portal with near-real-time and large-fire monitoring. WERMS does **not** consume that portal, FSI alerts or NDMA feeds. Linking a public source must never be presented as integration or affiliation. [FSI forest-fire portal](https://fsiforestfire.gov.in/)

## Open-Meteo contract

- Request `current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation` at the pilot centre. Explicit units: Celsius, km/h, millimetres; humidity is percent and direction degrees. [Forecast API](https://open-meteo.com/en/docs)
- Current values are **model-derived**, based on 15-minute data. For regions outside Central Europe/North America, 15-minute data are interpolated from hourly data. They are not local weather-station observations. [Forecast API](https://open-meteo.com/en/docs)
- Use `timeformat=unixtime&timezone=Asia/Kolkata`; timestamps then represent UTC epoch seconds. `current.time` is validity time; `current.interval` is the aggregation duration in seconds, so precipitation covers the preceding interval. Returned grid coordinates can differ from requested coordinates. `generationtime_ms` measures response computation, not model issuance. [Forecast API](https://open-meteo.com/en/docs)
- Data are CC BY 4.0; show linked Open-Meteo attribution. [Licence](https://open-meteo.com/en/licence)
- Free hosted service is for non-commercial use, below 10,000 calls/day, 5,000/hour and 600/minute, with 300,000/month shown in its plan table. Commercial products require an appropriate paid service arrangement; a data licence does not waive hosted-service terms. [Terms](https://open-meteo.com/en/terms)

Suggested request: [Dehradun current model weather](https://api.open-meteo.com/v1/forecast?latitude=30.335&longitude=78.02&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm&timeformat=unixtime&timezone=Asia%2FKolkata&forecast_days=1). The coordinate is an application-selected pilot reference, not a named weather station.

## Implementation decisions

These are design choices, rather than claims made by the sources:

- Fetch centrally for one fixed pilot coordinate and cache for ten minutes. Bound response size, timeout requests, and retain a retrieval timestamp separately from weather validity time.
- Show “Model weather context”, provider attribution, validity time in IST and stale/unavailable states. Never fabricate replacement readings or silently display old values as current.
- Keep weather display separate from route safety scoring. A hand-written combination of humidity, wind and temperature must not become a claimed fire probability or official warning.
- Keep road closures, assembly capacities and incidents explicitly operator-entered or demonstrative. OpenStreetMap landmarks do not establish authorised shelters or their capacity.
- Make the resilience lab a repeatable **what-if route comparison**: baseline versus simulated blocked roads and shelter unavailability, with distance, ETA and reachability changes. Simulations must not alter actual bookings or closures.
- Demonstrate provenance, versioned graph data, role permissions, transactional reservations and deterministic scenario results in interviews. Do not describe the project as trained ML, fire detection, validated evacuation advice, or patented technology.

No emergency number is embedded by this research task; the application remains a research decision-support demonstrator.
