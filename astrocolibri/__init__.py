"""
astrocolibri — Client library for the Astro-Colibri astronomical alert broker.

Quick start::

    from astrocolibri import Consumer

    with Consumer(
        username="your-username",
        password="your-password",
    ) as consumer:
        consumer.subscribe(["astrocolibri.all.JSON"])
        for message in consumer.consume(timeout=30):
            print(message.value())

Available topics:
    - ``astrocolibri.all.JSON``    — every alert, JSON format
    - ``astrocolibri.all.VOEvent`` — every alert, VOEvent/XML format
    - ``astrocolibri.important.JSON`` — important alerts, JSON format
    - ``astrocolibri.important.VOEvent`` — important alerts, VOEvent/XML format
"""

from ._version import __version__
from .consumer import Consumer, TOPICS
from .exceptions import (
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriError,
    AstrocolibriKafkaError,
)

__all__ = [
    "Consumer",
    "TOPICS",
    "AstrocolibriError",
    "AstrocolibriKafkaError",
    "AstrocolibriAuthError",
    "AstrocolibriConfigError",
    "__version__",
]
