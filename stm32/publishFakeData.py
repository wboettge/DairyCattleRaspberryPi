# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import argparse
from multiprocessing import connection
from awscrt import io, mqtt, exceptions
from awsiot import mqtt_connection_builder
from dotenv import load_dotenv
import sys
import threading
import time
from uuid import uuid4
import json
import platform
import random
import os
import time
# Load local configuration settings
# a .env file must be located in the directory and include definitions for:
# AWS_ENDPOINT, CERT_FILE, PRI_KEY_FILE, and ROOT_CA_FILE as 
load_dotenv()

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

# Using globals to simplify sample code

io.init_logging(getattr(io.LogLevel, 'NoLogs'), 'stderr')

received_count = 0
received_all_event = threading.Event()

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        print("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                sys.exit("Server rejected resubscribe to topic: {}".format(topic))


# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global received_count
    received_count += 1
    if received_count == 10:
        received_all_event.set()


def gen_fake_data(start=20.0, min=20.0, max=25.0):
    trending_up = True
    cur = start
    change_options = [0, 0.1, 0.2, -0.1]
    weights = [80, 8, 4, 8]
    while(True):
        change_val = random.choices(
            population= change_options,
            weights= weights
        )[0]
        cur = cur + change_val if trending_up else cur - change_val
        cur = round(cur, 3)
        if cur <= min:
            trending_up = True
        elif cur >= max:
            trending_up = False
        yield cur


if __name__ == '__main__':
    CLIENT_ID = 'test' + str(uuid4())
    TOPIC = 'test/temp'
    DEFAULT_TIMEOUT = 5
    timeout = int(os.getenv('SAMPLE_FREQUENCY')) if os.getenv('SAMPLE_FREQUENCY') is not None else DEFAULT_TIMEOUT
    print(timeout)

    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=os.getenv('AWS_ENDPOINT'),
        port=443,
        cert_filepath=os.getenv('CERT_FILE'),
        pri_key_filepath=os.getenv('PRI_KEY_FILE'),
        client_bootstrap=client_bootstrap,
        ca_filepath=os.getenv('ROOT_CA_FILE'),
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
        http_proxy_options=None)

    print(f"Connecting to {os.getenv('AWS_ENDPOINT')} with client ID '{CLIENT_ID}'...")

    connection_attempts = 0
    while connection_attempts < 6:
        connection_attempts += 1
        try:
            connect_future = mqtt_connection.connect()
            connect_future.result()
            print("Connected!")
            break
        except exceptions.AwsCrtError:
            print("Connection Failed, retring...")
            mqtt_connection.disconnect()
            time.sleep(10)

    # Subscribe
    print("Subscribing to topic '{}'...".format(TOPIC))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=TOPIC,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.
 
    publish_count = 1
    data_gen = gen_fake_data()
    while (True):
        message = {
            'Device_ID': platform.node(),
            'Data': {
                'Tempurature': next(data_gen)
            }
        }
        print("Publishing message to topic '{}': {}".format(TOPIC, message))
        message_json = json.dumps(message)
        mqtt_connection.publish(
            topic=TOPIC,
            payload=message_json,
            qos=mqtt.QoS.AT_LEAST_ONCE)
        time.sleep(timeout)
        publish_count += 1
