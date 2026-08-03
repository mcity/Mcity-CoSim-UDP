"""Authenticated UDP relay/broker server for bridging TeraSim Redis pub/sub
channels between remote co-simulation peers over the internet.

Clients that want to receive data periodically send a REGISTER datagram
listing the channels they are interested in; the server remembers their
(ip, port) for those channels. Clients that want to send data send PUBLISH
datagrams; the server relays each one to every other registered client that
is interested in that channel. All datagrams are authenticated with an
HMAC computed from a static, shared session password (see udp_protocol.py)
so the password itself is never sent on the wire.

Configuration is entirely via environment variables so this can be deployed
as-is in the accompanying Dockerfile:
    TERASIM_UDP_SERVER_HOST  - bind address (default 0.0.0.0)
    TERASIM_UDP_SERVER_PORT  - bind port (default 8443)
    TERASIM_UDP_PASSWORD     - required static session password
"""

import os
import socket
import threading
import time
import logging

from terasim_cosim.udp_protocol import (
    encode_message,
    decode_message,
    MSG_TYPE_REGISTER,
    MSG_TYPE_PUBLISH,
    MSG_TYPE_PING,
    MSG_TYPE_PONG,
    MAX_UDP_PAYLOAD_BYTES,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("terasim_udp_relay")

CLIENT_TIMEOUT_SECONDS = 30
PURGE_INTERVAL_SECONDS = 10


class UDPRelayServer:
    """Authenticated UDP relay/broker for TeraSim co-simulation channels."""

    def __init__(self, host: str, port: int, password: str):
        if not password:
            raise ValueError(
                "A static session password must be provided via the "
                "TERASIM_UDP_PASSWORD environment variable."
            )
        self.host = host
        self.port = port
        self.password = password

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))

        # addr -> {"channels": set[str], "last_seen": float}
        self.clients = {}
        self.clients_lock = threading.Lock()
        self._stop_event = threading.Event()

    def serve_forever(self) -> None:
        logger.info(f"TeraSim UDP relay server listening on {self.host}:{self.port}")
        purge_thread = threading.Thread(target=self._purge_loop, daemon=True)
        purge_thread.start()
        while not self._stop_event.is_set():
            try:
                raw, addr = self.socket.recvfrom(MAX_UDP_PAYLOAD_BYTES)
            except OSError:
                break
            self._handle_datagram(raw, addr)

    def _handle_datagram(self, raw: bytes, addr) -> None:
        body = decode_message(self.password, raw)
        if body is None:
            logger.warning(f"Rejected unauthenticated/malformed datagram from {addr}")
            return

        msg_type = body.get("type")
        if msg_type == MSG_TYPE_REGISTER:
            channels = set(body.get("channels", []))
            with self.clients_lock:
                self.clients[addr] = {"channels": channels, "last_seen": time.time()}
            logger.info(f"Registered client {addr} for channels {sorted(channels)}")
        elif msg_type == MSG_TYPE_PING:
            with self.clients_lock:
                if addr in self.clients:
                    self.clients[addr]["last_seen"] = time.time()
            self.socket.sendto(encode_message(self.password, MSG_TYPE_PONG), addr)
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
        with self.clients_lock:
            targets = [
                addr
                for addr, info in self.clients.items()
                if addr != sender_addr and channel in info["channels"]
            ]
        for addr in targets:
            self.socket.sendto(packet, addr)

    def _purge_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            with self.clients_lock:
                stale = [
                    addr
                    for addr, info in self.clients.items()
                    if now - info["last_seen"] > CLIENT_TIMEOUT_SECONDS
                ]
                for addr in stale:
                    del self.clients[addr]
                    logger.info(f"Removed stale client {addr}")
            self._stop_event.wait(PURGE_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._stop_event.set()
        self.socket.close()


def main() -> None:
    host = os.environ.get("TERASIM_UDP_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("TERASIM_UDP_SERVER_PORT", "8443"))
    password = os.environ.get("TERASIM_UDP_PASSWORD")

    server = UDPRelayServer(host=host, port=port, password=password)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
