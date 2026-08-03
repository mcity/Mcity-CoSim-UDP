# Mcity-CoSim-UDP

A standalone UDP bridge that mirrors TeraSim-Cosim Redis pub/sub channels
between two (or more) remote sites over the internet.

It has two pieces:

- **UDP relay server** (`udp_relay_server/`) — a small, dependency-free,
  password-authenticated broker you deploy on a publicly reachable host
  (e.g. a cloud VM). It relays datagrams between connected clients; it does
  not talk to Redis itself.
- **UDP bridge client** (`terasim_cosim/udp_client_wrapper/`) — runs next to
  each site's *local* Redis instance (the one TeraSim-Cosim already reads
  from/writes to). It reads chosen keys from local Redis and forwards them
  to the relay server, and writes back anything the relay server relays to
  it for the channels it subscribed to.

```
 Site A                                                   Site B
┌─────────────┐   pub_channels    ┌───────────────┐   pub_channels    ┌─────────────┐
│ Local Redis │ ───────────────►  │               │  ◄─────────────── │ Local Redis │
│  (site A)   │                   │  UDP Relay     │                   │  (site B)   │
│             │  ◄─────────────── │  Server        │ ───────────────► │             │
└─────────────┘   sub_channels    │ (public host)  │   sub_channels    └─────────────┘
       ▲                          └───────────────┘                          ▲
       │        TeraSimUDPClient (this repo)         TeraSimUDPClient (this repo)
       │                    UDP, over the internet, HMAC-authenticated       │
       └────────────────────────────────────────────────────────────────────┘
```

Site A's `pub_channels` should be Site B's `sub_channels`, and vice versa.
For example, a vehicle simulator site publishes `terasim/vehicle_state` and
subscribes to `terasim/vehicle_control`; a driving simulator site does the
opposite.

This repo is intentionally self-contained: it does **not** depend on the
rest of the TeraSim-Cosim package (no `redis_msgs`, no `redis_client_wrapper`).
It only needs a reachable local Redis instance and, once installed, works
independently of where the main TeraSim-Cosim source lives.

## Repository layout

```
Mcity-CoSim-UDP/
├── terasim_cosim/
│   ├── constants.py               # env var names + shared Redis channel keys
│   ├── udp_protocol.py            # dependency-free signed wire protocol
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
├── requirements.txt                # client-side deps (redis, loguru)
├── setup.py
└── .env.example
```

## How it works

1. Each site runs a `TeraSimUDPClient` (via `create_udp_client(...)`) pointed
   at the same relay server and the same shared password.
2. For every key in `pub_channels`, the client polls local Redis; whenever
   the value's `header.timestamp` field changes, it signs and sends the raw
   JSON string to the relay server over UDP.
3. For `sub_channels`, the client periodically sends a `register` datagram
   telling the relay server which channels it wants (this is also what lets
   the connectionless relay server know the client's public `ip:port`, and
   doubles as a NAT keep-alive).
4. The relay server relays every `publish` datagram it receives to every
   other registered client whose subscriptions include that channel. It
   never touches Redis — it only forwards authenticated bytes.
5. On the receiving client, incoming `publish` datagrams are authenticated,
   and if the channel is one this client subscribed to, the payload is
   written into local Redis under that same key — exactly where
   TeraSim-Cosim (or anything else reading local Redis) expects to find it.

### Security model

- Every datagram is `{"body": {...}, "sig": "<hmac-sha256>"}`. `sig` is an
  HMAC-SHA256 over the canonical JSON of `body`, keyed with the shared
  static password. **The password itself is never transmitted** — only
  parties that already know it can produce a valid signature.
- `body` carries a timestamp; datagrams older/newer than 30s of the relay
  server's clock are rejected (replay-window protection). Keep client/server
  clocks roughly in sync (e.g. NTP) or datagrams will be silently dropped.
- The relay server rejects (and logs) any datagram that fails signature
  verification, so a client without the correct password cannot register,
  publish, or receive anything.
- There is no per-client identity beyond "knows the password" — it's a
  single shared session secret, as requested. Anyone with the password and
  the server's host:port can join. Rotate the password (and restart both
  ends) if it may have leaked.

### Limitations

- UDP is best-effort: datagrams can be dropped, duplicated, or reordered.
  This matches the existing TeraSim-Cosim remote-Redis pub/sub bridge, which
  is also best-effort, and is fine for high-rate state broadcasts (vehicle
  state/control) but not for data that must never be lost.
- Max datagram payload is ~60 KB (`MAX_UDP_PAYLOAD_BYTES` in
  `udp_protocol.py`); oversized messages are dropped with a warning logged.
- The relay server keeps client registrations in memory only — restarting it
  clears all registrations (clients will re-register automatically within
  `register_interval`, default 5s).

## Prerequisites

- Python 3.9+ on both sites (for the bridge client).
- A local Redis instance already running and reachable at each site (the
  same one TeraSim-Cosim uses), default `localhost:6379`.
- Docker (or a plain Python 3.11+ runtime) on the machine that will host the
  relay server, with one UDP port reachable from both sites (open in any
  firewall / cloud security group).

## 1. Deploy the UDP relay server

The relay server needs no Redis and no third-party packages — only the
standard library — but the easiest deployment path is Docker.

### Option A: Docker Compose (recommended)

```bash
cd Mcity-CoSim-UDP
export TERASIM_UDP_PASSWORD="choose-a-strong-shared-password"
export TERASIM_UDP_SERVER_PORT=8443   # optional, defaults to 8443
docker compose -f udp_relay_server/docker-compose.yml up -d --build
```

This builds the image, binds UDP port `8443` (or your chosen port) on the
host, and restarts the container automatically. Check logs with:

```bash
docker compose -f udp_relay_server/docker-compose.yml logs -f
```

### Option B: Plain `docker run`

```bash
cd Mcity-CoSim-UDP
docker build -f udp_relay_server/Dockerfile -t terasim-udp-relay .
docker run -d --name terasim-udp-relay \
  -p 8443:8443/udp \
  -e TERASIM_UDP_PASSWORD="choose-a-strong-shared-password" \
  -e TERASIM_UDP_SERVER_PORT=8443 \
  terasim-udp-relay
```

### Option C: Run directly with Python (no Docker)

```bash
cd Mcity-CoSim-UDP
export PYTHONPATH=.
export TERASIM_UDP_PASSWORD="choose-a-strong-shared-password"
export TERASIM_UDP_SERVER_HOST=0.0.0.0
export TERASIM_UDP_SERVER_PORT=8443
python udp_relay_server/server.py
```

On Windows PowerShell, use `$env:TERASIM_UDP_PASSWORD = "..."` etc. instead
of `export`.

Whichever option you use, make sure UDP port `8443` (or your chosen port) is
open to the internet (cloud security group / firewall rule) so both sites'
clients can reach it.

### Deploying the relay server on AWS ECS (Fargate)

The image builds and runs as-is on ECS. A few things are specific to this
workload and worth getting right before sizing a task definition.

**Task sizing:**

| Workload | vCPU | Memory | Notes |
|---|---|---|---|
| Dev / test, 1-2 site pairs | 0.25 vCPU | 0.5 GB | Fargate's minimum task size. |
| Typical co-sim session (a few site pairs, state/control at 10-50 Hz) | 0.5 vCPU | 1 GB | Recommended starting point for production use. |
| Many concurrent site pairs / high publish rate | 1 vCPU | 2 GB | Only if load testing shows CPU or packet-drop pressure at 0.5 vCPU. |

These are reasoned estimates based on the code, **not measured benchmarks**:
the server does one JSON parse plus one HMAC-SHA256 verify per datagram
(sub-millisecond each) in a single-threaded `recvfrom` loop, so it's bound by
packets-per-second rather than raw compute, and its memory footprint (an
in-memory dict of connected clients) is negligible next to the ~50-80 MB
Python runtime baseline. Load-test with your real channel count and publish
rate before committing to a size; if CloudWatch `CPUUtilization` for the task
sits near 100%, or you observe delivery gaps under load, move up a tier.

**Do not horizontally scale this service.** `UDPRelayServer` keeps its
client registry (`self.clients`) in the process's own memory. Running more
than one task behind a load balancer or Cloud Map means a publisher
registered against task A cannot reach a subscriber that lands on task B —
pub/sub would silently, partially break. Keep the ECS service's
`desiredCount` at `1`; rely on ECS's automatic replacement of a failed task
for availability (clients re-register automatically within
`register_interval`, default 5s, after a brief outage) rather than running
replicas. Sizing up (more vCPU/memory on the one task) is the right lever
for more load, not scaling out — a shared registry (e.g. backed by Redis)
would be needed before this design could safely run multiple concurrent
tasks.

**Networking:** Fargate requires `awsvpc` mode, so the task gets its own
ENI. Application Load Balancers don't support UDP, so pick one of:

1. **Simplest** — run the single task in a public subnet with
   `assignPublicIp: ENABLED` and a security group allowing inbound UDP on
   your chosen port; point clients at that public IP directly. The IP
   changes if the task is replaced, so pair this with light automation
   (e.g. a Lambda on ECS task state-change events updating a Route 53
   record) if clients need a stable hostname.
2. **Network Load Balancer with a UDP listener** — gives a stable DNS name
   and lets the task stay private, but NLB target group health checks need
   TCP or HTTP; this server only speaks UDP, so you'd need to add a small
   TCP health-check listener to `server.py` (not included here) or configure
   the target group to treat the task as always-healthy and rely on ECS
   service-level health instead.

Either way, put `TERASIM_UDP_PASSWORD` in the task definition's `secrets`
field (AWS Secrets Manager or SSM Parameter Store), not as a plaintext
`environment` value.

## 2. Install the bridge client at each site

On each machine that has a local Redis instance to bridge:

```bash
cd Mcity-CoSim-UDP
pip install -r requirements.txt
```

(or `pip install -e .` to install it as an importable package.)

Set the client-side environment variables (see `.env.example`):

```bash
export TERASIM_UDP_HOST=<relay server public host or IP>
export TERASIM_UDP_PORT=8443
export TERASIM_UDP_PASSWORD="choose-a-strong-shared-password"   # must match the server
```

## 3. Bridge local Redis channels through the relay

Use `create_udp_client()` from Python, picking which local Redis keys this
site publishes out and which it subscribes to receive:

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

`create_udp_client()` starts its background publish/register/receive threads
immediately; call `udp_client.close()` to stop them (e.g. in a `finally`
block or on shutdown). `server_host` / `server_port` / `password` can also be
passed as explicit keyword arguments instead of environment variables, and
`local_redis_config` overrides the local Redis connection
(`{"host": ..., "port": ..., "db": ..., "password": ...}`, defaults to
`localhost:6379`).

The ready-to-run version of the snippet above is `examples/run_udp_bridge.py`
— edit its `PUB_CHANNELS` / `SUB_CHANNELS` lists for your site and run:

```bash
python examples/run_udp_bridge.py
```

### End-to-end test without a full TeraSim-Cosim install

You can validate the whole path — local Redis → relay server → remote local
Redis — using only the two helper scripts in `examples/`, no simulator
required:

On **Site A** (publishing site):
```bash
python examples/run_udp_bridge.py                 # PUB_CHANNELS=[VEHICLE_STATE]
python examples/seed_test_message.py terasim/vehicle_state "hello from A"
```

On **Site B** (receiving site, with `PUB_CHANNELS`/`SUB_CHANNELS` swapped in
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
| `TERASIM_UDP_PASSWORD` | client + server | Shared static session password (HMAC key). Must match on both ends. Required, no default. |
| `TERASIM_UDP_HOST` | client | Relay server host/IP to connect to. |
| `TERASIM_UDP_PORT` | client | Relay server port to connect to. |
| `TERASIM_UDP_SERVER_HOST` | server | Address the relay server binds to. Default `0.0.0.0`. |
| `TERASIM_UDP_SERVER_PORT` | server | Port the relay server binds to. Default `8443`. |

## Troubleshooting

- **Nothing arrives on the receiving site**: confirm both sites use the
  exact same `TERASIM_UDP_PASSWORD`, the relay server's UDP port is open
  through any firewall/security group, and the receiving client actually
  lists the channel in `sub_channels` (it silently ignores channels it
  didn't subscribe to).
- **Server logs "Rejected unauthenticated/malformed datagram"**: either a
  password mismatch, or the sender's clock is more than 30s off from the
  server's — sync clocks (NTP) and double-check the password.
- **Works locally but not across the internet**: most commonly a NAT/
  firewall dropping UDP; the client's periodic `register` datagrams (every
  5s) double as keep-alives, but the very first inbound reply still needs an
  open/forwarded UDP port on the relay server side (the relay server is the
  one that must be publicly reachable — clients behind NAT are fine as long
  as they initiate outbound UDP to the server).
- **Values in local Redis don't get picked up for publishing**: the bridge
  client only forwards a key when its JSON value's `header.timestamp` field
  changes (matching how TeraSim-Cosim already versions values); make sure
  whatever writes that key also bumps `header.timestamp`.
