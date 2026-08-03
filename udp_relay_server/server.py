"""Authenticated UDP relay/broker server for bridging TeraSim Redis pub/sub
channels between remote co-simulation peers over the internet.

Clients that want to receive data periodically send a REGISTER datagram
listing the channels they are interested in; the server remembers their
(ip, port) for those channels. Clients that want to send data send PUBLISH
datagrams; the server relays each one to every other registered client that
is interested in that channel. All datagrams are authenticated with an
HMAC computed from a static, shared session password (see udp_protocol.py)
so the password itself is never sent on the wire.

Built on asyncio's DatagramProtocol: a single non-blocking event loop calls
`datagram_received` for each inbound packet instead of blocking on
`socket.recvfrom` in a dedicated thread. Everything (packet handling, the
stale-client purge) runs on that one loop, so the client registry needs no
lock (compare with the previous threaded version, which required one).

Configuration is entirely via environment variables so this can be deployed
as-is in the accompanying Dockerfile:
    TERASIM_UDP_SERVER_HOST  - bind address (default 0.0.0.0)
    TERASIM_UDP_SERVER_PORT  - bind port (default 8443)
    TERASIM_UDP_PASSWORD     - required static session password
"""

import asyncio
import os
import signal
import time
import logging

from terasim_cosim.udp_protocol import (
    encode_message,
    decode_message,
    MSG_TYPE_REGISTER,
    MSG_TYPE_PUBLISH,
    MSG_TYPE_PING,
    MSG_TYPE_PONG,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("terasim_udp_relay")

CLIENT_TIMEOUT_SECONDS = 30
PURGE_INTERVAL_SECONDS = 10


class UDPRelayServer(asyncio.DatagramProtocol):
    """Authenticated UDP relay/broker for TeraSim co-simulation channels."""

    def __init__(self, password: str):
        if not password:
            raise ValueError(
                "A static session password must be provided via the "
                "TERASIM_UDP_PASSWORD environment variable."
            )
        self.password = password
        self.transport: "asyncio.DatagramTransport | None" = None
        # addr -> {"channels": set[str], "last_seen": float}
        self.clients = {}
        self._purge_task: "asyncio.Task | None" = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        self._purge_task = asyncio.ensure_future(self._purge_loop())

    def connection_lost(self, exc) -> None:
        if self._purge_task is not None:
            self._purge_task.cancel()

    def error_received(self, exc: Exception) -> None:
        logger.warning(f"UDP transport error: {exc}")

    def datagram_received(self, raw: bytes, addr) -> None:
        body = decode_message(self.password, raw)
        if body is None:
            logger.warning(f"Rejected unauthenticated/malformed datagram from {addr}")
            return

        msg_type = body.get("type")
        if msg_type == MSG_TYPE_REGISTER:
            channels = set(body.get("channels", []))
            self.clients[addr] = {"channels": channels, "last_seen": time.time()}
            logger.info(f"Registered client {addr} for channels {sorted(channels)}")
        elif msg_type == MSG_TYPE_PING:
            if addr in self.clients:
                self.clients[addr]["last_seen"] = time.time()
            self.transport.sendto(encode_message(self.password, MSG_TYPE_PONG), addr)
        elif msg_type == MSG_TYPE_PUBLISH:
            self._relay_publish(body, addr)
        else:
            logger.warning(f"Unknown message type '{msg_type}' from {addr}")

    def _relay_publish(self, body, sender_addr) -> None:
        channel = body.get("channel")
        data = body.get("data")
        if channel is None or data is None:
            return
        packet = encode_message(self.password, MSG_TYPE_PUBLISH, channel=channel, data=data)
        for addr, info in self.clients.items():
            if addr != sender_addr and channel in info["channels"]:
                self.transport.sendto(packet, addr)

    async def _purge_loop(self) -> None:
        while True:
            await asyncio.sleep(PURGE_INTERVAL_SECONDS)
            now = time.time()
            stale = [
                addr
                for addr, info in self.clients.items()
                if now - info["last_seen"] > CLIENT_TIMEOUT_SECONDS
            ]
            for addr in stale:
                del self.clients[addr]
                logger.info(f"Removed stale client {addr}")


async def run_server(host: str, port: int, password: str) -> None:
    loop = asyncio.get_running_loop()
    protocol = UDPRelayServer(password)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, local_addr=(host, port)
    )
    logger.info(f"TeraSim UDP relay server listening on {host}:{port}")

    stop_event = asyncio.Event()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    except NotImplementedError:
        # add_signal_handler is unavailable on Windows' default event loop;
        # Ctrl+C still raises KeyboardInterrupt, caught in main() below.
        pass

    try:
        await stop_event.wait()
    finally:
        transport.close()


def main() -> None:
    host = os.environ.get("TERASIM_UDP_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("TERASIM_UDP_SERVER_PORT", "8443"))
    password = os.environ.get("TERASIM_UDP_PASSWORD")

    try:
        asyncio.run(run_server(host, port, password))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
