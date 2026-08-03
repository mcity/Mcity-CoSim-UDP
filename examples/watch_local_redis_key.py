"""Poll a local Redis key and print it whenever it changes.

Useful for verifying the subscribe direction of the UDP bridge: run this on
the receiving site while `run_udp_bridge.py` is running there, then use
`seed_test_message.py` on the sending site.

Usage:
    python watch_local_redis_key.py [channel]
"""

import sys
import time

import redis

channel = sys.argv[1] if len(sys.argv) > 1 else "terasim/vehicle_state"

local_client = redis.Redis(host="localhost", port=6379, db=0, password="")

print(f"Watching local Redis key '{channel}'. Press Ctrl+C to stop.")
last_value = None
try:
    while True:
        value = local_client.get(channel)
        if value is not None and value != last_value:
            last_value = value
            print(f"[{time.strftime('%H:%M:%S')}] {channel} = {value.decode()}")
        time.sleep(0.2)
except KeyboardInterrupt:
    pass
