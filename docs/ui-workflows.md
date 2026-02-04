# Web UI workflows (demo)

## Quick demo flow
1) Open the web UI and confirm the map loads for the default city.
2) Toggle map layers (River, Pipes, Gauges, Hotspots) to show data richness.
3) Use tag filters (e.g., `basin:basin_ne, neighborhood:neighborhood_1_2`) to scope assets.
4) Click a hotspot pipe on the map to open its telemetry chart.
5) Change the time range to show recent vs. 7-day telemetry history.
6) Review the Events card for recent rain/overflow events in the same range.

## Validation checklist
- Map renders without console errors.
- Layer toggles work and legend matches colors.
- Asset detail card updates when clicking a map feature.
- Telemetry chart loads for the selected asset.
- Events list updates when changing range or type.
- Error banner appears for API failures and clears on refresh.
