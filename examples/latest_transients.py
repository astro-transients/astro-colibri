"""
Search for the transients detected in a time window.

Setup:
    pip install astro-colibri
    export ASTROCOLIBRI_UID="your-user-id"    # shown at https://astro-colibri.com/account

Run:
    python examples/latest_transients.py
    python examples/latest_transients.py 2026-09-01T00:00:00Z 2026-09-02T00:00:00Z

Searches need your user ID and count against your daily API quota. Without
arguments the window is the previous full day in UTC. Bounds that stay put
between runs let the API answer a repeated search from its cache, at no
quota cost; a window ending at "now" is a new search every time.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from astrocolibri import (
    AstrocolibriAuthError,
    AstrocolibriError,
    AstrocolibriRateLimitError,
    Client,
)


def previous_utc_day():
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return today - timedelta(days=1), today


def main(start, end) -> int:
    with Client() as client:
        try:
            results = client.latest_transients(start=start, end=end)
        except AstrocolibriAuthError as error:
            # No user ID configured, or one the API does not recognise. The
            # message says which, and never contains the ID itself.
            print(error)
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

    events = results["voevents"]
    if not events:
        print("No transients in this time window.")
        return 0

    print(f"{len(events)} transient(s):")
    for event in events:
        print(
            f"Name: {event.get('source_name', 'N/A')}, "
            f"Type: {event.get('type', 'N/A')}, "
            f"Detection date/time: {event.get('time', 'N/A')}, "
            f"RA: {event.get('ra', 'N/A')}, "
            f"Dec: {event.get('dec', 'N/A')}, "
            f"Trigger ID: {event.get('trigger_id', 'N/A')}"
        )
    return 0


if __name__ == "__main__":
    window = (sys.argv[1], sys.argv[2]) if len(sys.argv) == 3 else previous_utc_day()
    sys.exit(main(*window))
