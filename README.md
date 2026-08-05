# Mcity-CoSim-UDP

A UDP bridge that mirrors local Redis pub/sub channels between two (or more)
remote sites over the internet.

```
 Site A                                                   Site B
┌─────────────┐   pub_channels    ┌───────────────┐   pub_channels    ┌─────────────┐
│ Local Redis │ ───────────────►  │               │  ◄─────────────── │ Local Redis │
│  (site A)   │                   │  UDP Relay     │                   │  (site B)   │
│             │  ◄─────────────── │  Server        │ ───────────────► │             │
└─────────────┘   sub_channels    │ (public host)  │   sub_channels    └─────────────┘
```

Site A's `pub_channels` should be Site B's `sub_channels`, and vice versa.
For example, a vehicle simulator site publishes `terasim/vehicle_state` and
subscribes to `terasim/vehicle_control`; a driving simulator site does the
opposite.

## Repository layout

```
Mcity-CoSim-UDP/
├── terasim_cosim/
│   ├── constants.py               # env var names + shared Redis channel keys
│   ├── udp_protocol.py            # signed wire protocol
│   └── udp_client_wrapper/
│       └── udp_client.py          # TeraSimUDPClient / create_udp_client()
├── udp_relay_server/
│   ├── server.py                  # the relay/broker
│   ├── Dockerfile
│   └── docker-compose.yml
├── examples/
│   ├── run_udp_bridge.py          # start a bridge client for this site
│   ├── seed_test_message.py       # write a test value into local Redis
│   └── watch_local_redis_key.py   # watch a local Redis key for changes
├── requirements.txt
├── setup.py
└── .env.example
```

## Prerequisites

- Python 3.9+ on both sites (for the bridge client).
- A local Redis instance already running and reachable at each site, default
  `localhost:6379`.
- Docker (or a plain Python 3.11+ runtime) on the machine that will host the
  relay server, with one UDP port reachable from both sites (open in any
  firewall / cloud security group).

## 1. Install

```bash
git clone <this repo>
cd Mcity-CoSim-UDP
python -m venv venv && source venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` and fill it in:

```bash
cp .env.example .env
```

```dotenv
# Shared secret - MUST be identical on the relay server and every client.
TERASIM_UDP_PASSWORD=choose-a-strong-shared-password

# Client-side: where to reach the relay server
TERASIM_UDP_HOST=relay.example.com
TERASIM_UDP_PORT=8443

# Server-side: what the relay server binds to (used by Docker/compose)
TERASIM_UDP_SERVER_HOST=0.0.0.0
TERASIM_UDP_SERVER_PORT=8443
```

Load it into your shell before running anything:

```bash
set -a && source .env && set +a
```

## 2. Run the relay server

The relay server needs no Redis and no third-party packages — only the
standard library.

**Docker Compose (recommended):**

```bash
docker compose -f udp_relay_server/docker-compose.yml up -d --build
docker compose -f udp_relay_server/docker-compose.yml logs -f
```

**Or plain Python, no Docker:**

```bash
python udp_relay_server/server.py
```

Make sure UDP port `8443` (or your chosen port) is reachable from both
sites (open in any firewall / cloud security group).

## 3. Run the bridge client at each site

Use `create_udp_client()`, picking which local Redis keys this site
publishes out and which it subscribes to receive:

```python
from terasim_cosim.udp_client_wrapper import create_udp_client
from terasim_cosim.constants import VEHICLE_STATE, VEHICLE_CONTROL

# Site A: publish local vehicle state, receive remote vehicle control
udp_client = create_udp_client(
    pub_channels=[VEHICLE_STATE],
    sub_channels=[VEHICLE_CONTROL],
)
```

```python
# Site B: mirror image — publish control, receive state
udp_client = create_udp_client(
    pub_channels=[VEHICLE_CONTROL],
    sub_channels=[VEHICLE_STATE],
)
```

Call `udp_client.close()` to stop it (e.g. in a `finally` block). Instead of
environment variables, you can pass `server_host` / `server_port` /
`password` directly as keyword arguments, and `local_redis_config` to point
at a non-default local Redis (`{"host": ..., "port": ..., "db": ...,
"password": ...}`).

The ready-to-run version of this is `examples/run_udp_bridge.py` — edit its
`PUB_CHANNELS` / `SUB_CHANNELS` lists for your site and run:

```bash
python examples/run_udp_bridge.py
```

## 4. Try it end-to-end

Validate the whole path — local Redis → relay server → remote local Redis —
using the helper scripts in `examples/`.

On **Site A** (publishing):
```bash
python examples/run_udp_bridge.py                 # PUB_CHANNELS=[VEHICLE_STATE]
python examples/seed_test_message.py terasim/vehicle_state "hello from A"
```

On **Site B** (receiving, with `PUB_CHANNELS`/`SUB_CHANNELS` swapped in
`run_udp_bridge.py`):
```bash
python examples/run_udp_bridge.py                 # SUB_CHANNELS=[VEHICLE_STATE]
python examples/watch_local_redis_key.py terasim/vehicle_state
```

Site B's `watch_local_redis_key.py` should print the value written by
`seed_test_message.py` on Site A within a second or two.

## Environment variable reference

| Variable | Used by | Meaning |
|---|---|---|
| `TERASIM_UDP_PASSWORD` | client + server | Shared static session password. Must match on both ends. Required, no default. |
| `TERASIM_UDP_HOST` | client | Relay server host/IP to connect to. |
| `TERASIM_UDP_PORT` | client | Relay server port to connect to. |
| `TERASIM_UDP_SERVER_HOST` | server | Address the relay server binds to. Default `0.0.0.0`. |
| `TERASIM_UDP_SERVER_PORT` | server | Port the relay server binds to. Default `8443`. |

## Troubleshooting

- **Nothing arrives on the receiving site**: confirm both sites use the
  exact same `TERASIM_UDP_PASSWORD`, the relay server's UDP port is open
  through any firewall/security group, and the receiving client actually
  lists the channel in `sub_channels`.
- **Server logs "Rejected unauthenticated/malformed datagram"**: either a
  password mismatch, or the sender's clock is more than 30s off from the
  server's — sync clocks (NTP) and double-check the password.
- **Works locally but not across the internet**: most commonly a NAT/
  firewall dropping UDP — the relay server is the one that must be publicly
  reachable; clients behind NAT are fine as long as they initiate outbound
  UDP to the server.
