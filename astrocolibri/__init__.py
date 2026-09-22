"""
astrocolibri: the Python SDK for Astro-COLIBRI.

Two entry points:

- :class:`Consumer` receives alerts from the Astro-COLIBRI broker in real
  time.
- :class:`Client` queries the Astro-COLIBRI API: look up events and
  sources, and search for transients by time window or around a position.

Broker quick start, a complete listener that runs until you stop it::

    from astrocolibri import Consumer

    with Consumer(
        username="your-username",
        password="your-password",
    ) as consumer:
        consumer.subscribe(["astrocolibri.all.JSON"])
        for alert in consumer.consume():
            data = alert.value()      # already decoded: a dict here
            print(data["id"], data["ra"], data["dec"])

Payloads arrive decoded, never as raw bytes: ``alert.value()`` is a ``dict``
on the JSON topics and the XML document as ``str`` on the VOEvent topics.

API quick start (your user ID is shown at https://astro-colibri.com/account)::

    from astrocolibri import Client

    with Client() as client:          # reads the ASTROCOLIBRI_UID variable
        event = client.get_event("GRB 190829A")
        print(event["trigger_id"], event["ra"], event["dec"])

        results = client.cone_search(
            ra="05h34m31.94s",
            dec="+22d00m52.2s",
            radius=2,
            start="2026-09-01T00:00:00Z",
            end="2026-09-08T00:00:00Z",
        )
        for transient in results["voevents"]:
            print(transient.get("source_name"), transient.get("type"))

Available topics:
    - ``astrocolibri.all.JSON``    — every alert, JSON format
    - ``astrocolibri.all.VOEvent`` — every alert, VOEvent/XML format
    - ``astrocolibri.important.JSON`` — important alerts, JSON format
    - ``astrocolibri.important.VOEvent`` — important alerts, VOEvent/XML format
"""

from ._version import __version__
from .alert import FORMAT_JSON, FORMAT_UNKNOWN, FORMAT_VOEVENT, Alert
from .client import OPTIONAL_PARAMETERS, Client
from .consumer import TOPICS, Consumer
from .exceptions import (
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriDecodeError,
    AstrocolibriError,
    AstrocolibriKafkaError,
    AstrocolibriNotFoundError,
    AstrocolibriRateLimitError,
    AstrocolibriTransportError,
)

__all__ = [
    "Consumer",
    "Alert",
    "Client",
    "TOPICS",
    "OPTIONAL_PARAMETERS",
    "FORMAT_JSON",
    "FORMAT_VOEVENT",
    "FORMAT_UNKNOWN",
    "AstrocolibriError",
    "AstrocolibriKafkaError",
    "AstrocolibriAuthError",
    "AstrocolibriConfigError",
    "AstrocolibriDecodeError",
    "AstrocolibriAPIError",
    "AstrocolibriNotFoundError",
    "AstrocolibriRateLimitError",
    "AstrocolibriTransportError",
    "__version__",
]
