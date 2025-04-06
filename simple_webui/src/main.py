from aerospacejam import AerospaceJamServer, response_html, response_json
import time
from mfrc522 import MFRC522
import machine, onewire, ds18x20
from machine import UART, Pin
import utime
from binascii import hexlify

WIFI_CONFIG = {
    'ssid': 'Ariel Archictects', # You should change these two lines!
    'password': 'Gleason123',
    'static_ip': '192.168.4.1',
    'subnet_mask': '255.255.255.0',
    'gateway': '192.168.4.1',
    'dns': '192.168.4.1'
}

# Initialize the server with your Wi-Fi configuration
pico_server = AerospaceJamServer(WIFI_CONFIG)

# Register a sensor - this is a dummy sensor
pico_server.register_sensor("dummy", lambda: 25 + (time.time() % 10))
reader = MFRC522(spi_id=0,sck=6,miso=4,mosi=7,cs=5,rst=22)

# Register a path that prints a message when a GET request is made
def hello_handler(request):
    print("Someone said hello!")
    return response_html("<h1>Hello, world!</h1>")
pico_server.register_path('/hello', hello_handler)


ds_sensor = ds18x20.DS18X20(
    onewire.OneWire(
        machine.Pin(21)
    )
)
roms = ds_sensor.scan()
if len(roms) == 0:
    print("No thermometer found!")

def get_temp(unit: str="F") -> float:
    """
    Gets the temperature from the thermometer.

    Parameters:
    - unit: The unit of temperature to get the temperature in. Can be "F", "C", "K", "oC" "D" "L" "N" "R" or "tuple". "tuple" causes a return value of (tempC, tempF).
    """
    global roms, ds_sensor
    ds_sensor.convert_temp()
    if unit not in ["F", "C", "tuple"]:
        raise ValueError(f"Invalid unit: {unit}")
    tempC = ds_sensor.read_temp(roms[0])
    tempF = tempC * (9/5) + 32
    if unit == "tuple":
        return tempC, tempF
    elif unit == "C":
        return tempC
    elif unit == "F":
        return tempF
lidar = UART(0, baudrate=115200, tx=Pin(16), rx=Pin(17))

def save_settings() -> None:
    """Saves the current settings to the Lidar."""
    global lidar
    lidar.write(bytes([0x5a, 0x04, 0x11, 0x6F]))
    utime.sleep_ms(100)

def set_samp_rate(samp_rate: int = 20) -> None:
    """
    Sets the sampling rate of the Lidar.

    Parameters:
    - samp_rate: The desired sampling rate in Hz.
    """
    global lidar
    hex_rate = samp_rate.to_bytes(2, 'big')
    samp_rate_packet = [0x5a, 0x06, 0x03, hex_rate[1], hex_rate[0], 0x00, 0x00]
    lidar.write(bytes(samp_rate_packet))
    utime.sleep(0.1)
    save_settings()

def get_version() -> str:
    """
    Retrieves the Lidar version information.

    Returns:
    - A string representing the Lidar version.

    Raises:
    - RuntimeError: If the version retrieval fails.
    """
    global lidar
    info_packet = [0x5a, 0x04, 0x14, 0x00]
    lidar.write(bytes(info_packet))
    start_tick = utime.time()
    while utime.time() - start_tick < 10:
        if lidar.any() > 0:
            bin_ascii = lidar.read(30)
            if bin_ascii and bin_ascii[0] == 0x5a:
                version = bin_ascii[0:].decode('utf-8')
                return version
            else:
                lidar.write(bytes(info_packet))
    raise RuntimeError("Failed to retrieve version.")

def get_lidar_data() -> tuple:
    """
    Retrieves the Lidar distance, strength, and temperature data.

    Returns:
    - A tuple (distance, strength, temperature) with the corresponding values.

    Raises:
    - RuntimeError: If data retrieval fails.
    """
    global lidar
    while True:
        if lidar.any() > 0:
            bin_ascii = lidar.read(9)
            if bin_ascii and len(bin_ascii) == 9 and bin_ascii[0] == 0x59 and bin_ascii[1] == 0x59:
                distance = bin_ascii[2] + bin_ascii[3] * 256
                strength = bin_ascii[4] + bin_ascii[5] * 256
                temperature = (bin_ascii[6] + bin_ascii[7] * 256) / 8 - 256
                return distance, strength, temperature
                
        else:
            return 0
        utime.sleep_ms(10)
def read_tag() -> int:
    reader.init()
    (stat, tag_type) = reader.request(reader.REQIDL)
    if stat == reader.OK:
        (stat, uid) = reader.SelectTagSN()
        if stat == reader.OK:
            card = int.from_bytes(bytes(uid),"little",False)
            return card
    print("Failed to find a card.")
    return -1
    
pico_server.register_sensor("Thermoneter",lambda: get_temp("F"))
pico_server.register_sensor("Lidar", get_lidar_data)
pico_server.register_sensor("RFID Tag", read_tag)
print(get_lidar_data())
# Start the web server
pico_server.run()


