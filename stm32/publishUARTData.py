# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from uuid import uuid4
from awscrt import io, mqtt, exceptions
from awsiot import mqtt_connection_builder
from dotenv import load_dotenv
import json
import os
import platform
import re
import serial
import serial.tools.list_ports
import sys
import threading
import time


# Load local configuration settings
# a .env file must be located in the directory and include definitions for:
# AWS_ENDPOINT, CERT_FILE, PRI_KEY_FILE, and ROOT_CA_FILE as 
load_dotenv()

# Searches for available ports for UART (i.e. /dev/ttyACM0, /dev/ttyACM1)
# If there are multiple, defaults to the first one
ports = list(serial.tools.list_ports.grep('ACM'))
if len(ports) == 0:
    print('Cannot find UART port, exiting...')
    exit(-1)
UART_PORT = ports[0].device
BAUD_RATE = 115200
# Initialize the UART connection
ser = serial.Serial(port=UART_PORT, baudrate=BAUD_RATE)

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

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




def parse_lora_packet(packet_str):
    map_message_ids = {
        'I': {
            'cast_func': int,
            'full_name': 'Device_ID'
        },
        'T': {
            'cast_func': float,
            'full_name': 'Temperature'
        },
        'A': {
            'cast_func': str,
            'full_name': 'Acceleration'
        }
    }
    # Goal is to split a string with letters and data into two lists to build
    # a dictionary from the packet. i.e. I08 T34.1 A1.16 -1.91 becomes
    # {'Device_Id': 08, 'Temperature': 34.1, 'Acceleration': 1.16, -1.91}

    # 'I08 T34.1 A1.16 -1.91' -> [('I', '08'), ('T', '34.1 '), ('A', '1.16 -1.91)]
    data_points = re.findall(r'([a-zA-Z])+([^(a-zA-Z\n)]*)', packet_str) 
    # Build a dictionary by mapping letters to full labels and casting data based on given cast_func in map above
    return {map_message_ids[label]['full_name']: map_message_ids[label]['cast_func'](data) for label, data in data_points}


if __name__ == '__main__':
    CLIENT_ID = 'test' + str(uuid4())
    TOPIC = 'test/temp'
    TIMEOUT = 5

    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)



    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint= os.getenv('AWS_ENDPOINT'),
        cert_filepath= os.getenv('CERT_FILE'),
        pri_key_filepath= os.getenv('PRI_KEY_FILE'),
        client_bootstrap=client_bootstrap,
        ca_filepath= os.getenv('ROOT_CA_FILE'),
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
        http_proxy_options=None)

    print("Connecting to {} with client ID '{}'...".format(
        os.getenv('AWS_ENDPOINT'), CLIENT_ID))

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

    while True:
        # try:
            data = parse_lora_packet(str(ser.readline(), 'utf8'))
            message = {
                'Device_ID': data.pop('Device_ID'),
                'Data': data
            }
            print("Publishing message to topic '{}': {}".format(TOPIC, message))
            message_json = json.dumps(message)
            mqtt_connection.publish(
                topic=TOPIC,
                payload=message_json,
                qos=mqtt.QoS.AT_LEAST_ONCE)
        # except Exception:
        #     print('Exception occured, retrying...')
        #     time.sleep(TIMEOUT)

