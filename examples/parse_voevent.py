"""
Parse a VOEvent document: an Astro-COLIBRI event, or any VOEvent XML file.

Run:
    python examples/parse_voevent.py "GRB 190829A"
    python examples/parse_voevent.py path/to/notice.xml

Given an event name or trigger ID, the script downloads the event as a
VOEvent from the API, which needs no user ID and costs no quota. Given the
path of an XML file, it parses that file instead, so it also reads the
notices GCN distributes.

The documents on the broker's VOEvent topics are the same, and parse the
same way in a listener:

    consumer.subscribe(["astrocolibri.all.VOEvent"])
    for alert in consumer.consume():
        event = alert.voevent()
"""

from __future__ import annotations

import sys
from pathlib import Path

from astrocolibri import AstrocolibriError, Client, VOEvent, parse_voevent


def load(source: str) -> VOEvent:
    path = Path(source)
    if path.suffix.lower() == ".xml" and path.is_file():
        return parse_voevent(path.read_bytes())
    with Client() as client:
        return parse_voevent(client.get_event_voevent(source))


def describe(event: VOEvent) -> None:
    print(f"IVORN        {event.ivorn}")
    print(
        f"Role         {event.role}{'  (a test, not a real event)' if event.is_test else ''}"
    )
    print(f"Author       {event.author or 'N/A'}")
    print(f"Name         {event.name or 'N/A'}")
    print(f"Time         {event.time.isoformat() if event.time else 'N/A'}")
    if event.position is None:
        print("Position     none given")
    else:
        position = event.position
        error = f"{position.err}°" if position.err is not None else "none given"
        print(
            f"Position     RA {position.ra}°, Dec {position.dec}°, error radius {error}"
        )
    if event.importance is not None:
        print(f"Importance   {event.importance}")

    # Astro-COLIBRI documents group their Params; GCN notices mostly do not.
    if event.params:
        print_params("Params", event.params.values())
    for group_name, params in event.groups.items():
        print_params(group_name, params.values())

    for citation in event.citations:
        print(f"Cites        {citation.ivorn} ({citation.cite})")


def print_params(title, params) -> None:
    print(f"\n{title}")
    for param in params:
        unit = f" {param.unit}" if param.unit else ""
        print(f"  {param.name:22} {param.value!r}{unit}")


def main(source: str) -> int:
    try:
        event = load(source)
    except AstrocolibriError as error:
        print(f"Could not read a VOEvent from {source!r}: {error}")
        return 1
    describe(event)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "GRB 190829A"))
