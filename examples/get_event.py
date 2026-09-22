"""
Look up one event by trigger ID or name.

Run:
    python examples/get_event.py "GRB 190829A"
    python examples/get_event.py 922968

Event lookups need no user ID and do not count against your API quota.

A name can match several events. GRB 190829A, for instance, was localized
by both Fermi/GBM and Swift/XRT, and a lookup by name returns only one of
them, not necessarily the best. To list them all and follow the best
localization, run examples/resolve_source.py instead.
"""

from __future__ import annotations

import sys

from astrocolibri import AstrocolibriError, AstrocolibriNotFoundError, Client


def shown(event, key):
    # Fields the source does not provide come back empty rather than missing.
    value = event.get(key)
    return "N/A" if value in (None, "") else value


def main(identifier: str) -> int:
    with Client() as client:
        try:
            event = client.get_event(identifier)
        except AstrocolibriNotFoundError:
            print(f"No event matches {identifier!r}.")
            return 1
        except AstrocolibriError as error:
            print(f"The lookup failed: {error}")
            return 1

    print(f"Trigger ID   {shown(event, 'trigger_id')}")
    print(f"Source name  {shown(event, 'source_name')}")
    print(f"Type         {shown(event, 'type')}")
    print(
        f"Observatory  {shown(event, 'observatory')} {event.get('instrument') or ''}".rstrip()
    )
    print(f"Time         {shown(event, 'time')}")
    print(
        f"Position     RA {shown(event, 'ra')}°, Dec {shown(event, 'dec')}°, "
        f"uncertainty {shown(event, 'err')}°"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "GRB 190829A"))
