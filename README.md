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

## Example script

A minimal, ready-to-run version of the snippet above is provided in
[`example.py`](example.py). It connects with your credentials, subscribes to
all topics and prints each alert as it arrives — the fastest way
to check that your setup works before wiring the SDK into your own pipeline.

```bash
python example.py
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