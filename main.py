import os
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
IAQ_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_iaq/state', 'name': 'iaq'}
GAS_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_gas_resistance/state', 'name': 'gas'}
TEMP_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_temperature/state', 'name': 'temperature'}
HUMIDITY_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_humidity/state', 'name': 'humidity'}
FAN_STATE = {'path': 'climate/bathroom/extractor-fan/cmnd/power', 'name': 'fan_state'}
TOPIC_LIST = [IAQ_TOPIC, GAS_TOPIC, TEMP_TOPIC, HUMIDITY_TOPIC]

IAQ_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])
GAS_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])
TEMP_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])
HUMIDITY_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])

global power_off_time
power_off_time = pendulum.now()


def build_influx_point(topic, value, timestamp):
    measurement = ''
    if topic == 'iaq':
        measurement = 'bathroom_iaq'
    
    if topic == 'humidity':
        measurement = 'bathroom_humidity'

    if topic == 'temperature':
        measurement = 'bathroom_temperature'

    if topic == 'gas':
        measurement = 'bathroom_voc'

    base_dict = {'measurement' : measurement}
    base_dict.update({'time': timestamp.isoformat()})
    base_dict.update({'fields' : {'value' : value}}) 
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
    print(f"SUCCESS: {data_points} data points written to InfluxDB")
    print('#'*30)
    client.close()


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    print(f'Connected with result code {reason_code}')
    for topic in TOPIC_LIST:
        client.subscribe(topic['path'])


def check_power_state():
    now = pendulum.now()
    if now > power_off_time:
        mqttc.publish(FAN_STATE['path'], 'OFF')
        print(f'POWEROFF: Now set to {now}. power_off_time set to {power_off_time}')
        print('#'*30)


def power_on_extractor(time):
    power_off_time = pendulum.now() + pendulum.duration(minutes=time)
    mqttc.publish(FAN_STATE['path'], 'ON')
    print(f'POWERON: Powering on for {time} minutes')
    print(f'POWERON: Powering off scheduled at {power_off_time}')
    print('#'*30)


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    check_power_state()
    timestamp = pendulum.now('Europe/London')
    value = float(msg.payload)
    topic = check_topic(msg.topic)
    manage_deque(topic, value)
    influx_point = build_influx_point(topic, value, timestamp)
    write_to_influx(influx_point)

    print(f'MESSAGERCV: {timestamp} {topic} {value}')


def check_topic(input_topic):
    calculated_topic = 'null'
    for topic in TOPIC_LIST:
        if topic['path'] == input_topic:
            calculated_topic = topic['name']
    return calculated_topic


def manage_deque(topic, value):    
    if topic == 'iaq':
        IAQ_DEQUE.pop()
        IAQ_DEQUE.appendleft(value)
        iaq_mean = mean(IAQ_DEQUE)
        iaq_mean = round(iaq_mean, 2)
        iaq_stdev = stdev(IAQ_DEQUE)
        iaq_stdev = round(iaq_stdev, 2)
        if iaq_stdev > 5 and value > iaq_mean:
            print(f'POWERON: Fan on. IAQ: {value}. STDEV: {iaq_stdev}. MEAN: {iaq_mean}')
            print('#'*30)
            power_on_extractor(30)
        else:
            print(f'NOACTION: IAQ: {value}. STDEV: {iaq_stdev}. MEAN: {iaq_mean}')
            print('#'*30)


    if topic == 'gas':
        GAS_DEQUE.pop()
        GAS_DEQUE.appendleft(value)
        gas_stdev = stdev(GAS_DEQUE)
        gas_stdev = round(gas_stdev, 2)
        gas_mean = mean(GAS_DEQUE)
        gas_mean = round(gas_mean, 2)
        print(f'NOACTION: VOC: {value}. STDEV: {gas_stdev}. MEAN: {gas_mean}')
        print('#'*30)


    if topic == 'temperature':
        TEMP_DEQUE.pop()
        TEMP_DEQUE.appendleft(value)
        temp_stdev = stdev(TEMP_DEQUE)
        temp_stdev = round(temp_stdev, 2)
        temp_mean = mean(TEMP_DEQUE)
        temp_mean = round(temp_mean, 2)
        print(f'NOACTION: TEMP: {value}. STDEV: {temp_stdev}. MEAN: {temp_mean}')
        print('#'*30)


    if topic == 'humidity':
        HUMIDITY_DEQUE.pop()
        HUMIDITY_DEQUE.appendleft(value)
        humidity_stdev = stdev(HUMIDITY_DEQUE)
        humidity_stdev = round(humidity_stdev, 2)
        humidity_mean = mean(HUMIDITY_DEQUE)
        humidity_mean = round(humidity_mean, 2)
        if humidity_stdev > 5 and value > humidity_mean:
            print(f'POWERON: Fan on. HUMIDITY: {value}. STDEV: {humidity_stdev}. MEAN: {humidity_mean}')
            print('#'*30)
            power_on_extractor(45)
        else:
            print(f'NOACTION: HUMIDITY: {value}. STDEV: {humidity_stdev}. MEAN: {humidity_mean}')
            print('#'*30)


mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  
mqttc.username_pw_set(MQTT_USER, MQTT_PASSWORD)
mqttc.on_connect = on_connect
mqttc.on_message = on_message

mqttc.connect(MQTT_HOST, MQTT_PORT, 60)

mqttc.loop_forever()