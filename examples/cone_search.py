"""
Search for transients around a sky position.

Setup:
    pip install astro-colibri
    export ASTROCOLIBRI_UID="your-user-id"    # shown at https://astro-colibri.com/account

Run:
    python examples/cone_search.py

Each run is one search, counted against your daily API quota.

Coordinates can be decimal degrees or sexagesimal strings, and the unit is
read from the notation, never from the size of the number. For the Crab
Nebula all of these are the same position:

    ra=83.6331,           dec=22.0145
    ra="05h34m31.94s",    dec="+22d00m52.2s"
    ra="05:34:31.94",     dec="+22:00:52.2"    (colons: hours for RA, degrees for Dec)

A radius of "30′" or "30'" is half a degree.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from astrocolibri import (
    AstrocolibriConfigError,
    AstrocolibriError,
    AstrocolibriRateLimitError,
    Client,
)


def main() -> int:
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=30)

    with Client() as client:
        try:
            results = client.cone_search(
                ra="05h34m31.94s",
                dec="+22d00m52.2s",
                radius=2,
                start=start,
                end=end,
            )
        except AstrocolibriConfigError as error:
            # A malformed coordinate is rejected before anything is sent, so
            # it costs no quota.
            print(f"Invalid search: {error}")
            return 1
        except AstrocolibriRateLimitError as error:
            renewal = error.reset_time or "an unreported time"
            print(
                f"Your daily API quota is used up. It renews at {renewal} (server time)."
            )
            return 1
        except AstrocolibriError as error:
            print(f"The search failed: {error}")
            return 1

    transients = results["voevents"]
    print(
        f"Transients within 2° of the Crab Nebula in the last 30 days: {len(transients)}"
    )
    for event in transients:
        print(
            f"  {event.get('time', 'N/A')}  {event.get('source_name', 'N/A')} ({event.get('type', 'N/A')})"
        )

    # Catalog matches are listed whatever their date: the time window only
    # applies to transients.
    catalog = results.get("sources", []) + results.get("Xsources", [])
    print(f"Catalog sources in the cone, regardless of date: {len(catalog)}")
    for source in catalog:
        print(f"  {source.get('source_name') or source.get('assoc') or 'unnamed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
