# Astro-COLIBRI Python SDK

The `astro-colibri` distribution provides the `astrocolibri` Python package,
the SDK for **Astro-COLIBRI**. Its first public capability is the astronomical
alert-broker consumer; future modules will add supported access to the main API
and shared event models.

Receive multi-messenger astrophysics alerts in real time — JSON or
VOEvent/XML — directly from the Astro-Colibri broker.

---

## Installation

```bash
pip install astro-colibri
```

Requires Python 3.9+ and `confluent-kafka` (installed automatically).

---

## Quick start

### 1. Get your credentials

Request broker access from your account page on
[astro-colibri.com](https://astro-colibri.com). Your SCRAM `username` and
`password` are available under **Manage broker access**.

### 2. Subscribe and receive alerts

```python
import json
from astrocolibri import Consumer

with Consumer(
    username="your-username",
    password="your-password",
) as consumer:
    consumer.subscribe(["astrocolibri.all.JSON"])

    for message in consumer.consume(timeout=30):
        alert = json.loads(message.value())
        print(f"Alert received: {alert['id']} — RA={alert['ra']}, Dec={alert['dec']}")
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
    config: dict | None = None,        # advanced confluent-kafka options
)
```

#### `consumer.subscribe(topics, *, on_assign=None, on_revoke=None)`

Subscribe to a list of topics.

#### `consumer.consume(num_messages=1, timeout=-1)`

Message generator.

- `timeout=-1` (default): blocks until the next message — infinite loop.
- `timeout=N` (seconds): returns after N seconds with no message.

```python
# Infinite loop
for message in consumer.consume():
    handle(message.value())

# With a timeout (lets you do other work between batches)
while True:
    for message in consumer.consume(timeout=5.0):
        handle(message.value())
    check_app_state()
```

#### `consumer.close()`

Cleanly closes the connection (called automatically by the context manager).

---

## Persisting your read position

By default, a random UUID is used as the `group_id` suffix: you re-read from
`start_at` on every restart.

To persist your progress across sessions, pass a fixed `group_id`. The client
automatically prefixes it with your Kafka username to satisfy the per-user ACL:

```python
consumer = Consumer(
    username="your-username",
    password="your-password",
    group_id="my-program-v1",   # Kafka remembers where you left off
    start_at="latest",          # Only read new alerts going forward
)
```

---

## Testing locally against your own broker

If you're running the Astro-Colibri broker stack locally (see the
broker's `DEV.md`), point the client at it directly:

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

## TestPyPI release

Build and validate a release from a clean checkout:

```bash
python -m pip install -e ".[dev]"
python -m build
python -m twine check dist/*
python -m twine upload --repository testpypi dist/*
```

Test the uploaded distribution in a fresh environment. The additional PyPI
index supplies runtime dependencies that may not be mirrored on TestPyPI:

```bash
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  astro-colibri==0.1.0
```

Neither index allows an uploaded filename to be replaced. If a successful test
upload needs changes, increment the version before rebuilding. The exact
artifacts validated on TestPyPI can subsequently be uploaded to production
PyPI with the same version.

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
