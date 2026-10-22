"""Minimal Astro-COLIBRI broker listener.

Connects to the broker, subscribes to every public topic and then keeps
listening: the loop waits for the next alert and never ends on its own, so
this is a complete, runnable listener. Stop it with Ctrl-C.

Optionally, it keeps only the alerts that pass your Astro-COLIBRI filters:
see "Optional filtering" below.

Get your credentials at https://astro-colibri.com/broker
"""

from astrocolibri import TOPICS, Consumer, EventFilter

# Optional filtering: keep only the alerts that pass your Astro-COLIBRI
# filters. Heartbeats always get through. Leave both settings as they are to
# receive every alert.
# - USE_SAVED_FILTERS = True applies the filters saved in the Astro-COLIBRI
#   app for your account. It needs your user ID in the ASTROCOLIBRI_UID
#   environment variable (shown at https://astro-colibri.com/account).
# - FILTER_FILE applies a filter file instead, such as the one the
#   "Download Filters" button in the app's filter menu saves.
USE_SAVED_FILTERS = False
FILTER_FILE = None  # e.g. "Astro-COLIBRI_filters.json"

event_filter = None
if USE_SAVED_FILTERS:
    event_filter = EventFilter.from_saved_filters()
elif FILTER_FILE:
    event_filter = EventFilter.from_file(FILTER_FILE)

# Create a consumer to connect to the broker.
# Your read position is remembered between runs, so restarting this script
# resumes where it stopped. Running several scripts on the same credentials?
# Give each one its own group_id (e.g. group_id="ingest"), otherwise they share
# one group and each receives only part of the alert stream.
consumer = Consumer(username="your_username", password="your_password")
print("1. Connected to the Broker")

# List all available topics the ones you wish to subscribe to.
print("2. Available topics =", TOPICS)
topic_list = TOPICS
print("Selected topics =", topic_list)

# Subscribe to the topics you have selected
consumer.subscribe(topic_list)
print("3. Subscribed to the topics")

# Start listening. consume() without a timeout waits for the next alert
# indefinitely, so this loop runs until you interrupt it. With an
# event_filter, only the alerts that pass it arrive here.
print("4. Listening for alerts (Ctrl-C to stop)")
try:
    for alert in consumer.consume(event_filter=event_filter):
        # Payloads arrive decoded: a dict on the .JSON topics, the XML
        # document as a string on the .VOEvent topics.
        content = alert.value()

        if alert.topic() == "astrocolibri.heartbeat":
            print(f"[heartbeat] {content}")
        elif alert.format == "json":
            print(
                f"[{alert.topic()}] trigger_id={content.get('trigger_id')} "
                f"type={content.get('type')} "
                f"ra={content.get('ra')} dec={content.get('dec')}"
            )
        else:
            print(f"[{alert.topic()}] VOEvent, {len(alert)} bytes")
            print(content)
except KeyboardInterrupt:
    print("\nStopping.")
finally:
    # Commits the read position, so the next run picks up where this stopped.
    consumer.close()
