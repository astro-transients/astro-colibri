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
    Authentication failure against the Astro-Colibri broker or API.

    Raised when `username`/`password` are invalid or the broker refuses
    the connection, and when an API request needs an Astro-COLIBRI user ID
    that is either not configured or not recognised by the API.
    """


class AstrocolibriConfigError(AstrocolibriError):
    """
    Invalid Consumer or Client configuration.

    Raised when invalid parameters are passed to a constructor or to a
    `Client` method: an empty `uid`, a malformed coordinate, a time without
    a timezone. Always raised before anything is sent to the API, so it
    never costs quota.
    """


class AstrocolibriDecodeError(AstrocolibriError):
    """
    A message payload could not be decoded into its announced format.

    Raised by `Alert.value()` / `Alert.text()` / `Alert.json()` when the
    payload is not valid UTF-8, or when a JSON topic carries something that
    is not valid JSON.

    Decoding is lazy, so this is raised while you read the alert and not
    while it is consumed: a single malformed message can be skipped without
    interrupting a long-running stream.

    Example::

        for alert in consumer.consume():
            try:
                data = alert.value()
            except AstrocolibriDecodeError as e:
                print(f"skipping undecodable alert: {e}")
                continue
            handle(data)
    """


class AstrocolibriTransportError(AstrocolibriError):
    """
    The API request never produced a response.

    Raised for DNS failures, refused connections, TLS problems and
    timeouts: anything that prevented `astro-colibri.science` from
    answering at all. An answer that happens to be an error is an
    `AstrocolibriAPIError` instead.

    The SDK never retries on its own: an API query can consume your daily
    quota or trigger expensive server-side processing, so repeating it is
    your decision.

    Example::

        try:
            events = client.cone_search(ra=83.6, dec=22.0, radius=2, ...)
        except AstrocolibriTransportError as e:
            print(f"could not reach the API: {e}")
    """


class AstrocolibriAPIError(AstrocolibriError):
    """
    The Astro-Colibri API answered, and the answer was an error.

    Attributes:
        status_code: HTTP status reported by the API, when there was one.
        endpoint: Path that was requested, e.g. `"/cone_search"`.
        message: The server's own error message, without the decoration
            added to `str(exception)`.

    Example::

        try:
            client.cone_search(...)
        except AstrocolibriAPIError as e:
            print(e.status_code, e.endpoint, e.message)
    """

    def __init__(
        self,
        message: str,
        *,
        status_code=None,
        endpoint=None,
    ) -> None:
        detail = message
        if endpoint:
            detail = f"{endpoint}: {detail}"
        if status_code:
            detail = f"[HTTP {status_code}] {detail}"
        super().__init__(detail)
        self.message = message
        self.status_code = status_code
        self.endpoint = endpoint


class AstrocolibriNotFoundError(AstrocolibriAPIError):
    """
    The requested event or source does not exist.

    Raised by `Client.get_event()` and `Client.get_events()` when the API
    reports an identifier as unknown, and by `Client.get_event_voevent()`
    when there is no event to convert.

    Note that the API signals a missing event with HTTP 207 and a body
    describing the failure, not with a 404, so this exception is what makes
    a miss look like a miss.
    """


class AstrocolibriRateLimitError(AstrocolibriAPIError):
    """
    The account's API quota is exhausted.

    Search endpoints are limited per Astro-COLIBRI account (100 requests
    per day at the time of writing). Event and source lookups are not
    metered and keep working.

    Attributes:
        reset_time: When the quota renews, parsed from the server message.
            `None` if the server did not report a parseable time.

    Example::

        try:
            client.latest_transients(start=..., end=...)
        except AstrocolibriRateLimitError as e:
            print(f"quota exhausted, renews at {e.reset_time}")
    """

    def __init__(
        self,
        message: str,
        *,
        status_code=None,
        endpoint=None,
        reset_time=None,
    ) -> None:
        super().__init__(message, status_code=status_code, endpoint=endpoint)
        self.reset_time = reset_time
