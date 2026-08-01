"""
astrocolibri/exceptions.py

Astro-Colibri client library exceptions.
"""


class AstrocolibriError(Exception):
    """
    Base exception for all Astro-Colibri client errors.

    All other exceptions in this library inherit from it, so you can catch
    any Astro-Colibri error with a single `except`.

    Example::

        from astrocolibri.exceptions import AstrocolibriError

        try:
            consumer = Consumer(...)
        except AstrocolibriError as e:
            print(f"Astro-Colibri error: {e}")
    """


class AstrocolibriKafkaError(AstrocolibriError):
    """
    Unrecoverable Kafka error encountered while consuming a message.

    Raised when a message carries a Kafka error other than
    `_PARTITION_EOF` (which is silently ignored).
    """


class AstrocolibriAuthError(AstrocolibriError):
    """
    Authentication failure against the Astro-Colibri broker.

    Raised when `username`/`password` are invalid or the broker refuses
    the connection.
    """


class AstrocolibriConfigError(AstrocolibriError):
    """
    Invalid Consumer configuration.

    Raised when invalid parameters are passed to the constructor.
    """
