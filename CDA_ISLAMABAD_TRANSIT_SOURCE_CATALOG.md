# Islamabad CDA Transit Route Source Catalog

Prepared 18 November 2026 for use as a source pack when updating VisionNav's route and stop data.

## Scope and source of truth

This catalog assumes the requested network is Islamabad's Capital Development Authority (CDA) transit network. CDA currently publishes 22 route labels on its [Transit Map of Islamabad](https://www.cda.gov.pk/cdaTransitMap): 18 routes with `FR-` labels, the `FRB-01` and `FRG-1` routes, and two sightseeing routes `ST-01` and `ST-02`.

The CDA route page lists route names, both directions, and published headways. The direction-specific PDF links below contain stop-by-stop scheduled arrival and departure times for the trips in that PDF. Use the PDFs to build direction-specific stop sequences and schedules when they agree with the website index. **If the linked PDF conflicts with the CDA website index endpoints or headway, VisionNav keeps the website index and treats the route as terminals-only (start/end navigation).** Routes with no mid-stop pins also use terminals-only guidance. These are scheduled timetable values, not live bus ETAs.

The linked timetable files are live URLs hosted by CDA. If a link is unavailable, check the CDA route page for its current replacement. `FR-04B` is listed by CDA but the detail link did not resolve to a usable timetable PDF when this catalog was prepared.

## Routes, headways, and complete timetable links

`F` means the CDA page's Forward timetable; `B` means its Backward timetable. Open the PDF for the complete stop list and each trip's scheduled times.

| Route | CDA-listed endpoints | Published headway | Complete stop/timing PDFs |
|---|---|---:|---|
| FR-01 | NUST Metro Station – Khanna Pul | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-01_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-01_Backward.pdf) |
| FR-03A | PIMS – Saidpur Village | 20 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-03A_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-03A_Backward.pdf) |
| FR-04 | PIMS – Bari Imam | 10 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-04_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-04_Backward.pdf) |
| FR-04A | Bari Imam – Quaid-e-Azam University | 30 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-04A_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-04A_Backward.pdf) |
| FR-04B | Diplomatic Enclave Shuttle Service | Random / no fixed headway | [CDA route listing](https://www.cda.gov.pk/cdaTransitMap); no usable timetable PDF found |
| FR-05 | Golra Morh – Taxila | 5 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-05_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-05_Backward.pdf) |
| FR-06 | PIMS – Golra Sharif | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-06_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-06_Backward.pdf) |
| FR-07 | PIMS – Police Foundation Metro Station | 10 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-07_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-07_Backward.pdf) |
| FR-08A | PIMS – Capt. Naeem Tufail Shaheed Chowk via Abpara | 20 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-08A_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-08A_Backward.pdf) |
| FR-08C | PIMS – Capt. Naeem Tufail Shaheed Chowk via Faizabad | 20 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-08C_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-08C_Backward.pdf) |
| FR-09 | Khanna Pul – Golra Morh Metro Station | 15 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-09_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-09_Backward.pdf) |
| FR-10 | Golra Morh Metro Station – Taxila | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-10_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-10_Backward.pdf) |
| FR-11 | Golra Morh Metro Station – I-16 | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-11_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-11_Backward.pdf) |
| FR-12 | Taxila – Hassan Abdal | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-12_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-12_Backward.pdf) |
| FR-13 | Golra Morh Metro Station – Fateh Jang | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-13_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-13_Backward.pdf) |
| FR-14 | Barakahu – Mandi Morh | 15 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-14_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-14_Backward.pdf) |
| FR-14A | Barakahu – Satra Meel | 15 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-14A_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-14A_Backward.pdf) |
| FR-15 | Khanna Pul – T-Chowk | 30 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FR-15_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FR-15_Backward.pdf) |
| FRB-01 (Blue-labeled CDA route) | PIMS – Gulberg | 5 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FRB-01_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FRB-01_Backward.pdf) |
| FRG-1 (Green-labeled CDA route) | PIMS – Barakahu | 5 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/FRG-1_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/FRG-1_Backward.pdf) |
| ST-01 (sightseeing) | PIMS – Daman-e-Koh | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/ST-01_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/ST-01_Backward.pdf) |
| ST-02 (sightseeing) | PIMS – Capt. Naeem Tufail Shaheed Chowk via Shakarparian Park | 60 min | [F](https://www.cda.gov.pk/Assets/metro_transit_route/ST-02_Forward.pdf) · [B](https://www.cda.gov.pk/Assets/metro_transit_route/ST-02_Backward.pdf) |

## Important data conflicts to resolve before importing

Do not treat the route-page summary as a fully validated route graph. CDA's own route index and its timetable PDFs conflict for some routes:

- **FR-03A:** the index calls it PIMS–Saidpur Village, headway 20 minutes. The linked timetable's title says PIMS Hospital–Faisal Masjid; its stop sequence includes Shaheen Chowk and ends at Flower Market, and its listed departures appear every 10 minutes. Saidpur Village is not in that PDF's stop sequence. Compare [CDA index](https://www.cda.gov.pk/cdaTransitMap) and [FR-03A Forward PDF](https://www.cda.gov.pk/Assets/metro_transit_route/FR-03A_Forward.pdf).
- **FR-05:** the route index and PDF header say Golra Morh–Taxila, but the Forward PDF's actual stop sequence starts at NUST Metro Station and ends at D-12. Do not silently assign the header endpoints to that stop sequence. Compare [CDA index](https://www.cda.gov.pk/cdaTransitMap) and [FR-05 Forward PDF](https://www.cda.gov.pk/Assets/metro_transit_route/FR-05_Forward.pdf).
- **FR-08A:** index headway is 20 minutes, while the Forward PDF advertises an average headway around 5 minutes. Treat as unresolved pending CDA confirmation.
- **FR-04B:** listed as a shuttle with random service, but no usable detailed stop/timetable file is linked.

The timetable PDFs provide scheduled times; they do not by themselves confirm actual current service, service disruptions, vehicle location, a live ETA, electric vehicle identity, or which side of a divided road is the accessible boarding platform.

## Useful example for VisionNav route tests

The [FR-07 Forward PDF](https://www.cda.gov.pk/Assets/metro_transit_route/FR-07_Forward.pdf) is the PIMS-to-Police-Foundation direction and its stop table includes the corridor through G-8/G-9/G-10/G-11. Use both FR-07 direction PDFs when testing journeys so the planner must distinguish toward PIMS from toward Police Foundation. Confirm the actual stop coordinates and curb/platform sides separately; the timetable alone does not encode safe sidewalk access.

## Other live/current sources

- [CDA Transit Map and route-index page](https://www.cda.gov.pk/cdaTransitMap) — current route list, direction names, headways, and PDF links.
- [CDA Transit Map PDF](https://cda.gov.pk/public/Assets/pdf/Transit-Map-Islamabad-V-07.pdf) — network map.
- [CDA Metro App on Google Play](https://play.google.com/store/apps/details?id=com.kentkart.cdamobile) — CDA app listing advertises real-time bus arrivals and trip planning. This is not a developer API and does not establish that VisionNav can access the feed.
- [CDA Mobile App terms](https://www.cda.gov.pk/termsAndConditions) — official app/service terms.

## Instructions for Cursor

Use this catalog and its CDA links to inspect the official timetable PDFs and update VisionNav's transit data. Preserve each direction as its own ordered stop sequence. For every stop store its source and verification status; do not infer stop coordinates or roadside platform from the timetable text. Preserve scheduled arrival/departure times and trips separately from headway summaries; do not present static schedule values as live ETA.

Before committing route data, report the discrepancies above and reconcile them rather than choosing whichever version looks convenient. Add regression tests for G-11 to PIMS, G-11 to Karachi Company, opposite-direction rejection, nearby valid stops and the 2 km confirmation threshold, and transfers only where a shared, verified stop and compatible scheduled service exist. Do not claim live arrivals, electric vehicle subtype, or safe curb-side boarding unless a suitable authoritative data source verifies it.

## Rebuild and audit commands

```bash
# From repo root, with venv activated and pypdf + beautifulsoup4 installed:
python tools/build_direct_bus_routes.py --cache tmp/cda_pdfs
python tools/audit_cda_routes.py --cache tmp/cda_pdfs
```

Latest human-readable audit: [`docs/cda_route_audit_report.md`](docs/cda_route_audit_report.md). Conflicting routes remain in `coverage` as `unverified_conflict` and are **not** imported into planner `directions` until CDA confirms which document is authoritative.
