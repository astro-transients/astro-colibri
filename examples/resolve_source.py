"""
List every event recorded under a source name, then fetch the best one.

Run:
    python examples/resolve_source.py "GRB 190829A"
    python examples/resolve_source.py Crab

Source lookups need no user ID and do not count against your API quota.

One source often has several localizations: a gamma-ray burst can be
reported by Fermi/GBM within seconds and pinned down by Swift/XRT minutes
later. The summaries arrive best-localized first, so the first is usually
the one to follow up.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Dict

from astrocolibri import AstrocolibriError, Client


def detection_time(summary: Dict[str, Any]) -> str:
    # Source summaries carry the time in milliseconds since the Unix epoch.
    timestamp = summary.get("timestamp")
    if not timestamp or timestamp <= 0:
        return "time unknown"
    moment = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def uncertainty(summary: Dict[str, Any]) -> str:
    err = summary.get("err")
    return (
        f"±{err}°"
        if isinstance(err, (int, float)) and err > 0
        else "uncertainty unknown"
    )


def degrees(value: Any) -> str:
    return f"{value:.4f}°" if isinstance(value, (int, float)) else "N/A"


def main(name: str) -> int:
    with Client() as client:
        try:
            summaries = client.resolve_source(name)
            if not summaries:
                # Catalog sources, bright stars and SIMBAD objects have no
                # transient events, but a summary still gives their position.
                # A SIMBAD lookup can be slow, hence the long timeout.
                summary = client.get_source_summary(name, timeout=300)
                if summary is None:
                    print(f"No source named {name!r} is known.")
                    return 1
                print(
                    f"{summary.get('name', name)} ({summary.get('origin', 'catalog')}) is at "
                    f"RA {degrees(summary.get('ra'))}, Dec {degrees(summary.get('dec'))}, "
                    f"but has no transient events."
                )
                return 0

            print(f"{len(summaries)} localization(s) of {name}, best first:")
            for summary in summaries:
                instrument = "/".join(
                    part
                    for part in (summary.get("observatory"), summary.get("instrument"))
                    if part
                )
                print(
                    f"  {summary['trigger_id']:>12}  {instrument or 'instrument unknown':<14}"
                    f"  {uncertainty(summary):<22}  {detection_time(summary)}"
                )

            best = client.get_event(summaries[0]["trigger_id"])
        except AstrocolibriError as error:
            print(f"The lookup failed: {error}")
            return 1

    print()
    print(
        f"Best localization: trigger {best.get('trigger_id')} from {best.get('observatory')}, "
        f"RA {degrees(best.get('ra'))}, Dec {degrees(best.get('dec'))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "GRB 190829A"))
