"""This file is a demonstration of how to use this package"""

from astrocolibri import Consumer, TOPICS

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

# Start consuming messages from the broker
print("4. Start consuming messages from the broker")
for message in consumer.consume():
    print("Received message:", message)
