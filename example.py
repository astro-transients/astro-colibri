"""Minimal Astro-COLIBRI broker listener.

Connects to the broker, subscribes to every public topic and then keeps
listening: the loop waits for the next alert and never ends on its own, so
this is a complete, runnable listener. Stop it with Ctrl-C.

Get your credentials at https://astro-colibri.com/broker
"""

from astrocolibri import TOPICS, Consumer

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
# indefinitely, so this loop runs until you interrupt it.
print("4. Listening for alerts (Ctrl-C to stop)")
try:
    for alert in consumer.consume():
        # Payloads arrive decoded: a dict on the .JSON topics, the XML
        # document as a string on the .VOEvent topics.
        content = alert.value()

        if alert.topic() == "astrocolibri.heartbeat":
            print(f"[heartbeat] {content}")
        elif alert.format == "json":
            print(
                f"[{alert.topic()}] id={content.get('id')} "
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
