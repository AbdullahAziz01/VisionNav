# CDA route audit report

Generated 2026-11-18 21:05 UTC.

Source of truth: [CDA Transit Map](https://www.cda.gov.pk/cdaTransitMap) and `CDA_ISLAMABAD_TRANSIT_SOURCE_CATALOG.md`.

Scheduled timetable values are not live bus ETAs. Coordinates in `transit_stops.json` are mapped gazetteer pins, not verified roadside platforms.

## Catalog coverage

- Catalog routes: **22**
- Routes with coverage rows: **22**
- Usable mapped directions in planner: **44**
- Mapped gazetteer stops: **224**


## Per-route status

### FR-01 (feeder)
- Direction listed as `FR-01 Backward` — status `available`; published stops 26; mapped stops 7; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-01_Backward.pdf
  - **Incomplete mapping:** 19 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-01 Forward` — status `available`; published stops 17; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-01_Forward.pdf
  - **Incomplete mapping:** 14 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Nust Metro Station` — 7 ordered mapped stops; 59.0 min avg gap from first mapped stop times.
- Planner direction toward `MCI Model School` — 3 ordered mapped stops; 60.0 min avg gap from first mapped stop times.

### FR-03A (feeder)
- Direction listed as `Saidpur Village - PIMS Hospital` — status `available_index_terminals`; published stops 14; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-03A_Backward.pdf
- Direction listed as `PIMS Hospital - Saidpur Village` — status `available_index_terminals`; published stops 14; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-03A_Forward.pdf
- Planner direction toward `PIMS Hospital` — 2 ordered mapped stops; 20.0 min avg gap from first mapped stop times.
- Planner direction toward `Saidpur Village` — 2 ordered mapped stops; 20.0 min avg gap from first mapped stop times.
- **Planning policy:** Index-over-PDF: planner uses CDA website endpoints PIMS–Saidpur Village (20 min). Conflicting PDF Faisal Masjid sequence is audit-only.

### FR-04 (feeder)
- Direction listed as `FR-04 Backward` — status `available`; published stops 25; mapped stops 20; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-04_Backward.pdf
  - **Incomplete mapping:** 5 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-04 Forward` — status `available`; published stops 25; mapped stops 20; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-04_Forward.pdf
  - **Incomplete mapping:** 5 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `PIMS Hospital` — 20 ordered mapped stops; 10.0 min avg gap from first mapped stop times.
- Planner direction toward `Bari Imam` — 20 ordered mapped stops; 10.0 min avg gap from first mapped stop times.

### FR-04A (feeder)
- Direction listed as `Quaid Azam University - Bari Imam` — status `available_index_terminals`; published stops 7; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-04A_Backward.pdf
- Direction listed as `Bari Imam - Quaid Azam University` — status `available_index_terminals`; published stops 7; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-04A_Forward.pdf
- Planner direction toward `Bari Imam` — 2 ordered mapped stops; 30.0 min avg gap from first mapped stop times.
- Planner direction toward `Quaid Azam University` — 2 ordered mapped stops; 30.0 min avg gap from first mapped stop times.
- **Planning policy:** Terminals-only: Bari Imam ↔ Quaid-e-Azam University.

### FR-04B (feeder)
- Direction listed as `PIMS Hospital - Diplomatic Enclave` — status `available_index_terminals`; published stops 2; mapped stops 2; source https://www.cda.gov.pk/cdaTransitMap
- Planner direction toward `Diplomatic Enclave` — 2 ordered mapped stops; no headway from departures.
- Planner direction toward `PIMS Hospital` — 2 ordered mapped stops; no headway from departures.
- **Planning policy:** Terminals-only: Diplomatic Enclave shuttle has no timetable PDF; navigate PIMS ↔ Diplomatic Enclave only, no fixed schedule.

### FR-05 (feeder)
- Direction listed as `Taxila - Golra Morh Metro Station` — status `available_index_terminals`; published stops 16; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-05_Backward.pdf
- Direction listed as `Golra Morh Metro Station - Taxila` — status `available_index_terminals`; published stops 16; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-05_Forward.pdf
- Planner direction toward `Golra Morh Metro Station` — 2 ordered mapped stops; 5.0 min avg gap from first mapped stop times.
- Planner direction toward `Taxila` — 2 ordered mapped stops; 5.0 min avg gap from first mapped stop times.
- **Planning policy:** Index-over-PDF: planner uses CDA website endpoints Golra Morh–Taxila (5 min). Conflicting PDF NUST–D-12 sequence is audit-only.

### FR-06 (feeder)
- Direction listed as `FR-06 Backward` — status `available`; published stops 26; mapped stops 6; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-06_Backward.pdf
  - **Incomplete mapping:** 20 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-06 Forward` — status `available`; published stops 26; mapped stops 6; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-06_Forward.pdf
  - **Incomplete mapping:** 20 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `PIMS Hospital` — 6 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Golra sharif` — 6 ordered mapped stops; 60.0 min avg gap from first mapped stop times.

### FR-07 (feeder)
- Direction listed as `FR-07 Backward` — status `available`; published stops 23; mapped stops 13; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-07_Backward.pdf
  - **Incomplete mapping:** 10 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-07 Forward` — status `available`; published stops 23; mapped stops 13; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-07_Forward.pdf
  - **Incomplete mapping:** 10 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `PIMS Hospital` — 13 ordered mapped stops; 10.2 min avg gap from first mapped stop times.
- Planner direction toward `Police Foundation Metro Station` — 13 ordered mapped stops; 10.0 min avg gap from first mapped stop times.

### FR-08A (feeder)
- Direction listed as `Capt. Naeem Tufail Shaheed Chowk - PIMS Hospital` — status `available_index_terminals`; published stops 23; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-08A_Backward.pdf
- Direction listed as `PIMS Hospital - Capt. Naeem Tufail Shaheed Chowk` — status `available_index_terminals`; published stops 23; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-08A_Forward.pdf
- Planner direction toward `PIMS Hospital` — 2 ordered mapped stops; 20.0 min avg gap from first mapped stop times.
- Planner direction toward `Capt. Naeem Tufail Shaheed Chowk` — 2 ordered mapped stops; 20.0 min avg gap from first mapped stop times.
- **Planning policy:** Index-over-PDF: planner uses CDA website 20 min headway and terminals PIMS–Capt. Naeem Tufail Shaheed Chowk; denser PDF headway ignored.

### FR-08C (feeder)
- Direction listed as `Capt. Naeem Tufail Shaheed Chowk - PIMS Hospital` — status `available_index_terminals`; published stops 23; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-08C_Backward.pdf
- Direction listed as `PIMS Hospital - Capt. Naeem Tufail Shaheed Chowk` — status `available_index_terminals`; published stops 23; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-08C_Forward.pdf
- Planner direction toward `PIMS Hospital` — 3 ordered mapped stops; 20.0 min avg gap from first mapped stop times.
- Planner direction toward `Capt. Naeem Tufail Shaheed Chowk` — 3 ordered mapped stops; 20.0 min avg gap from first mapped stop times.
- **Planning policy:** Terminals-only: PIMS ↔ Capt. Naeem Tufail Shaheed Chowk via Faizabad corridor.

### FR-09 (feeder)
- Direction listed as `FR-09 Backward` — status `available`; published stops 27; mapped stops 7; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-09_Backward.pdf
  - **Incomplete mapping:** 20 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-09 Forward` — status `available`; published stops 27; mapped stops 7; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-09_Forward.pdf
  - **Incomplete mapping:** 20 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Khanna Pul` — 7 ordered mapped stops; 15.0 min avg gap from first mapped stop times.
- Planner direction toward `Golra Morh Metro Station` — 7 ordered mapped stops; 15.0 min avg gap from first mapped stop times.

### FR-10 (feeder)
- Direction listed as `FR-10 Backward` — status `available`; published stops 25; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-10_Backward.pdf
  - **Incomplete mapping:** 22 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-10 Forward` — status `available`; published stops 25; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-10_Forward.pdf
  - **Incomplete mapping:** 22 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Golra Morh Metro Station` — 3 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Taxila` — 3 ordered mapped stops; 50.0 min avg gap from first mapped stop times.

### FR-11 (feeder)
- Direction listed as `I-16 - Golra Morh Metro Station` — status `available_index_terminals`; published stops 11; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-11_Backward.pdf
- Direction listed as `Golra Morh Metro Station - I-16` — status `available_index_terminals`; published stops 11; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-11_Forward.pdf
- Planner direction toward `Golra Morh Metro Station` — 2 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Rafiullah Shaheed Chowk` — 2 ordered mapped stops; 53.3 min avg gap from first mapped stop times.
- **Planning policy:** Terminals-only: Golra Morh ↔ I-16.

### FR-12 (feeder)
- Direction listed as `FR-12 Backward` — status `available`; published stops 25; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-12_Backward.pdf
  - **Incomplete mapping:** 23 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-12 Forward` — status `available`; published stops 25; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-12_Forward.pdf
  - **Incomplete mapping:** 23 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Taxila Chowk` — 2 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Tipu Sultan Shaheed Chowk` — 2 ordered mapped stops; 60.0 min avg gap from first mapped stop times.

### FR-13 (feeder)
- Direction listed as `FR-13 Backward` — status `available`; published stops 29; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-13_Backward.pdf
  - **Incomplete mapping:** 26 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-13 Forward` — status `available`; published stops 29; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-13_Forward.pdf
  - **Incomplete mapping:** 26 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Golra Morh Metro Station` — 3 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Fateh Jang` — 3 ordered mapped stops; 60.0 min avg gap from first mapped stop times.

### FR-14 (feeder)
- Direction listed as `FR-14 Backward` — status `available`; published stops 17; mapped stops 4; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-14_Backward.pdf
  - **Incomplete mapping:** 13 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-14 Forward` — status `available`; published stops 19; mapped stops 4; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-14_Forward.pdf
  - **Incomplete mapping:** 15 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Barahkahu` — 4 ordered mapped stops; 15.0 min avg gap from first mapped stop times.
- Planner direction toward `Mandi Morh` — 4 ordered mapped stops; 15.0 min avg gap from first mapped stop times.

### FR-14A (feeder)
- Direction listed as `Satra Meel - Barakahu` — status `available_index_terminals`; published stops 16; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-14A_Backward.pdf
- Direction listed as `Barakahu - Satra Meel` — status `available_index_terminals`; published stops 15; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-14A_Forward.pdf
- Planner direction toward `Barakahu Terminal` — 2 ordered mapped stops; 15.0 min avg gap from first mapped stop times.
- Planner direction toward `Satra Meel` — 2 ordered mapped stops; 15.0 min avg gap from first mapped stop times.
- **Planning policy:** Terminals-only: Barakahu ↔ Satra Meel.

### FR-15 (feeder)
- Direction listed as `FR-15 Backward` — status `available`; published stops 16; mapped stops 4; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-15_Backward.pdf
  - **Incomplete mapping:** 12 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FR-15 Forward` — status `available`; published stops 16; mapped stops 4; source https://www.cda.gov.pk/Assets/metro_transit_route/FR-15_Forward.pdf
  - **Incomplete mapping:** 12 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `Khanna Pul` — 4 ordered mapped stops; 29.4 min avg gap from first mapped stop times.
- Planner direction toward `T- Chowk` — 4 ordered mapped stops; 30.0 min avg gap from first mapped stop times.

### FRB-01 (blue_labeled_feeder)
- Direction listed as `FRB-01 Backward` — status `available`; published stops 17; mapped stops 6; source https://www.cda.gov.pk/Assets/metro_transit_route/FRB-01_Backward.pdf
  - **Incomplete mapping:** 11 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FRB-01 Forward` — status `available`; published stops 15; mapped stops 6; source https://www.cda.gov.pk/Assets/metro_transit_route/FRB-01_Forward.pdf
  - **Incomplete mapping:** 9 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `PIMS` — 6 ordered mapped stops; 5.0 min avg gap from first mapped stop times.
- Planner direction toward `Gulberg` — 6 ordered mapped stops; 5.0 min avg gap from first mapped stop times.

### FRG-1 (green_labeled_feeder)
- Direction listed as `FRG-1 Backward` — status `available`; published stops 12; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FRG-1_Backward.pdf
  - **Incomplete mapping:** 9 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `FRG-1 Forward` — status `available`; published stops 10; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/FRG-1_Forward.pdf
  - **Incomplete mapping:** 7 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `PIMS` — 3 ordered mapped stops; 5.0 min avg gap from first mapped stop times.
- Planner direction toward `Barakahu` — 3 ordered mapped stops; 5.0 min avg gap from first mapped stop times.

### ST-01 (sightseeing)
- Direction listed as `ST-01 Backward` — status `available`; published stops 14; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/ST-01_Backward.pdf
  - **Incomplete mapping:** 11 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Direction listed as `ST-01 Forward` — status `available`; published stops 13; mapped stops 3; source https://www.cda.gov.pk/Assets/metro_transit_route/ST-01_Forward.pdf
  - **Incomplete mapping:** 10 published stop name(s) lack a unique gazetteer match and are omitted from the ordered planner sequence.
- Planner direction toward `PIMS Hospital` — 3 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Daman e Koh` — 3 ordered mapped stops; 60.0 min avg gap from first mapped stop times.

### ST-02 (sightseeing)
- Direction listed as `Capt. Naeem Tufail Shaheed Chowk - PIMS Hospital` — status `available_index_terminals`; published stops 23; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/ST-02_Backward.pdf
- Direction listed as `PIMS Hospital - Capt. Naeem Tufail Shaheed Chowk` — status `available_index_terminals`; published stops 20; mapped stops 2; source https://www.cda.gov.pk/Assets/metro_transit_route/ST-02_Forward.pdf
- Planner direction toward `PIMS` — 2 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- Planner direction toward `Capt. Naeem Tufail Shaheed Chowk` — 2 ordered mapped stops; 60.0 min avg gap from first mapped stop times.
- **Planning policy:** Terminals-only: PIMS ↔ Capt. Naeem Tufail Shaheed Chowk via Shakarparian.

## Mapping gaps / terminals-only routes

Where mid-stop pins are missing, the planner still offers **terminals-only** boarding and exit navigation (start or end depending on trip direction). Where the CDA website index conflicts with a PDF, the **index endpoints win**.

- None: every catalog route has at least terminals-only planner coverage.

## Live timing note

CDA timetable PDFs provide **scheduled** arrival/departure times only. The CDA Metro mobile app advertises real-time arrivals, but VisionNav has no authoritative developer feed. The app must continue to speak **scheduled wait / next listed departure** at trip offer and at boarding-stop arrival, clearly labeled as schedule-based, never as live GPS bus ETA.

## Opposite-direction rule

Each forward and backward PDF is a separate ordered route. Presence of a stop on one direction does not prove service in the other direction.

