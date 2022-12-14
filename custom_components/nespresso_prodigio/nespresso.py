import asyncio
import ctypes
import logging
import uuid
from enum import Enum
from typing import Union

import binascii
from bleak import BleakClient, BLEDevice, BleakScanner, BleakGATTCharacteristic

_LOGGER = logging.getLogger(__name__)

c_uint8 = ctypes.c_uint8

CHAR_UUID_MANUFACTURER_NAME = "06aa3a41-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_STATUS = "06aa3a12-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_NBCAPS = "06aa3a15-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_SLIDER = "06aa3a22-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_WATER_HARDNESS = "06aa3a44-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_AUTH = "06aa3a41-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_COMMAND = "06aa3a42-f22a-11e3-9daa-0002a5d5c51b"
CHAR_UUID_SERVICE = "06aa1910-f22a-11e3-9daa-0002a5d5c51b"

RETRIES_NUMBER = 5
SLEEP_TIME = 5


class NespressoVolume(Enum):
    RISTRETTO = "Ristretto"
    ESPRESSO = "Espresso"
    LUNGO = "Lungo"


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


BYTE = Flags()


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
    str(CHAR_UUID_STATUS): BaseDecode(name="state", format_type="state"),
    str(CHAR_UUID_NBCAPS): BaseDecode(name="caps_number", format_type="caps_number"),
    str(CHAR_UUID_SLIDER): BaseDecode(name="slider", format_type="slider"),
    str(CHAR_UUID_WATER_HARDNESS): BaseDecode(
        name="water_hardness", format_type="water_hardness"
    ),
}


class BLEClientWrapper:
    def __init__(self, device: BLEDevice, auth_code: str):
        self._device = device
        self._client = BleakClient(self._device)
        self._auth_code = auth_code
        self._authenticated = False
        self._connected = False

    @property
    async def services(self):
        client = await self._get_client()
        return client.services

    async def _authenticate(self, retries=RETRIES_NUMBER):
        if not self._authenticated:
            client = self._client
            try:
                await client.write_gatt_char(
                    CHAR_UUID_AUTH, binascii.unhexlify(self._auth_code), True
                )
            except Exception as e:
                if retries > 0:
                    self.validate_connection(e)
                    _LOGGER.warning(
                        "Authentication failed. Attempts left {}\n{}".format(
                            retries, str(e)
                        )
                    )
                    await asyncio.sleep(SLEEP_TIME)
                    return await self._authenticate(retries - 1)
                else:
                    raise e
            self._authenticated = True
            _LOGGER.debug(
                "Successfully authenticated to bluetooth client {}".format(
                    self._authenticated
                )
            )

    def validate_connection(self, e: Exception):
        if str(e) == "Disconnected" or str(e) == "Not connected":
            self._connected = False
        if str(e).endswith("Insufficient authentication"):
            self._authenticated = False

    async def _get_client(self, retries=RETRIES_NUMBER):
        if not self._client.is_connected or not self._connected:
            try:
                self._authenticated = False
                _LOGGER.debug("Connecting to bluetooth device")
                await self._client.connect()
                if not self._client.is_connected:
                    raise Exception("Bluetooth connection failed")
                self._connected = True
                _LOGGER.debug(
                    "Successfully connected to bluetooth client {}".format(
                        self._client.is_connected
                    )
                )
            except Exception as e:
                if retries > 0:
                    self.validate_connection(e)
                    _LOGGER.warning(
                        "Connection reset, attempting reconnect. Attempts left {}\n{}".format(
                            retries, str(e)
                        )
                    )
                    await asyncio.sleep(SLEEP_TIME)
                    return await self._get_client(retries - 1)
                else:
                    raise e
        if not self._authenticated:
            await self._authenticate()

        return self._client

    async def read_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        retries=RETRIES_NUMBER,
        **kwargs,
    ) -> bytearray:
        client = await self._get_client()
        try:
            return await client.read_gatt_char(char_specifier, **kwargs)
        except Exception as e:
            if retries > 0:
                self.validate_connection(e)
                _LOGGER.warning(
                    "Read gatt char error. Attempts left {}\n{}".format(retries, str(e))
                )
                await asyncio.sleep(SLEEP_TIME)
                return await self.read_gatt_char(char_specifier, retries - 1, **kwargs)
            else:
                raise e

    async def read_gatt_descriptor(
        self, handle: int, retries=RETRIES_NUMBER, **kwargs
    ) -> bytearray:
        client = await self._get_client()
        try:
            return await client.read_gatt_descriptor(handle, **kwargs)
        except Exception as e:
            if retries > 0:
                self.validate_connection(e)
                _LOGGER.warning(
                    "Read gatt descriptor error. Attempts left {}\n{}".format(
                        retries, str(e)
                    )
                )
                await asyncio.sleep(SLEEP_TIME)
                return await self.read_gatt_descriptor(handle, retries - 1, **kwargs)
            else:
                raise e

    async def write_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        data: Union[bytes, bytearray, memoryview],
        response: bool = False,
        retries=RETRIES_NUMBER,
    ) -> None:
        client = await self._get_client()
        try:
            return await client.write_gatt_char(char_specifier, data, response)
        except Exception as e:
            if retries > 0:
                self.validate_connection(e)
                _LOGGER.warning(
                    "Write gatt char error. Attempts left {}\n{}\n{}".format(
                        retries, str(e), self._client.is_connected
                    )
                )
                await asyncio.sleep(SLEEP_TIME)
                return await self.write_gatt_char(
                    char_specifier, data, response, retries - 1
                )
            else:
                raise e


class BLEClientPool:
    def __init__(self, auth_code: str):
        self._auth_code = auth_code
        self._clients = {}

    def get_client(self, device: BLEDevice) -> BLEClientWrapper:
        client = self._clients.get(device.address)
        if client is None:
            client = BLEClientWrapper(device, self._auth_code)
            self._clients[device.address] = client
        return client


class NespressoDeviceBundle:
    def __init__(self, device: BLEDevice, attributes: dict):
        self.device = device
        self.attributes = attributes
        self.selected_volume: NespressoVolume = None


class NespressoClient:
    def __init__(self, scanner: BleakScanner, auth_code: str) -> None:
        """Sample API Client."""
        self._scanner = scanner
        self.bundles: list[NespressoDeviceBundle] = []
        self._client_pool = BLEClientPool(auth_code)

    async def discover_nespresso_devices(self):
        # Scan for devices and try to figure out if it is a Nespresso device.
        await self._scanner.discover()
        discovered_devices = self._scanner.discovered_devices

        if discovered_devices is not None:
            for device in discovered_devices:
                if str(device.name).startswith("Prodigio"):
                    _LOGGER.debug(
                        "Found nespresso_prodigio device {}".format(device.address)
                    )
                    self.bundles.append(NespressoDeviceBundle(device, {}))
            _LOGGER.debug("Found {} Nespresso devices".format(len(self.bundles)))

    async def get_device_data(self):
        for bundle in self.bundles:
            device = bundle.device
            client = self._client_pool.get_client(device)
            services = await client.services
            if services is not None:
                for service in services:
                    characteristics = service.characteristics
                    if characteristics is None:
                        continue
                    for characteristic in service.characteristics:
                        _LOGGER.debug("characteristic {}".format(characteristic))
                        if characteristic.uuid in sensor_decoders:
                            characteristic_data = await client.read_gatt_char(
                                characteristic.uuid
                            )
                            _LOGGER.debug(
                                "{} data {}".format(
                                    characteristic.uuid, characteristic_data
                                )
                            )
                            decoded_data = sensor_decoders[
                                characteristic.uuid
                            ].decode_data(characteristic_data)
                            _LOGGER.debug(
                                "{} Got sensordata {}".format(
                                    device.address, decoded_data
                                )
                            )
                            bundle.attributes = {**bundle.attributes, **decoded_data}

    async def cancel_coffee(self, device: BLEDevice):
        pass

    async def make_coffee(
        self, device: BLEDevice, volume: NespressoVolume = NespressoVolume.LUNGO
    ):
        _LOGGER.debug("make flow a coffee")
        client = self._client_pool.get_client(device)
        command = "0305070400000000"
        command += "00"
        if volume == NespressoVolume.ESPRESSO:
            command += "01"
        elif volume == NespressoVolume.LUNGO:
            command += "02"
        elif volume == NespressoVolume.RISTRETTO:
            command += "00"
        else:
            command += "00"
        await client.write_gatt_char(
            CHAR_UUID_COMMAND, binascii.unhexlify(command), True
        )


async def main():
    logging.basicConfig()
    _LOGGER.setLevel(logging.INFO)
    async with BleakScanner() as scanner:
        client = NespressoClient(scanner, "87302f3c2b62e4f0")
        await client.discover_nespresso_devices()
        for bundle in client.bundles:
            device = bundle.device
            _LOGGER.info("{}".format(device))

        await client.get_device_data()
        for bundle in client.bundles:
            device = bundle.device
            for name, val in bundle.attributes.items():
                _LOGGER.info("{}: {}: {}".format(device.address, name, val))


if __name__ == "__main__":
    asyncio.run(main())
