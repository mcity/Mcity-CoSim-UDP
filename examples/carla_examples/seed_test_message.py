"""Write a single JSON test value into local Redis under a channel key.

Useful for exercising the publish direction of the UDP bridge without
running the full TeraSim-Cosim stack: run this on the publishing site after
`run_udp_bridge.py` is already running, then check `watch_local_redis_key.py`
on the receiving site.

Usage:
    python seed_test_message.py [channel] [message]
"""

import sys
import json
import time

import redis

channel = sys.argv[1] if len(sys.argv) > 1 else "terasim/vehicle_state"
message = sys.argv[2] if len(sys.argv) > 2 else "hello from seed_test_message.py"

local_client = redis.Redis(host="localhost", port=6379, db=0, password="")

# Every UDP-bridged value must contain a "header.timestamp" field: the
# bridge client uses timestamp changes to detect new values worth forwarding.
payload = {
    "header": {"timestamp": time.time(), "information": "seed_test_message"},
    "data": message,
}
local_client.set(channel, json.dumps(payload))

print(f"Set local Redis key '{channel}' to: {payload}")
