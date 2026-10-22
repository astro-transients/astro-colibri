"""
Listen to the broker and keep only the alerts that pass your filters.

Setup:
    pip install astro-colibri
    export ASTROCOLIBRI_UID="your-user-id"    # shown at https://astro-colibri.com/account
    Put your broker credentials (https://astro-colibri.com/broker) below.

Run:
    python examples/filter_stream.py                             # your app filters
    python examples/filter_stream.py Astro-COLIBRI_filters.json  # a filter file

Without an argument the script applies the filters saved in the
Astro-COLIBRI app for your account, fetched once at startup with your user ID
(one request against your daily API quota). With the path of a filter file,
such as the one the app's "Download Filters" button saves, it applies that
file instead and needs no user ID.

Filters give the same answer on the JSON and the VOEvent topics, so either
works below. Stop the script with Ctrl-C.
"""

from __future__ import annotations

import sys
from typing import Optional

from astrocolibri import (
    AstrocolibriError,
    AstrocolibriNotFoundError,
    Consumer,
    EventFilter,
)

USERNAME = "your_username"
PASSWORD = "your_password"
TOPICS = ["astrocolibri.all.JSON"]


def load_filter(filter_file: Optional[str]) -> EventFilter:
    if filter_file:
        return EventFilter.from_file(filter_file)
    return EventFilter.from_saved_filters()


def main(filter_file: Optional[str] = None, timeout: float = -1) -> int:
    try:
        event_filter = load_filter(filter_file)
    except AstrocolibriNotFoundError:
        print("No filters are saved for your account yet: set them up in the app.")
        return 1
    except (AstrocolibriError, OSError) as error:
        # A missing user ID, an unreadable file or an invalid filter. The
        # message says which, and never contains the user ID itself.
        print(f"Could not load the filter: {error}")
        return 1

    with Consumer(username=USERNAME, password=PASSWORD) as consumer:
        consumer.subscribe(TOPICS)
        print(f"Listening on {', '.join(TOPICS)} (Ctrl-C to stop)")
        try:
            for alert in consumer.consume(timeout=timeout, event_filter=event_filter):
                # The event as a dict, whether it came as JSON or as a VOEvent.
                event = alert.event()
                print(
                    f"{event.get('trigger_id')}  type={event.get('type')}  "
                    f"observatory={event.get('observatory')}  "
                    f"ra={event.get('ra')} dec={event.get('dec')}"
                )
        except KeyboardInterrupt:
            print("\nStopping.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
