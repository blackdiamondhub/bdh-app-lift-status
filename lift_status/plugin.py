from bdh_sdk import PluginSpec, Tile
from bdh_sdk.plugins import LIFECYCLE_ON_DEMAND, NETWORK_OUTBOUND
from bdh_sdk.provides import SEASON, STATS

STAT_KEYS = (
    ("runs_open", "Runs open"),
    ("lifts_open", "Lifts open"),
    ("groomed", "Runs groomed"),
)

spec = PluginSpec(
    id="lift_status",
    app="lift_status",
    urls="lift_status.urls",
    status="lift_status.homepage.status",
    provides={STATS: "lift_status.provides.stats", SEASON: "lift_status.provides.season"},
    stat_keys=STAT_KEYS,
    # Read-only lift and run lookups for the hub's assistant, in every mode.
    tools="lift_status.assistant.tools",
    run_tool="lift_status.assistant.run_tool",
    tiles=(
        Tile(
            title="Lift Status",
            url_name="lift_status",
            icon="lift_status/hub/icon.svg",
            section="mountain",
            subtitle="Which lifts are running",
            order=20,
        ),
    ),
    api_version=2,
    # No hub data: the lifts and trails are Sun Peaks'.
    permissions=(),
    # Scrapes sunpeaksresort.com.
    network=NETWORK_OUTBOUND,
    # Status is scraped on request and cached; the hub's status/stats/season
    # hooks wake the app when it's stopped.
    lifecycle=LIFECYCLE_ON_DEMAND,
    memory_mb=96,
)
