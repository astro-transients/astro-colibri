"""
Submit your photometry of an event as an observation report.

Setup:
    pip install astro-colibri
    export ASTROCOLIBRI_API_TOKEN="colibri_..."

    Create the token in the app at astro-colibri.com/account, under
    Observatory & TOM access > Community observatories.

Run:
    python examples/submit_observation_report.py MYOBS "GRB 251020A" photometry.csv

You must be a member of the observatory (MYOBS here). The CSV has one row
per measurement and a header naming the columns, for example:

    observation_type,filter,magnitude,magnitude_error,time_utc_mid
    detection,r,18.21,0.05,2025-10-20T21:14:05Z
    upper_limit,g,20.5,,2025-10-20T21:20:00Z

Empty cells are left out. The report is shown on the event in the app and
your observatory's members are notified. Running the script again with the
same file stores nothing new.
"""

from __future__ import annotations

import csv
import sys

from astrocolibri import (
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriError,
    AstrocolibriNotFoundError,
    Client,
)

NUMBER_COLUMNS = ("magnitude", "magnitude_error", "flux", "flux_error")


def read_observations(path: str) -> list:
    observations = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            observation = {
                key: value.strip()
                for key, value in row.items()
                if value and value.strip()
            }
            for column in NUMBER_COLUMNS:
                if column in observation:
                    observation[column] = float(observation[column])
            observations.append(observation)
    return observations


def main(observatory: str, event: str, path: str) -> int:
    try:
        observations = read_observations(path)
    except (OSError, ValueError) as error:
        print(f"Could not read {path}: {error}")
        return 1

    with Client() as client:
        try:
            result = client.submit_observation_report(
                observatory,
                source_name=event,
                observations=observations,
            )
        except AstrocolibriConfigError as error:
            # Rejected before anything was sent.
            print(f"Invalid report: {error}")
            return 1
        except AstrocolibriAuthError as error:
            print(f"Not allowed: {error}")
            return 1
        except AstrocolibriNotFoundError as error:
            print(f"Not found: {error}")
            return 1
        except AstrocolibriError as error:
            print(f"The submission failed: {error}")
            return 1

    if result["status"] == "unchanged":
        print(f"This report was already submitted as {result['report_id']}.")
    else:
        print(
            f"Stored report {result['report_id']} for {result['source_name']} "
            f"({len(observations)} measurements)."
        )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
