"""
    Ledslie, a community information display
    Copyright (C) 2017  Chotee@openended.eu

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

===========

I send incoming raw frames messages to the connected serial output.

TOPIC: ledslie.definitions.LEDSLIE_TOPIC_SERIALIZER:
MESSAGE STRUCTURE: Bytes of the frame to display. One byte per pixel. Pixel 0 is top-left, going right and down.
Value 0 is off, 255 is full brightness. Sending more or less then config.get("DISPLAY_SIZE") pixels will make the
serializer ignore the message.

"""

from zlib import crc32
import serial

import paho.mqtt.client as mqtt
from flask.config import Config

from ledslie.definitions import LEDSLIE_TOPIC_SERIALIZER

config = Config(".")

serial_port = None

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe(LEDSLIE_TOPIC_SERIALIZER)


class FakeSerial(object):
    def write(self, data):
        print("FAKE SERIAL: Would serialize %d bytes of %d now" % (len(data), crc32(data)))


def connect_serial():
    global serial_port
    if config.get('SERIAL_PORT') != "fake":
        try:
            serial_port = serial.Serial(config.get('SERIAL_PORT'), baudrate=config.get('SERIAL_BAUDRATE'))
            print("Serial port SUCCESS: %s at %s" % (config.get('SERIAL_PORT'), config.get('SERIAL_BAUDRATE')))
        except serial.serialutil.SerialException as exc:
            print("Serial port failure: %s", exc)
            serial_port = FakeSerial()
    else:
        print("running fake.")
        serial_port = FakeSerial()

def send_serial(data):
    if serial_port is None:
        connect_serial()
    serial_port.write(data)


def prepare_image(image_data):
    shifted_data = bytearray()
    shifted_data.append(1 << 7) ## start with a new frame marker, a byte with the high byte 1
    for b in image_data:
        shifted_data.append(b >> 1)  # Downshift the data one byte. making the highbyte 0.
    return shifted_data


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, mqtt_msg):
    image = mqtt_msg.payload
    data = prepare_image(image)
    if int(len(image)) != int(config.get("DISPLAY_SIZE")):
        client.publish("ledslie/logs/serializer", "WRONG message size. Expected %d but got %d." % (
            len(image), config.get("DISPLAY_SIZE")))
        return
    send_serial(data)
    client.publish("ledslie/logs/serializer", "Send image %s of %d bytes" % (
        crc32(image), len(image)))


def main():
    config.from_object('ledslie.defaults')
    config.from_envvar('LEDSLIE_CONFIG')
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(config.get('MQTT_BROKER_URL'),
                   config.get('MQTT_BROKER_PORT'),
                   config.get('MQTT_KEEPALIVE'))
    client.loop_forever()


if __name__ == '__main__':
    main()