import asyncio
import ctypes
import inspect
import logging
import time
import uuid
from collections import namedtuple
from typing import Coroutine, Union

import binascii
from bleak import BleakClient, BLEDevice, BleakScanner, BleakGATTCharacteristic

_LOGGER = logging.getLogger(__name__)

CHAR_UUID_MANUFACTURER_NAME = "06aa3a41-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_STATE = "06aa3a12-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_NBCAPS = "06aa3a15-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_SLIDER = "06aa3a22-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_WATER_HARDNESS = "06aa3a44-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_AUTH = "06aa3a41-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_COMMAND = "06aa3a42-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_SERVICE = "06aa1910-f22a-11e3-9daa-0002a5d5c51b"

Characteristic = namedtuple("Characteristic", ["uuid", "name", "format"])

c_uint8 = ctypes.c_uint8


class FlagsBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("bit0", c_uint8, 1),  # asByte & 1
        ("bit1", c_uint8, 1),  # asByte & 2
        ("bit2", c_uint8, 1),  # asByte & 4
        ("bit3", c_uint8, 1),  # asByte & 8
        ("bit4", c_uint8, 1),  # asByte & 16
        ("bit5", c_uint8, 1),  # asByte & 32
        ("bit6", c_uint8, 1),  # asByte & 64
        ("bit7", c_uint8, 1),  # asByte & 128
    ]


class Flags(ctypes.Union):
    _anonymous_ = ("bit",)
    _fields_ = [("bit", FlagsBits), ("asByte", c_uint8)]


class NespressoDeviceInfo:
    def __init__(self, manufacturer="", serial_nr="", model_nr="", device_name=""):
        self.manufacturer = manufacturer
        self.serial_nr = serial_nr
        self.model_nr = model_nr
        self.device_name = device_name

    def __str__(self):
        return "Manufacturer: {} Model: {} Serial: {} Device:{}".format(
            self.manufacturer, self.model_nr, self.serial_nr, self.device_name
        )


BYTE = Flags()
sensors_characteristics_uuid = [
    CHAR_UUID_STATE,
    CHAR_UUID_NBCAPS,
    CHAR_UUID_SLIDER,
    CHAR_UUID_WATER_HARDNESS,
]

sensors_characteristics_uuid_str = [str(x) for x in sensors_characteristics_uuid]


class BaseDecode:
    def __init__(self, name, format_type):
        self.name = name
        self.format_type = format_type

    def decode_data(self, raw_data):
        # val = struct.unpack(self.format_type,raw_data)
        val = raw_data
        if self.format_type == "caps_number":
            res = int.from_bytes(val, byteorder="big")
        elif self.format_type == "water_hardness":
            res = int.from_bytes(val[2:3], byteorder="big")
        elif self.format_type == "slider":
            res = binascii.hexlify(val)
            if res == b"00":
                res = 0
                # res = 'on'
            elif res == b"02":
                res = 1
                # res = 'off'
            else:
                res = "N/A"
        elif self.format_type == "state":
            byte0 = Flags()
            byte1 = Flags()
            byte2 = Flags()
            byte3 = Flags()

            byte0.asByte = val[0]
            byte1.asByte = val[1] if len(val) > 1 else 0
            byte2.asByte = val[2] if len(val) > 2 else 0
            byte3.asByte = val[3] if len(val) > 3 else 0
            try:
                descaling_counter = int.from_bytes(val[6:9], byteorder="big")
            except Exception as e:
                _LOGGER.debug("can't get descaling counter", e)
                descaling_counter = 0
            return {
                "water_is_empty": byte0.bit0,
                "descaling_needed": byte0.bit2,
                "capsule_mechanism_jammed": byte0.bit4,
                "always_1": byte0.bit6,
                "water_temp_low": byte1.bit0,
                "awake": byte1.bit1,
                "water_engadged": byte1.bit2,
                "sleeping": byte1.bit3,
                "tray_sensor_during_brewing": byte1.bit4,
                "tray_open_tray_sensor_full": byte1.bit6,
                "capsule_engaged": byte1.bit7,
                "Fault": byte3.bit5,
                "descaling_counter": descaling_counter,
            }
        else:
            _LOGGER.debug("state_decoder else")
            res = val
        return {self.name: res}


sensor_decoders = {
    str(CHAR_UUID_STATE): BaseDecode(name="state", format_type="state"),
    str(CHAR_UUID_NBCAPS): BaseDecode(name="caps_number", format_type="caps_number"),
    str(CHAR_UUID_SLIDER): BaseDecode(name="slider", format_type="slider"),
    str(CHAR_UUID_WATER_HARDNESS): BaseDecode(
        name="water_hardness", format_type="water_hardness"
    ),
}

RETRIES_NUMBER = 3
SLEEP_TIME = 3


class BLEClientWrapper:
    def __init__(self, device: BLEDevice):
        self._device = device
        self._client = BleakClient(self._device, self._disconnected_callback)

    @property
    async def services(self):
        client = await self._get_client()
        return client.services

    def _disconnected_callback(self: BleakClient):
        self.connect()

    async def _get_client(self, retries=RETRIES_NUMBER):
        if not self._client.is_connected:
            try:
                await self._client.connect()
                if not self._client.is_connected:
                    raise Exception("Bluetooth connection failed")
            except Exception as e:
                if retries > 0:
                    await asyncio.sleep(SLEEP_TIME)
                    return await self._get_client(retries - 1)
                else:
                    raise e
        return self._client

    async def read_gatt_descriptor(self, handle: int, retries=RETRIES_NUMBER, **kwargs) -> bytearray:
        client = await self._get_client()
        try:
            return await client.read_gatt_descriptor(
                handle, **kwargs
            )
        except Exception as e:
            if retries > 0:
                await asyncio.sleep(SLEEP_TIME)
                return await self.read_gatt_descriptor(handle, retries - 1, **kwargs)
            else:
                raise e

    async def write_gatt_char(
            self,
            char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
            data: Union[bytes, bytearray, memoryview],
            response: bool = False,
            retries=RETRIES_NUMBER
    ) -> None:
        client = await self._get_client()
        try:
            return await client.write_gatt_char(
                char_specifier, data, response
            )
        except Exception as e:
            if retries > 0:
                await asyncio.sleep(SLEEP_TIME)
                return await client.write_gatt_char(
                    char_specifier, data, response, retries - 1
                )
            else:
                raise e


class BLEClientPool:
    def __init__(self):
        self._clients = {}

    def get_client(self, device: BLEDevice) -> BLEClientWrapper:
        client = self._clients.get(device.address)
        if client is None:
            client = BLEClientWrapper(device)
            self._clients[device.address] = client
        return client


class NespressoClient:
    def __init__(self, scanner: BleakScanner, auth_code: str) -> None:
        """Sample API Client."""
        self._scanner = scanner
        self._auth_code = auth_code
        self.devices = []
        self._client_pool = BLEClientPool()

    async def _authenticate(self, client: BLEClientWrapper, tries=0):
        try:
            # Write the auth code from android or Ios apps to the specific UUID to allow catching value from the machine
            await client.write_gatt_char(
                CHAR_UUID_AUTH, binascii.unhexlify(self._auth_code), True
            )
        except Exception as e:
            _LOGGER.exception("Failed to send auth code, retrying in 5s", e)
            time.sleep(5)  # wait 5s
            if tries < 3:
                _LOGGER.exception("Failed to send auth code, 3 times")
                await self._authenticate(client, tries + 1)  # retry
            else:
                _LOGGER.exception("Failed to send auth code, more than 3 times")

    async def discover_nespresso_devices(self):
        # Scan for devices and try to figure out if it is an Nespresso device.
        await self._scanner.discover()
        discovered_devices = self._scanner.discovered_devices

        self.devices = []

        for device in discovered_devices:
            if CHAR_UUID_SERVICE in device.metadata.get("uuids"):
                _LOGGER.debug("Found nespresso_prodigio device {}".format(device.address))
                device.attributes = {}
                self.devices.append(device)
        _LOGGER.debug("Found {} Nespresso devices".format(len(self.devices)))

    async def get_device_data(self):
        for device in self.devices:
            try:
                client = self._client_pool.get_client(device)
                services = await client.services
                for service in services:
                    for characteristic in service.characteristics:
                        _LOGGER.debug("characteristic {}".format(characteristic))
                        try:
                            for descriptor in characteristic.descriptors:
                                descriptor_data = await client.read_gatt_descriptor(
                                    descriptor.handle
                                )
                                if characteristic.uuid in sensor_decoders:
                                    _LOGGER.debug(
                                        "{} data {}".format(
                                            characteristic.uuid, descriptor_data
                                        )
                                    )
                                    decoded_data = sensor_decoders[
                                        characteristic.uuid
                                    ].decode_data(descriptor_data)
                                    _LOGGER.debug(
                                        "{} Got sensordata {}".format(
                                            device.address, decoded_data
                                        )
                                    )
                                    device.attributes = decoded_data
                        except Exception as e:
                            _LOGGER.exception("Failed to read characteristic", e)
            except Exception as e:
                _LOGGER.exception("Failed to discover sensors", e)

    async def cancel_coffee(self, device: BLEDevice):
        print()

    async def make_coffee(self, device: BLEDevice, volume="lungo"):
        try:
            _LOGGER.debug("make flow a coffee")
            client = self._client_pool.get_client(device)
            await self._authenticate(client)
            try:
                command = "0305070400000000"
                # TODO when temp will be used for other machine
                command += "00"
                if volume == "espresso":
                    command += "01"
                elif volume == "lungo":
                    command += "02"
                elif volume == "ristretto":
                    command += "00"
                else:
                    command += "00"
                await client.write_gatt_char(
                    CHAR_UUID_COMMAND, binascii.unhexlify(command), True
                )
            except Exception as e:
                _LOGGER.exception("Failed to write characteristic for coffee flow", e)
        except Exception as e:
            _LOGGER.exception("Failed to connect for coffee flow", e)


async def main():
    logging.basicConfig()
    _LOGGER.setLevel(logging.INFO)
    async with BleakScanner() as scanner:
        client = NespressoClient(scanner, "87302f3c2b62e4f0")
        await client.discover_nespresso_devices()
        for dev in client.devices:
            await client.make_coffee(dev)
            _LOGGER.info("{}".format(dev))

        await client.get_device_data()
        for device in client.devices:
            for name, val in device.attributes.items():
                _LOGGER.info("{}: {}: {}".format(device.address, name, val))


if __name__ == "__main__":
    asyncio.run(main())
