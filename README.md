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
│   └── udp_examples/
│       ├── run_udp_bridge.py          # start a bridge client for this site
│       ├── seed_test_message.py       # repeatedly write a test value into local Redis
│       └── watch_local_redis_key.py   # watch a local Redis key for changes
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

### Client environment setup

Most users only run the bridge client and connect to an existing relay
server. Get the relay's host, port and password from whoever runs it, then
copy `.env.example` to `.env` and set these three values:

```bash
cp .env.example .env
```

```dotenv
# Where to reach the relay server
TERASIM_UDP_HOST=relay.example.com
TERASIM_UDP_PORT=8443

# Shared secret - must match the relay server's password exactly
TERASIM_UDP_PASSWORD=choose-a-strong-shared-password
```

The `TERASIM_UDP_SERVER_*` lines in `.env.example` are only for hosting a
relay server; clients can ignore them.

Load it into your shell before running the client:

Linux / macOS (bash, zsh):

```bash
set -a && source .env && set +a
```

Windows (PowerShell):

```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { Set-Item "env:$($matches[1])" $matches[2] } }
```

Windows (Command Prompt):

```bat
for /f "usebackq eol=# tokens=1,* delims==" %a in (".env") do set "%a=%b"
```

These set the variables for the current terminal session only, so run them
again in each new terminal. In a `.bat` file, write `%%a` / `%%b` instead of
`%a` / `%b`.

If you are connecting to an existing relay server, skip to
[step 3](#3-run-the-bridge-client-at-each-site).

## 2. Run the relay server (relay host only)

Only one machine needs to do this: the publicly reachable host that both
sites connect to. The relay server needs no Redis and no third-party
packages, only the standard library.

### Server environment setup

On the relay host, set these in `.env`:

```dotenv
# Shared secret - every client must use this same value
TERASIM_UDP_PASSWORD=choose-a-strong-shared-password

# What the relay server binds to
TERASIM_UDP_SERVER_HOST=0.0.0.0
TERASIM_UDP_SERVER_PORT=8443
```

Load it into your shell before starting the server (Docker Compose or plain
Python):

Linux / macOS (bash, zsh):

```bash
set -a && source .env && set +a
```

Windows (PowerShell):

```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { Set-Item "env:$($matches[1])" $matches[2] } }
```

Windows (Command Prompt):

```bat
for /f "usebackq eol=# tokens=1,* delims==" %a in (".env") do set "%a=%b"
```

These set the variables for the current terminal session only, so run them
again in each new terminal. In a `.bat` file, write `%%a` / `%%b` instead of
`%a` / `%b`.

### Start the server

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

The ready-to-run version of this is `examples/udp_examples/run_udp_bridge.py`
— edit its `PUB_CHANNELS` / `SUB_CHANNELS` lists for your site and run:

```bash
python examples/udp_examples/run_udp_bridge.py
```

## 4. Try it end-to-end

Validate the whole path — local Redis → relay server → remote local Redis —
using the helper scripts in `examples/udp_examples/`.

On **Site A** (publishing):
```bash
python examples/udp_examples/run_udp_bridge.py                 # PUB_CHANNELS=[VEHICLE_STATE]
python examples/udp_examples/seed_test_message.py 20 terasim/vehicle_state "hello from A"
```

`seed_test_message.py [freq_hz] [channel] [message]` writes to `channel`
repeatedly at `freq_hz` (10-100 Hz) until you press Ctrl+C.

On **Site B** (receiving, with `PUB_CHANNELS`/`SUB_CHANNELS` swapped in
`run_udp_bridge.py`):
```bash
python examples/udp_examples/run_udp_bridge.py                 # SUB_CHANNELS=[VEHICLE_STATE]
python examples/udp_examples/watch_local_redis_key.py terasim/vehicle_state
```

Site B's `watch_local_redis_key.py` should print the values written by
`seed_test_message.py` on Site A, updating live as they arrive.

## Environment variable reference

### Client (bridge)

| Variable | Meaning |
|---|---|
| `TERASIM_UDP_HOST` | Relay server host/IP to connect to. Required. |
| `TERASIM_UDP_PORT` | Relay server port to connect to. Required. |
| `TERASIM_UDP_PASSWORD` | Shared session password. Must match the relay server's. Required, no default. |

### Server (relay host only)

| Variable | Meaning |
|---|---|
| `TERASIM_UDP_PASSWORD` | Shared session password that every client must use. Required, no default. |
| `TERASIM_UDP_SERVER_HOST` | Address the relay server binds to. Default `0.0.0.0`. |
| `TERASIM_UDP_SERVER_PORT` | Port the relay server binds to. Default `8443`. |

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
