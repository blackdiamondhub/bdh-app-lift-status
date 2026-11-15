# bdh-app-lift-status

Black Diamond Hub app: Sun Peaks lift and trail status. Moved out of
[BlackDiamondHub](https://github.com/blackdiamondlodge/BlackDiamondHub) and
installed into the hub through the `blackdiamondhub.plugins` entry point
(see [bdh-sdk](https://github.com/blackdiamondlodge/bdh-sdk)).

Page: `/lift_status/`. Shows the trail map, open/groomed summary rings,
Sun Peaks' daily operations update, lift hours, and trails per zone
(West Bowl is a section of Tod Mountain; scrolling to it switches the map).

## Container (hub API 2)

Since 2.0.0 the app runs in its own container: no broker permissions (it
uses no hub data), `network: outbound` (sunpeaksresort.com),
`lifecycle: on_demand`, `memory_mb: 96`. The hub pulls the status tile and
the `stats` and `season` providers from the container, waking it if it's
stopped. CI's `image` job (from bdh-sdk's `app-ci.yml`) locks the
dependencies against the hub's app runtime, builds the app's image and
smoke-tests it the way the supervisor runs it.

## Development

CI (`.github/workflows/ci.yml`) uses the reusable `app-ci.yml` from
bdh-sdk. It builds the wheel, installs it next to the hub, then runs
`hub_smoke`, the app tests and the selenium tests. CI also runs daily, because some tests hit the live site this app scrapes.

To release, bump `version` in `pyproject.toml`. When that lands on
`main`, `release.yml` tags it and publishes the wheel, and the release
notes include the hashed line for the hub's `sites/<site>/apps.txt`.
