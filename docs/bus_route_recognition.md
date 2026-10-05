# Bus route recognition

VisionNav reads text on a detected bus and, once the reading is stable, speaks the route. The phone speaks the backend sentence verbatim. It does not guess a direction, announce whether a service is running, or give boarding instructions.

Recognition reuses the existing EasyOCR reader, bus-only crop, six-frame OCR interval, ByteTrack identity, and 3-of-5 stability window. An OCR exception does not stop the frame.

## What is in the route database

`pipeline/bus_route/routes.json` keeps the existing Green Line and Orange Line records and adds the 22 feeder corridors from `docs/feeder_routes_source_snapshot_2026-10-05.json` (metro-status.com feeder dashboard, observed 2026-10-05).

Online/offline labels and advertised frequency are not stored and are not used for recognition. Every listed corridor is included.

Substation lists are copied only for the five corridors whose detail panel provided them: **FR-1**, **FR-3A**, **FR-4**, **FR-4A**, and **FR-7**. Order and duplicate names are preserved. The other 17 corridors have no substation list. Those stops were not invented.

Corridor endpoints come from the source titles. They are not replaced by the first or last substation. Destination spellings such as G-11 / G11, Aabpara / Abpara, Tramri / Tramari, Golra Mor / Golra Morh, and the source spellings of Barakahu are recognition aliases. They are not new verified routes. A stop in the middle of a list, such as G-9 Markaz, is not a destination.

## How a reading is chosen

Route codes use bounded patterns. `FR-7`, `FR7`, and `FR 7` match FR-7. `FR-8A`, `FR8A`, and `FR 8 A` match FR-8A. `EXP-16`, `EXP16`, and `EXP 16` match EXP-16. A shorter code is not taken from inside a longer one, so FR-10 is not FR-1.

`FR-04` and `FR-4` stay separate because their titles differ. `FR-04`, `FR04`, and `FR 04` mean FR-04. `FR-4` and `FR 4` mean FR-4. `FR4` alone is ambiguous and is not announced.

All OCR lines from the same bus crop are kept. A clear route code limits destination matching to that route. If the code is clear and the direction is not, the result is route-only:

- Confirmed code and destination: “Feeder route seven toward G-11.”
- Code without a direction: “Feeder route seven detected. Direction could not be read.”
- Suffixes are spoken separately: “Feeder route eight A”, “eight B”, and “eight C”.
- EXP-16 is “Express route sixteen”. FRG-01 is “Feeder route G zero one”.

A destination with no code is used only when that wording identifies one route and one direction in the combined database. PIMS, Barakahu, Tramri, Khanna Pul, and Golra Mor are shared, so they do not select a route. Seeing both ends of a corridor does not establish which way the bus is going. Conflicting codes, or a destination that cannot belong to the recognized code, produce no announcement.

Green Line and Orange Line announcements that still have unique evidence are unchanged. `PIMS HOSPITAL` and `BARAKAHU STOP` can still identify the Green Line. `N-5` and `Faiz Ahmad Faiz` can still identify the Orange Line. `BARAKAHU` by itself, and `GREEN` together with `PIMS`, are no longer enough.

FRG-01 is stored separately from the Green Line. The database does not treat them as the same service or as proven different services. Shared PIMS and Barakahu wording does not announce either one.

The same route code and direction must agree in 3 of the last 5 OCR reads before it is published. A route with no direction is its own stable state. A later confirmed direction can replace it and is spoken once. An old direction ages out of that window when later reads disagree. It is not kept forever.

## Unresolved source conflicts

These are preserved on purpose:

- FR-04 (PIMS ↔ Bari Imam) and FR-4 (PIMS ↔ Aiwan e Saddar) are different source entries. They are not merged.
- FR-3A’s stop list continues past Faisal Masjid to Said Pur Village.
- FR-7’s stop list continues past G-11 to Police Foundation Metro Station. It also includes Nust Metro Station, which is an endpoint name on FR-1.
- FR-4A’s stop list starts at Bari Imam, not at PIMS. The corridor remains PIMS ↔ QAU.
- FR-4 contains two overlapping stop sequences and no direction labels. Bari Imam is in that list and is not treated as FR-4’s destination.
- FR-1’s stop list is in the opposite order from its title, and Iqbal Town is duplicated.
- FR-8A and FR-8C both use Tramri. Tramri alone does not choose.
- Barakahu wording is shared by the Green Line, FR-14, FR-15, and FRG-01.
- Khanna Pul, Golra Mor, Taxila, and PIMS are each shared by more than one record.
- The snapshot was not checked against CDA or NRTC, and the site’s separate route guide was not merged in.

## Trying a real bus photo

From the repository root:

```bash
python tools/test_bus_route_ocr.py --image path/to/bus.jpg
python tools/test_bus_route_ocr.py --image path/to/bus.jpg --crop x,y,width,height
```

The first run may download EasyOCR’s English weights. The tool prints the OCR lines, the matched code, whether a direction is known, whether the reading is ambiguous, and the speech sentence. It uses the same matcher as the live pipeline and does not apply the 3-of-5 stability rule.

Unit tests feed mocked OCR text. They check the database, the matching rules, stability, and the spoken sentence. They do not measure how often real bus signs are read correctly.

Automated checks:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Flutter announcement and JSON parsing:

```bash
cd visionnav_app
flutter test test/announcement_manager_test.dart
```
