# bdh-app-lift-status

Black Diamond Hub app: Sun Peaks lift and trail status. Moved out of
[BlackDiamondHub](https://github.com/blackdiamondhub/BlackDiamondHub) and
installed into the hub through the `blackdiamondhub.plugins` entry point
(see [bdh-sdk](https://github.com/blackdiamondhub/bdh-sdk)).

Page: `/lift_status/`. Shows the trail map, open/groomed summary rings,
Sun Peaks' daily operations update, lift hours, and trails per zone
(West Bowl is a section of Tod Mountain; scrolling to it switches the map).

## Assistant tools

The hub's assistant (e.g. the voice app) can look up lifts and runs through two read-only tools,
offered in every mode (guest, dashboard and owner). The hub only offers them when `lift_status`
is in its `assistant_apps` setting (Settings > Location > Assistant).

| Tool | Params | Answers |
|---|---|---|
| `lift_status` | `lift` (optional, the guest's words: "crystal", "the sunburst chair") | Without `lift`: lifts open ("5 of 13"), the open lifts with when they close, the closed lifts, runs open and the resort's operations update. With `lift`: its status ("open until 4 pm", "opens at 9:30 am", "closed for the day at 4 pm", "closed") and today's hours |
| `run_status` | `run` (optional, loose name) and/or `area` (Mt. Morrisey, Sundance, Tod Mountain, Orient Ridge, West Bowl) | Without `run`: runs open, the groomed runs (first 15, then a count) and open runs per area, or for one area its groomed and open-but-ungroomed runs. With `run`: its area, status and grooming, and difficulty |

Lift and run names are matched loosely (case, filler words like "the" and "chair", number words,
misheard words such as "kristal" or "burr field"). A name several lifts share ("Morrisey", "carpet")
answers with each of them under `matches`, unless "chair" or "express" picks the chairlift; an
unknown name ("gondola") fails with the list of real lifts. Hours are the schedule in effect today
(a "starting February 1" line takes over on that date), and the open/closed wording uses lodge
time (UTC-7 all year). When the resort page can't be fetched, or lists no lifts (between
seasons), the tool fails with a short sentence the assistant can say.

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
