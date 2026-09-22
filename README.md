# Astro-COLIBRI Python SDK

The `astro-colibri` distribution provides the `astrocolibri` Python package,
the SDK for **Astro-COLIBRI**. It has two parts:

| | What it does | You need |
|---|---|---|
| `Consumer` | Receives multi-messenger alerts in real time, as JSON or VOEvent/XML, from the Astro-COLIBRI broker | Broker credentials from [astro-colibri.com/broker](https://astro-colibri.com/broker) |
| `Client` | Queries the Astro-COLIBRI API: looks up events and sources, and searches for transients by time window or around a sky position | Your user ID from [astro-colibri.com/account](https://astro-colibri.com/account) (lookups work without one) |

Full documentation, with tutorials, is at
[astro-colibri.science/sdkdoc](https://astro-colibri.science/sdkdoc).

---

## Installation

```bash
pip install astro-colibri
```

Requires Python 3.9+. `confluent-kafka` and `requests` are installed
automatically.

---

## Quick start: real-time alerts

### 1. Get your credentials

Go to **[astro-colibri.com/broker](https://astro-colibri.com/broker)**. The link
opens the broker access page directly and prompts you to sign in if you are not
already. Request access there to be issued your SCRAM `username` and `password`;
the same page lets you rotate or revoke them later. A verified Astro-COLIBRI
account is required.

### 2. Subscribe and listen

```python
from astrocolibri import Consumer

with Consumer(
    username="your-username",
    password="your-password",
) as consumer:
    consumer.subscribe(["astrocolibri.all.JSON"])

    # Runs until you stop it, waiting for the next alert.
    for alert in consumer.consume():
        data = alert.value()
        print(f"Alert received: {data['id']} — RA={data['ra']}, Dec={data['dec']}")
```

That loop is the whole listener: `consume()` never ends on its own, so the
script keeps waiting for the next alert instead of exiting after the current
backlog. Stop it with Ctrl-C.

---

## Quick start: querying the API

### 1. Get your user ID

Open **[astro-colibri.com/account](https://astro-colibri.com/account)** (the
link asks you to sign in if needed) and copy your user ID. It identifies your
account to the API, which uses it for the per-account search quota and for
anything specific to you, such as your watchlist. Treat it like a personal key:
keep it out of shared notebooks and published code.

Event and source lookups work without a user ID; searches need one.

### 2. Configure it

Export it once in your shell or deployment environment:

```bash
export ASTROCOLIBRI_UID="your-user-id"
```

```python
from astrocolibri import Client

client = Client()              # reads ASTROCOLIBRI_UID
```

or pass it explicitly, for example from a variable your script already holds.
The explicit argument wins:

```python
client = Client(uid=my_uid)
```

The SDK keeps the user ID in memory only. It writes no configuration file, and
leaves the ID out of `repr(client)` and every error message.

### 3. Search

```python
from astrocolibri import Client

with Client() as client:
    results = client.latest_transients(
        start="2026-09-01T00:00:00Z",
        end="2026-09-02T00:00:00Z",
    )
    for event in results["voevents"]:
        print(
            f"Name: {event.get('source_name', 'N/A')}, "
            f"Type: {event.get('type', 'N/A')}, "
            f"Detection date/time: {event.get('time', 'N/A')}, "
            f"RA: {event.get('ra', 'N/A')}, "
            f"Dec: {event.get('dec', 'N/A')}, "
            f"Trigger ID: {event.get('trigger_id', 'N/A')}"
        )
```

---

## Alerts arrive decoded

Kafka carries bytes, but you don't need to handle them: `consume()` yields `Alert`
objects whose `value()` is the payload already decoded:

| Topic | `alert.value()` returns |
|---|---|
| `astrocolibri.*.JSON`, `astrocolibri.heartbeat` | `dict` — the parsed alert |
| `astrocolibri.*.VOEvent` | `str` — the XML document |

```python
for alert in consumer.consume():
    if alert.format == "json":
        data = alert.value()            # dict
        print(data["id"], data["type"], data["ra"], data["dec"])
    else:
        print(alert.value())            # XML, as text
```

Everything else about the record stays available:

| | |
|---|---|
| `alert.value()` | Decoded payload — `dict` or XML `str` |
| `alert.text()` | Payload as text, whatever the format |
| `alert.json()` | Payload parsed as JSON, whatever the topic |
| `alert.raw` | `bytes` — payload exactly as published |
| `alert.format` | `"json"` or `"voevent"` |
| `alert.key()` | `str` — the event id (all updates of an event share it) |
| `alert.headers()` | `dict[str, str]` — `event_id`, `dedupe_key`, `event_version`, `update_type`, `important`, `changed_fields` |
| `alert.topic()`, `.partition()`, `.offset()`, `.timestamp()` | Kafka coordinates |
| `alert.message` | The underlying `confluent_kafka.Message` |

A payload that cannot be decoded raises `AstrocolibriDecodeError` — and only
when you read it, so one bad record never takes down a running listener:

```python
from astrocolibri import AstrocolibriDecodeError

for alert in consumer.consume():
    try:
        data = alert.value()
    except AstrocolibriDecodeError as e:
        print(f"skipping: {e}")
        continue
    handle(data)
```

To handle the raw bytes yourself, turn decoding off — `consume()` then yields
the `confluent_kafka.Message` unchanged:

```python
consumer = Consumer(username="...", password="...", decode=False)
```

---

## Example scripts

Each script is a complete, runnable program:

| Script | Shows | Needs |
|---|---|---|
| [`example.py`](example.py) | A broker listener that subscribes to every topic and prints alerts as they arrive; stop it with Ctrl-C | Broker credentials |
| [`examples/get_event.py`](examples/get_event.py) | Looking up one event by trigger ID or name | Nothing |
| [`examples/resolve_source.py`](examples/resolve_source.py) | Listing every localization of a source, then fetching the best one | Nothing |
| [`examples/latest_transients.py`](examples/latest_transients.py) | Searching a time window, with user ID and quota errors handled | User ID |
| [`examples/cone_search.py`](examples/cone_search.py) | Searching around a position written in sexagesimal notation | User ID |
| [`examples/contour_search.py`](examples/contour_search.py) | Searching inside a gravitational-wave localization contour | User ID |

```bash
python example.py
python examples/resolve_source.py "GRB 190829A"
```

---

## Available topics

| Topic | Description |
|---|---|
| `astrocolibri.all.JSON` | Every alert, Astro-Colibri JSON format |
| `astrocolibri.all.VOEvent` | Every alert, VOEvent/XML format |
| `astrocolibri.important.JSON` | Important alerts, Astro-Colibri JSON format |
| `astrocolibri.important.VOEvent` | Important alerts, VOEvent/XML format |
| `astrocolibri.heartbeat` | Pipeline liveness message, JSON format |

---

## Querying the API

### Events and sources

`get_event()` accepts a trigger ID, a source name or a discoverer designation,
and tolerates spacing differences (`"GRB190829A"` finds `"GRB 190829A"`):

```python
event = client.get_event("GRB 190829A")
print(event["trigger_id"], event["ra"], event["dec"], event["err"])
```

A name can belong to several events: GRB 190829A was localized by both
Fermi/GBM and Swift/XRT. A lookup by name returns only one of them, not
necessarily the best. `resolve_source()` lists them all, best-localized first:

```python
for summary in client.resolve_source("GRB 190829A"):
    print(summary["trigger_id"], summary.get("observatory"), summary["err"])
# 922968 swift 0.0016
# 588801358 fermi 2.21

best = client.get_event("922968")
```

`resolve_source()` only covers transient events. Catalog sources (TeVCat, 4FGL,
X-ray binaries), bright stars and objects known only to SIMBAD give an empty
list; `get_source_summary()` returns their position instead, or `None` for a
name nobody knows. A SIMBAD lookup can be slow, so allow it time:

```python
summary = client.get_source_summary("Crab", timeout=300)
```

Timestamps in source summaries are in **milliseconds** since the Unix epoch.

Several events in one request, in the order given:

```python
events = client.get_events(["922968", "588801358", "S230518h"], missing="skip")
```

Heavy fields are left out unless you ask for them; otherwise `gw_contours` and
`archive` come back as `{"Parameter": "Not requested"}`:

```python
event = client.get_event("S230518h", optional_parameters=["gw_contours"])
```

### Searches

`latest_transients()` searches a time window; `cone_search()` also restricts
it to a region of the sky. Both return the API's JSON as a `dict`. The
transients are in `"voevents"`, one `dict` per event, and the
[API documentation](https://astro-colibri.science/apidoc#params-voevent) lists every event
parameter. A cone search adds catalog matches in `"sources"`, `"Xsources"` and
`"icecat"`, which are not restricted to the time window.

Times must carry a timezone: an aware `datetime`, or an ISO 8601 string ending
in `Z` or an offset. A time without one is rejected rather than guessed.

Angles accept decimal degrees or sexagesimal strings, and the unit is read from
the notation, never from the size of the number:

| You write | Read as |
|---|---|
| `83.6331`, `"83.6331"` | degrees |
| `"05h34m31.94s"` | hours, minutes, seconds |
| `"+22d00m52.2s"`, `"22°00′52.2″"` | degrees, arcminutes, arcseconds |
| `ra="05:34:31.94"` | colons for right ascension: hours |
| `dec="+22:00:52.2"`, `radius="00:30:00"` | colons for declination and radius: degrees |
| `radius="30′"` or `"30'"` | arcminutes (0.5°) |

```python
results = client.cone_search(
    ra="05h34m31.94s",
    dec="+22d00m52.2s",
    radius=2,
    start="2026-08-01T00:00:00Z",
    end="2026-09-01T00:00:00Z",
)
```

Gravitational waves, Fermi/GBM and IPN bursts, IceCube neutrinos and MAXI
transients are localized to regions far from circular. Search inside the
event's 90% localization contour instead of a circle, optionally widened by a
margin in degrees. If no contour is stored, the circle is searched, and
`"search_region"` says which one was used:

```python
results = client.cone_search(
    ra=100.72,
    dec=-22.10,
    radius=15,
    start="2023-05-18T12:59:08Z",
    end="2023-05-25T12:59:08Z",
    contour_trigger_id="S230518h",
    contour_margin=1.0,
)
print(results["search_region"])   # "contour_90" or "circle"
```

### Filters

A search returns every event your account may access unless you narrow it.
Pass an API filter dictionary, the same structure the Astro-COLIBRI app builds.
The [filter notebook](https://colab.research.google.com/drive/1i-O0vfV18ndKVeTyoAjH6XDMxKqcQe2B?usp=sharing)
walks through that structure interactively, and the
[photometry sub-filter notebook](https://colab.research.google.com/drive/1QaB5lZ_xwxvf5fHLW0GYJupMkc2zIQbE?usp=sharing)
shows how to select fast-rising or fast-fading transients from their light
curves. Optical transients only:

```python
optical_transients = {
    "type": "FieldSpecification",
    "operation": "==",
    "field": "type",
    "value": "ot",
    "typeField": "string",
}
results = client.latest_transients(start=start, end=end, event_filter=optical_transients)
```

or apply the filters you saved in the app:

```python
results = client.latest_transients(start=start, end=end, use_saved_filters=True)
```

### Your quota

Searches count against a daily per-account quota (100 requests at the time of
writing); lookups do not. An identical search repeated within the same half
hour is normally answered from the API's cache without counting again, which
is why the SDK sends an explicit match-everything filter by default. Two things
defeat the cache: `use_saved_filters=True`, which always runs a fresh search,
and a window that moves between calls, such as one ending at `datetime.now()`.

The SDK never retries a request on its own. When the quota runs out you get
`AstrocolibriRateLimitError`, whose `reset_time` says when it renews.

### Scientific formats

```python
voevent = client.get_event_voevent("GRB 190829A")            # VOEvent XML
votable = client.cone_search(..., return_format="votable")   # VOTable XML
```

### Errors

| Exception | When |
|---|---|
| `AstrocolibriConfigError` | An argument is invalid. Raised before anything is sent, so it costs no quota |
| `AstrocolibriAuthError` | A search without a user ID, or with one the API does not recognize |
| `AstrocolibriNotFoundError` | No event matches the identifier |
| `AstrocolibriRateLimitError` | The daily search quota is used up; see `reset_time` |
| `AstrocolibriAPIError` | The API rejected or failed the request; see `status_code` and `message` |
| `AstrocolibriTransportError` | The API could not be reached, or the request timed out |

All of them derive from `AstrocolibriError`.

---

## API reference

### `Consumer`

```python
Consumer(
    username: str,
    password: str,
    *,
    broker_url: str | None = None,
    group_id: str | None = None,
    start_at: str = "earliest",       # "earliest" | "latest"
    security_protocol: str = "SASL_SSL",
    decode: bool = True,               # False yields raw confluent_kafka.Message
    poll_interval: float = 1.0,        # seconds per internal poll while listening
    config: dict | None = None,        # advanced confluent-kafka options
)
```

#### `consumer.subscribe(topics, *, on_assign=None, on_revoke=None, on_lost=None)`

Subscribe to a list of topics.

#### `consumer.consume(num_messages=1, timeout=-1)`

Generator of `Alert` objects.

- `timeout=-1` (default): **listens continuously**. The generator never ends;
  it waits for the next alert. Internally it polls in `poll_interval` slices,
  so Ctrl-C stays responsive.
- `timeout=N` (seconds): ends after N seconds without a new alert, so your
  program can do something else between bursts.

```python
# Continuous listener — this is the normal case
for alert in consumer.consume():
    handle(alert.value())

# Batch mode (lets you do other work between bursts)
while True:
    for alert in consumer.consume(timeout=5.0):
        handle(alert.value())
    check_app_state()
```

Transient Kafka conditions — end of partition, a dropped broker connection, a
group rebalance — are logged through the standard `logging` module and skipped,
because the client recovers from them on its own. Only an unrecoverable error
raises `AstrocolibriKafkaError`. To see those warnings:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

#### `consumer.close()`

Cleanly closes the connection (called automatically by the context manager).

### `Client`

```python
Client(
    uid: str | None = None,          # default: the ASTROCOLIBRI_UID variable
    *,
    timeout: float = 30.0,           # seconds per request
    session: requests.Session | None = None,
)
```

`Client` talks to the public Astro-COLIBRI API at `https://astro-colibri.science`.

| Method | Returns | Quota |
|---|---|---|
| `get_event(identifier, *, optional_parameters=(), simbad=False, include_custom_events=False)` | event `dict` | free |
| `get_events(identifiers, *, optional_parameters=(), simbad=False, include_custom_events=False, missing="raise")` | `list` of event dicts | free |
| `get_event_voevent(identifier, *, optional_parameters=())` | VOEvent XML `str` | free |
| `resolve_source(name)` | `list` of localization summaries, best first | free |
| `get_source_summary(name)` | summary `dict`, or `None` | free |
| `latest_transients(*, start, end, event_filter=None, use_saved_filters=False, optional_parameters=(), include_watchlist=False, return_format="json")` | results `dict`, or `str` for `"votable"` and `"url"` | counts |
| `cone_search(*, ra, dec, radius, start, end, contour_trigger_id=None, contour_margin=None, event_filter=None, use_saved_filters=False, optional_parameters=(), include_watchlist=False, return_format="json")` | results `dict`, or `str` for `"votable"` and `"url"` | counts |
| `close()` | | |

Every method also accepts `timeout=`. `Client` is a context manager. Like the
`requests.Session` it holds, it is not thread-safe: use one per thread.

---

## Your read position

Your read position (offset) is always persisted. With no `group_id`, the client
joins the consumer group `<your-username>.default`, so restarting a program
resumes exactly where it left off: nothing is re-read, nothing is missed.

`start_at` only applies the **first** time a given consumer group connects. On
every later run the stored offset wins, so changing `start_at` on an existing
group has no effect. To deliberately re-read the retention window, use a
`group_id` you have never used before.

The client automatically prefixes `group_id` with your Kafka username to satisfy
the per-user ACL, so `group_id="my-program-v1"` becomes the Kafka group
`your-username.my-program-v1`.

```python
consumer = Consumer(
    username="your-username",
    password="your-password",
    group_id="my-program-v1",   # its own independent read position
    start_at="latest",          # only applies on this group's very first run
)
```

---

## Running several scripts with the same credentials

One set of credentials can drive as many scripts as you like, but **give each
script its own `group_id`**. Consumers that share a group are treated by Kafka
as one logical reader and have the partitions divided between them, so each
script would receive only a slice of the stream rather than every alert.

```python
# ingest.py
consumer = Consumer(username="alice", password="...", group_id="ingest")

# alerting.py
consumer = Consumer(username="alice", password="...", group_id="alerting")
```

Each group keeps its own independent read position, so the two scripts can run
at different speeds, restart independently, and both still see the full alert
stream.

Leaving `group_id` unset in more than one script is the case to avoid: they all
land in `<your-username>.default` and silently share the stream between them.

Running the *same* script as several replicas is the one case where sharing a
`group_id` is what you want: that is how you spread the load, and Kafka
rebalances the partitions across the replicas automatically.

---

## Testing locally against your own broker

If you're running the Astro-Colibri broker stack locally (see the
broker's `QUICKSTART.md`), point the client at it directly:

```python
consumer = Consumer(
    username="alice",
    password="alice-strong-password",
    broker_url="localhost:9092",
    security_protocol="SASL_PLAINTEXT",  # local trusted broker only
)
```

Install the package in editable mode from the repository root for
development:

```bash
cd Colibri_v2/colibri_client
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Citation

Please cite the software release using [`CITATION.cff`](CITATION.cff) and the
Astro-COLIBRI platform papers:

- Reichherzer et al. (2023), *Astro-COLIBRI 2 - An Advanced Platform for
  Real-Time Multi-Messenger Discoveries*, Galaxies 11, 22,
  [doi:10.3390/galaxies11010022](https://doi.org/10.3390/galaxies11010022).
- Reichherzer et al. (2021), *Astro-COLIBRI - The COincidence LIBrary for
  Real-time Inquiry for Multimessenger Astrophysics*, ApJS 256, 5,
  [doi:10.3847/1538-4365/ac1517](https://doi.org/10.3847/1538-4365/ac1517).

---

## License

This source-available software is licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE). It may be used, modified, and
redistributed for permitted noncommercial purposes, including use by
educational institutions and public research organizations.

Commercial use requires a separate written license. Contact
[Astro-COLIBRI (Fabian Schüssler)](mailto:astro.colibri@gmail.com) and see
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

Use of Astro-COLIBRI hosted services, including the Kafka broker and its data,
is governed separately by the
[Astro-COLIBRI Terms of Service](https://astro-colibri.science/tos).
