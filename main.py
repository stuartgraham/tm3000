import os
import paho.mqtt.client as mqtt
import pendulum
from collections import deque
from statistics import mean, stdev
# from influxdb_client import InfluxDBClient, Point
# from influxdb_client.client.write_api import WriteOptions


# GLOBALS
MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
# INFLUX_HOST = os.environ['INFLUX_HOST']
# INFLUX_HOST_PORT = int(os.environ['INFLUX_HOST_PORT'])
# INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "")
# INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "")
# INFLUX_ORG = os.environ.get("INFLUX_ORG", "-")
IAQ_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_iaq/state', 'name': 'iaq'}
GAS_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_gas_resistance/state', 'name': 'gas'}
TEMP_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_temperature/state"', 'name': 'temperature'}
HUMIDITY_TOPIC = {'path': 'bathroom-sensor/sensor/bme680_humidity/state', 'name': 'humidity'}
TOPIC_LIST = [IAQ_TOPIC, GAS_TOPIC, TEMP_TOPIC, HUMIDITY_TOPIC]

IAQ_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])
GAS_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])
TEMP_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])
HUMIDITY_DEQUE = deque([0,0,0,0,0,0,0,0,0,0])

# # Set up batch write options
# BATCH_WRITE_OPTIONS = WriteOptions(batch_size=500, flush_interval=10_000, jitter_interval=2_000, retry_interval=5_000)

# # Instantiate Influx Client
# INFLUX_CLIENT = InfluxDBClient(
#     url=f"http://{INFLUX_HOST}:{INFLUX_HOST_PORT}", org=INFLUX_ORG, token=INFLUX_TOKEN
#     )
# INFLUX_WRITE_API = INFLUX_CLIENT.write_api(write_options=BATCH_WRITE_OPTIONS)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")
    for topic in TOPIC_LIST:
        client.subscribe(topic['path'])


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    timestamp = pendulum.now('Europe/London')
    value = float(msg.payload)
    topic = check_topic(msg.topic)
    print(f'MESSAGERCV: {timestamp} {topic} {value}')

    manage_deque(value, topic)


def check_topic(input_topic):
    calculated_topic = 'null'
    for topic in TOPIC_LIST:
        if topic['path'] == input_topic:
            calculated_topic = topic['name']
    return calculated_topic


def manage_deque(value, topic):
    if topic == "iaq":
        IAQ_DEQUE.pop()
        IAQ_DEQUE.appendleft(value)
        print(IAQ_DEQUE)
        print(mean(IAQ_DEQUE), stdev(IAQ_DEQUE))

    if topic == "gas":
        GAS_DEQUE.pop()
        GAS_DEQUE.appendleft(value)
        print(GAS_DEQUE)
        print(mean(GAS_DEQUE), stdev(GAS_DEQUE))

    if topic == "temperature":
        TEMP_DEQUE.pop()
        TEMP_DEQUE.appendleft(value)
        print(TEMP_DEQUE)
        print(mean(TEMP_DEQUE), stdev(TEMP_DEQUE))

    if topic == "humidity":
        HUMIDITY_DEQUE.pop()
        HUMIDITY_DEQUE.appendleft(value)
        print(HUMIDITY_DEQUE)
        print(mean(HUMIDITY_DEQUE), stdev(HUMIDITY_DEQUE))


mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  
mqttc.username_pw_set(MQTT_USER, MQTT_PASSWORD)
mqttc.on_connect = on_connect
mqttc.on_message = on_message

mqttc.connect(MQTT_HOST, MQTT_PORT, 60)

mqttc.loop_forever()