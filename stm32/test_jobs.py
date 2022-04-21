# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt import auth, http, io, mqtt
from awsiot import iotjobs
from awsiot import mqtt_connection_builder
from concurrent.futures import Future
import sys
import threading
import time
import os
import subprocess
import traceback
from uuid import uuid4
from dotenv import load_dotenv

# - Overview -
# This sample uses the AWS IoT Jobs Service to receive and execute operations
# on the device. Imagine periodic software updates that must be sent to and
# executed on devices in the wild.
#
# - Instructions -
# This sample requires you to create jobs for your device to execute. See:
# https://docs.aws.amazon.com/iot/latest/developerguide/create-manage-jobs.html
#
# - Detail -
# On startup, the sample tries to start the next pending job execution.
# If such a job exists, the sample emulates "doing work" by spawning a thread
# that sleeps for several seconds before marking the job as SUCCEEDED. When no
# pending job executions exist, the sample sits in an idle state.
#
# The sample also subscribes to receive "Next Job Execution Changed" events.
# If the sample is idle, this event wakes it to start the job. If the sample is
# already working on a job, it remembers to try for another when it's done.
# This event is sent by the service when the current job completes, so the
# sample will be continually prompted to try another job until none remain.
load_dotenv()

# Using globals to simplify sample code
is_sample_done = threading.Event()

mqtt_connection = None
jobs_client = None
thing_name = os.getenv('THING_NAME')

class LockedData:
    def __init__(self):
        self.lock = threading.Lock()
        self.disconnect_called = False
        self.is_working_on_job = False
        self.is_next_job_waiting = False

locked_data = LockedData()

processes = {}

# Function for gracefully quitting this sample
def exit(msg_or_exception):
    if isinstance(msg_or_exception, Exception):
        print("Exiting Sample due to exception.")
        traceback.print_exception(msg_or_exception.__class__, msg_or_exception, sys.exc_info()[2])
    else:
        print("Exiting Sample:", msg_or_exception)

    with locked_data.lock:
        if not locked_data.disconnect_called:
            print("Disconnecting...")
            locked_data.disconnect_called = True
            future = mqtt_connection.disconnect()
            future.add_done_callback(on_disconnected)

def try_start_next_job():
    print("Trying to start the next job...")
    with locked_data.lock:
        if locked_data.is_working_on_job:
            print("Nevermind, already working on a job.")
            return

        if locked_data.disconnect_called:
            print("Nevermind, sample is disconnecting.")
            return

        locked_data.is_working_on_job = True
        locked_data.is_next_job_waiting = False

    print("Publishing request to start next job...")
    request = iotjobs.StartNextPendingJobExecutionRequest(thing_name=os.getenv('THING_NAME'))
    publish_future = jobs_client.publish_start_next_pending_job_execution(request, mqtt.QoS.AT_LEAST_ONCE)
    publish_future.add_done_callback(on_publish_start_next_pending_job_execution)

def done_working_on_job():
    with locked_data.lock:
        locked_data.is_working_on_job = False
        try_again = locked_data.is_next_job_waiting

    if try_again:
        try_start_next_job()

def on_disconnected(disconnect_future):
    # type: (Future) -> None
    print("Disconnected.")

    # Signal that sample is finished
    is_sample_done.set()

def on_next_job_execution_changed(event):
    # type: (iotjobs.NextJobExecutionChangedEvent) -> None
    try:
        execution = event.execution
        if execution:
            print("Received Next Job Execution Changed event. job_id:{} job_document:{}".format(
                execution.job_id, execution.job_document))

            # Start job now, or remember to start it when current job is done
            start_job_now = False
            with locked_data.lock:
                if locked_data.is_working_on_job:
                    locked_data.is_next_job_waiting = True
                else:
                    start_job_now = True

            if start_job_now:
                try_start_next_job()

        else:
            print("Received Next Job Execution Changed event: None. Waiting for further jobs...")

    except Exception as e:
        exit(e)

def on_publish_start_next_pending_job_execution(future):
    # type: (Future) -> None
    try:
        future.result() # raises exception if publish failed

        print("Published request to start the next job.")

    except Exception as e:
        exit(e)

def on_start_next_pending_job_execution_accepted(response):
    # type: (iotjobs.StartNextJobExecutionResponse) -> None
    try:
        if response.execution:
            execution = response.execution
            print("Request to start next job was accepted. job_id:{} job_document:{}".format(
                execution.job_id, execution.job_document))

            # To emulate working on a job, spawn a thread that sleeps for a few seconds
            job_thread = threading.Thread(
                target=lambda: job_thread_fn(execution.job_id, execution.job_document),
                name='job_thread')
            job_thread.start()
        else:
            print("Request to start next job was accepted, but there are no jobs to be done. Waiting for further jobs...")
            done_working_on_job()

    except Exception as e:
        exit(e)

def on_start_next_pending_job_execution_rejected(rejected):
    # type: (iotjobs.RejectedError) -> None
    exit("Request to start next pending job rejected with code:'{}' message:'{}'".format(
        rejected.code, rejected.message))

def job_thread_fn(job_id, job_document):
    try:
        print("Starting local work on job...")
        if job_id == RPi_Address:
            os.Popen(['python', 'publishRPiIP.py'])
        print("Done working on job.")

        print("Publishing request to update job status to SUCCEEDED...")
        request = iotjobs.UpdateJobExecutionRequest(
            thing_name=os.getenv('THING_NAME'),
            job_id=job_id,
            status=iotjobs.JobStatus.SUCCEEDED)
        publish_future = jobs_client.publish_update_job_execution(request, mqtt.QoS.AT_LEAST_ONCE)
        publish_future.add_done_callback(on_publish_update_job_execution)

    except Exception as e:
        exit(e)

def on_publish_update_job_execution(future):
    # type: (Future) -> None
    try:
        future.result() # raises exception if publish failed
        print("Published request to update job.")

    except Exception as e:
        exit(e)

def on_update_job_execution_accepted(response):
    # type: (iotjobs.UpdateJobExecutionResponse) -> None
    try:
        print("Request to update job was accepted.")
        done_working_on_job()
    except Exception as e:
        exit(e)

def on_update_job_execution_rejected(rejected):
    # type: (iotjobs.RejectedError) -> None
    exit("Request to update job status was rejected. code:'{}' message:'{}'.".format(
        rejected.code, rejected.message))

def setup_job_listener(mqtt_connection):
    global jobs_client
    jobs_client = iotjobs.IotJobsClient(mqtt_connection)
    try:
        # Subscribe to necessary topics.
        # Note that is **is** important to wait for "accepted/rejected" subscriptions
        # to succeed before publishing the corresponding "request".
        print("Subscribing to Next Changed events...")
        changed_subscription_request = iotjobs.NextJobExecutionChangedSubscriptionRequest(
            thing_name=os.getenv('THING_NAME')
        )

        subscribed_future, _ = jobs_client.subscribe_to_next_job_execution_changed_events(
            request=changed_subscription_request,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_next_job_execution_changed)

        # Wait for subscription to succeed
        subscribed_future.result()

        print("Subscribing to Start responses...")
        start_subscription_request = iotjobs.StartNextPendingJobExecutionSubscriptionRequest(
            thing_name=os.getenv('THING_NAME')
        )
        subscribed_accepted_future, _ = jobs_client.subscribe_to_start_next_pending_job_execution_accepted(
            request=start_subscription_request,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_start_next_pending_job_execution_accepted)

        subscribed_rejected_future, _ = jobs_client.subscribe_to_start_next_pending_job_execution_rejected(
            request=start_subscription_request,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_start_next_pending_job_execution_rejected)

        # Wait for subscriptions to succeed
        subscribed_accepted_future.result()
        subscribed_rejected_future.result()

        print("Subscribing to Update responses...")
        # Note that we subscribe to "+", the MQTT wildcard, to receive
        # responses about any job-ID.
        update_subscription_request = iotjobs.UpdateJobExecutionSubscriptionRequest(
            thing_name=os.getenv('THING_NAME'),
            job_id='+'
        )

        subscribed_accepted_future, _ = jobs_client.subscribe_to_update_job_execution_accepted(
            request=update_subscription_request,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_update_job_execution_accepted)

        subscribed_rejected_future, _ = jobs_client.subscribe_to_update_job_execution_rejected(
            request=update_subscription_request,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_update_job_execution_rejected)

        # Wait for subscriptions to succeed
        subscribed_accepted_future.result()
        subscribed_rejected_future.result()

        # Make initial attempt to start next job. The service should reply with
        # an "accepted" response, even if no jobs are pending. The response
        # will contain data about the next job, if there is one.
        try_start_next_job()

    except Exception as e:
        exit(e)

if __name__ == '__main__':
    CLIENT_ID = 'test' + str(uuid4())

    # Process input args
    thing_name = os.getenv('THING_NAME')

    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=os.getenv('AWS_ENDPOINT'),
        cert_filepath=os.getenv('CERT_FILE'),
        pri_key_filepath=os.getenv('PRI_KEY_FILE'),
        client_bootstrap=client_bootstrap,
        ca_filepath=os.getenv('ROOT_CA_FILE'),
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
        http_proxy_options=None)

    print(f"Connecting to {os.getenv('AWS_ENDPOINT')} with client ID '{CLIENT_ID}'...")

    connected_future = mqtt_connection.connect()
    connected_future.result()
    print("Connected!")

    # processes['publishProcess'] = subprocess.Popen(
    #     ['/usr/bin/python', 
    #     '/home/pi/DairyCattleRaspberryPi/stm32/publishFakeData.py'])

    setup_job_listener(mqtt_connection)