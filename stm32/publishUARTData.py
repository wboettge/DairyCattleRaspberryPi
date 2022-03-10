# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import argparse
from multiprocessing import connection
from awscrt import io, mqtt, exceptions
from awsiot import mqtt_connection_builder
import sys
import threading
import time
from uuid import uuid4
import json
import platform
import random
import serial
import serial.tools.list_ports
import time
 
ports = list(serial.tools.list_ports.grep('ACM'))
if len(ports) == 0:
    print('Cannot find UART port, exiting...')
    exit(-1)

UART_PORT = ports[0].device
BAUD_RATE = 9600

ser = serial.Serial(port=UART_PORT, baudrate=9600)

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

parser = argparse.ArgumentParser(description="Send and receive messages through and MQTT connection.")
parser.add_argument('--endpoint', required=True, help="Your AWS IoT custom endpoint, not including a port. " +
                                                      "Ex: \"abcd123456wxyz-ats.iot.us-east-1.amazonaws.com\"")
parser.add_argument('--port', type=int, help="Specify port. AWS IoT supports 443 and 8883.")
parser.add_argument('--cert', help="File path to your client certificate, in PEM format.")
parser.add_argument('--key', help="File path to your private key, in PEM format.")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format. " +
                                      "Necessary if MQTT server uses a certificate that's not already in " +
                                      "your trust store.")
parser.add_argument('--client-id', default="test-" + str(uuid4()), help="Client ID for MQTT connection.")
parser.add_argument('--topic', default="test/temp", help="Topic to subscribe to, and publish messages to.")
parser.add_argument('--count', default=10, type=int, help="Number of messages to publish/receive before exiting. " +
                                                          "Specify 0 to run forever.")
parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
    help='Logging level')
parser.add_argument('--timeout', default=5, type=int, help="Time between publishing new data")

parser.add_argument('--datasource', default='Cow01', type=str)
parser.add_argument('--measures', default=['Temperature'], nargs='+')

# Using globals to simplify sample code
args = parser.parse_args()

io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

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
    if received_count == args.count:
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
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=args.endpoint,
        port=args.port,
        cert_filepath=args.cert,
        pri_key_filepath=args.key,
        client_bootstrap=client_bootstrap,
        ca_filepath=args.root_ca,
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=args.client_id,
        clean_session=False,
        keep_alive_secs=30,
        http_proxy_options=None)

    print("Connecting to {} with client ID '{}'...".format(
        args.endpoint, args.client_id))

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
    print("Subscribing to topic '{}'...".format(args.topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=args.topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.


    if args.count == 0:
        print ("Sending messages until program killed")
    else:
        print ("Sending {} message(s)".format(args.count))

    publish_count = 1
    while (publish_count <= args.count) or (args.count == 0):
        try:
            data = (str(ser.readline(), 'utf8'))
            print(data, end='')
            message = {
                'Device_ID': platform.node(),
                'Data': {
                    'Tempurature': float(data.strip())
                }
            }
            print("Publishing message to topic '{}': {}".format(args.topic, message))
            message_json = json.dumps(message)
            mqtt_connection.publish(
                topic=args.topic,
                payload=message_json,
                qos=mqtt.QoS.AT_LEAST_ONCE)
            publish_count += 1
        except Exception:
            time.sleep(args.timeout)

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if args.count != 0 and not received_all_event.is_set():
        print("Waiting for all messages to be received...")

    received_all_event.wait()
    print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")
