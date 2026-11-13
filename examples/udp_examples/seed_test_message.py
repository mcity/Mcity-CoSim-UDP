"""Repeatedly write a JSON test value into local Redis under a channel key.

Useful for exercising the publish direction of the UDP bridge without
running the full TeraSim-Cosim stack: run this on the publishing site after
`run_udp_bridge.py` is already running, then check `watch_local_redis_key.py`
on the receiving site.

Usage:
    python seed_test_message.py [freq_hz] [channel] [message]

    freq_hz   How often to update the local Redis key, in Hz. Must be
              between 10 and 100. Defaults to 10 if omitted.
"""

import sys
import json
import time

import redis

MIN_FREQ_HZ = 10
MAX_FREQ_HZ = 100

freq_hz = float(sys.argv[1]) if len(sys.argv) > 1 else MIN_FREQ_HZ
channel = sys.argv[2] if len(sys.argv) > 2 else "terasim/vehicle_state"
message = sys.argv[3] if len(sys.argv) > 3 else "hello from seed_test_message.py"

if not (MIN_FREQ_HZ <= freq_hz <= MAX_FREQ_HZ):
    sys.exit(
        f"freq_hz must be between {MIN_FREQ_HZ} and {MAX_FREQ_HZ}, got {freq_hz}"
    )

local_client = redis.Redis(host="localhost", port=6379, db=0, password="")
period = 1.0 / freq_hz

print(
    f"Updating local Redis key '{channel}' at {freq_hz} Hz. Press Ctrl+C to stop."
)
count = 0
try:
    while True:
        # Every UDP-bridged value must contain a "header.timestamp" field:
        # the bridge client uses timestamp changes to detect new values
        # worth forwarding.
        payload = {
            "header": {"timestamp": time.time(), "information": "seed_test_message"},
            "data": f"{message} (#{count})",
        }
        local_client.set(channel, json.dumps(payload))
        count += 1
        time.sleep(period)
except KeyboardInterrupt:
    pass

print(f"Sent {count} update(s) to '{channel}'.")
