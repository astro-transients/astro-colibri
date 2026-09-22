"""
Search for transients inside a gravitational-wave localization.

Setup:
    pip install astro-colibri
    export ASTROCOLIBRI_UID="your-user-id"    # shown at https://astro-colibri.com/account

Run:
    python examples/contour_search.py
    python examples/contour_search.py S230518h

Localizations of gravitational waves, Fermi/GBM and IPN bursts, IceCube
neutrinos and MAXI transients are far from circular. Passing an event's
trigger ID as contour_trigger_id searches inside its 90% localization contour
instead of a circle. If no contour is stored for the event, the API searches
the circle, and the result's "search_region" says which of the two was used.

Looking up the event is free; the search counts once against your quota.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from astrocolibri import (
    AstrocolibriError,
    AstrocolibriNotFoundError,
    AstrocolibriRateLimitError,
    Client,
)

FALLBACK_RADIUS = 15  # degrees; only searched when no contour is stored
MARGIN = 1.0  # degrees added around the contour


def main(trigger_id: str) -> int:
    with Client() as client:
        try:
            event = client.get_event(trigger_id)
            # Astro-COLIBRI event times are UTC, usually written without an offset.
            merger = datetime.fromisoformat(event["time"])
            if merger.tzinfo is None:
                merger = merger.replace(tzinfo=timezone.utc)

            results = client.cone_search(
                ra=event["ra"],
                dec=event["dec"],
                radius=FALLBACK_RADIUS,
                start=merger,
                end=merger + timedelta(days=7),
                contour_trigger_id=trigger_id,
                contour_margin=MARGIN,
            )
        except AstrocolibriNotFoundError:
            print(f"No event matches {trigger_id!r}.")
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

    if results.get("search_region") == "contour_90":
        print(f"Searched the 90% contour of {trigger_id}, widened by {MARGIN:g}°.")
    else:
        print(
            f"No contour is stored for {trigger_id}: searched a {FALLBACK_RADIUS}° circle "
            f"around its position instead."
        )

    transients = results["voevents"]
    print(
        f"Transients in the week after {merger:%Y-%m-%d %H:%M} UTC: {len(transients)}"
    )
    for transient in transients:
        print(
            f"  {transient.get('time', 'N/A')}  {transient.get('source_name', 'N/A')} "
            f"({transient.get('type', 'N/A')})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "S230518h"))
