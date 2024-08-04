import os
import json
import paho.mqtt.client as mqtt
import pendulum
from collections import deque
from statistics import mean, stdev
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from urllib3 import Retry
import time

# GLOBALS
MQTT_HOST = os.environ.get('MQTT_HOST', '')
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
MQTT_USER = os.environ.get('MQTT_USER', '')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', '')
INFLUX_HOST = os.environ.get('INFLUX_HOST', '')
INFLUX_HOST_PORT = int(os.environ.get('INFLUX_HOST_PORT', 8086))
INFLUX_BUCKET = os.environ.get('INFLUX_BUCKET', '')
INFLUX_TOKEN = os.environ.get('INFLUX_TOKEN', '')
INFLUX_ORG = os.environ.get('INFLUX_ORG', '-')
NEW_SENSOR_TOPIC = 'bathroom/sensor/SENSOR'
FAN_STATE = {'path': 'climate/bathroom/extractor-fan/cmnd/power', 'name': 'fan_state'}

IAQ_DEQUE = deque([1, 1], maxlen=10)
TEMP_DEQUE = deque([1, 1], maxlen=10)
HUMIDITY_DEQUE = deque([1, 1], maxlen=10)

power_off_time = pendulum.now('Europe/London')

def build_influx_point(measurement, value, timestamp):
    base_dict = {'measurement': measurement}
    base_dict.update({'time': timestamp.isoformat()})
    base_dict.update({'fields': {'value': value}})
    return base_dict

def write_to_influx(data_payload):
    time.sleep(1)
    print("SUBMIT:" + str(data_payload))
    retries = Retry(connect=5, read=2, redirect=5)
    with InfluxDBClient(f"http://{INFLUX_HOST}:{INFLUX_HOST_PORT}", org=INFLUX_ORG, token=INFLUX_TOKEN, retries=retries) as client:
        try:
            client.write_api(write_options=SYNCHRONOUS).write(INFLUX_BUCKET, INFLUX_ORG, data_payload)
        except InfluxDBError as e:
            if e.response.status == 401:
                raise Exception(f"Insufficient write permissions to {INFLUX_BUCKET}.") from e
            raise

    data_points = len([data_payload])
    print(f"INFLUXCLIENT: {data_points} data points written to InfluxDB")
    # print('#' * 30)
    client.close()

def on_connect(client, userdata, flags, reason_code, properties):
    print(f'Connected with result code {reason_code}')
    client.subscribe(NEW_SENSOR_TOPIC)

def check_power_state():
    global power_off_time
    now = pendulum.now('Europe/London')
    if now > power_off_time:
        mqttc.publish(FAN_STATE['path'], 'OFF')
        print(f'POWEROFF: Now set to {now}. power_off_time set to {power_off_time}')
    else:
        print(f'NOACTION: Power off time is {power_off_time}. Now is {now}. ')

def power_on_extractor(minutes):
    global power_off_time
    power_off_time = pendulum.now('Europe/London') + pendulum.duration(minutes=minutes)
    mqttc.publish(FAN_STATE['path'], 'ON')
    print(f'POWERON: Powering on for {minutes} minutes. Power off scheduled at {power_off_time}')

def on_message(client, userdata, msg):
    print('#' * 30)

    check_power_state()
    timestamp = pendulum.now('Europe/London')
    payload = json.loads(msg.payload.decode())
    bme680_data = payload['BME680']

    measurements = {
        'bathroom_temperature': bme680_data['Temperature'],
        'bathroom_humidity': bme680_data['Humidity'],
        'bathroom_iaq': bme680_data['Gas']
    }
    print(f'MQTTMSG: Timestamp: {timestamp}. Data: {measurements}')
    
    influx_points = []
    for measurement, value in measurements.items():
        influx_points.append(build_influx_point(measurement, value, timestamp))
        manage_deque(measurement.split('_')[1], value)

    write_to_influx(influx_points)


def manage_deque(topic, value):
    if topic == 'temperature':
        TEMP_DEQUE.append(value)
        temp_stdev = round(stdev(TEMP_DEQUE), 2)
        temp_mean = round(mean(TEMP_DEQUE), 2)
        print(f'INFO: TEMP: {value} (STD:{temp_stdev} AVG: {temp_mean})')

    if topic == 'humidity':
        HUMIDITY_DEQUE.append(value)
        humidity_stdev = round(stdev(HUMIDITY_DEQUE), 2)
        humidity_mean = round(mean(HUMIDITY_DEQUE), 2)
        if humidity_stdev > 1 and value > humidity_mean:
            print(f'POWERON: Humidity too high. Fan on. HUMIDITY: {value} (STD:{humidity_stdev} AVG: {humidity_mean})')
            power_on_extractor(45)
        else:
            print(f'INFO: HUMIDITY: {value} (STD:{humidity_stdev} AVG: {humidity_mean})')

    if topic == 'iaq':
        IAQ_DEQUE.append(value)
        iaq_stdev = round(stdev(IAQ_DEQUE), 2)
        iaq_mean = round(mean(IAQ_DEQUE), 2)
        if iaq_stdev > 0.5 and value < iaq_mean:
            print(f'POWERON: IAQ too low. Fan on. IAQ: {value} (STD:{iaq_stdev} AVG: {iaq_mean})')
            power_on_extractor(30)
        else:
            print(f'INFO: IAQ: {value} (STD:{iaq_stdev} AVG: {iaq_mean})')

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.username_pw_set(MQTT_USER, MQTT_PASSWORD)
mqttc.on_connect = on_connect
mqttc.on_message = on_message

mqttc.connect(MQTT_HOST, MQTT_PORT, 60)

mqttc.loop_forever()