"""Run a TeraSim UDP bridge client that mirrors local Redis channels to/from
a remote site through the UDP relay server.

Configure the relay connection via environment variables (see ../.env.example):
    TERASIM_UDP_HOST=<relay server host>
    TERASIM_UDP_PORT=<relay server port>
    TERASIM_UDP_PASSWORD=<same static password configured on the relay server>

Edit PUB_CHANNELS / SUB_CHANNELS below to match what this site should send
and receive. A typical two-site setup:
    Site A (vehicle simulator): PUB_CHANNELS=[VEHICLE_STATE],   SUB_CHANNELS=[VEHICLE_CONTROL]
    Site B (driving simulator): PUB_CHANNELS=[VEHICLE_CONTROL], SUB_CHANNELS=[VEHICLE_STATE]
"""

import time

from terasim_cosim_udp.constants import VEHICLE_STATE, VEHICLE_CONTROL
from terasim_cosim_udp.udp_client_wrapper import create_udp_client

PUB_CHANNELS = [VEHICLE_STATE]
SUB_CHANNELS = [VEHICLE_CONTROL]

udp_client = create_udp_client(
    pub_channels=PUB_CHANNELS,
    sub_channels=SUB_CHANNELS,
)

print(f"UDP bridge client running. Publishing {PUB_CHANNELS}, subscribing to {SUB_CHANNELS}.")
print("Press Ctrl+C to stop.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    udp_client.close()
