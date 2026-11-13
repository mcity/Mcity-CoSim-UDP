import os
import json
import time
import socket
import threading
from typing import Any, List, Optional

import redis
from loguru import logger

import terasim_cosim_udp.constants as constants
from terasim_cosim_udp.udp_protocol import (
    encode_message,
    decode_message,
    MSG_TYPE_REGISTER,
    MSG_TYPE_PUBLISH,
    MAX_UDP_PAYLOAD_BYTES,
)


class TeraSimUDPClient:
    """Bridges local Redis keys to a remote TeraSim UDP relay server.

    Publish direction: the value of every key in `pub_channels` is read from
    the local Redis instance and forwarded to the UDP relay server whenever
    it changes.
    Subscribe direction: messages the relay server relays for `sub_channels`
    are written back into the local Redis instance under the same key.
    """

    publish_poll_interval = 0.001
    register_interval = 5.0
    socket_timeout = 1.0

    def __init__(
        self,
        server_host: Optional[str] = None,
        server_port: Optional[int] = None,
        password: Optional[str] = None,
        pub_channels: List[str] = [],
        sub_channels: List[str] = [],
        local_redis_config: Optional[dict] = None,
    ):
        """Initialize the UDP bridge client.

        Args:
            server_host (str, optional): Relay server host. Defaults to the
                TERASIM_UDP_HOST environment variable.
            server_port (int, optional): Relay server port. Defaults to the
                TERASIM_UDP_PORT environment variable.
            password (str, optional): Static session password shared with the
                relay server. Defaults to the TERASIM_UDP_PASSWORD
                environment variable.
            pub_channels (list, optional): Local Redis keys to forward to the
                relay server. Defaults to [].
            sub_channels (list, optional): Channels to receive from the relay
                server and write into the local Redis instance. Defaults to [].
            local_redis_config (dict, optional): host/port/db/password of the
                local Redis instance. Defaults to localhost:6379.
        """
        server_host = server_host or os.environ.get(constants.ENVIRONMENT_VARIABLE_UDP_HOST)
        server_port = server_port or os.environ.get(constants.ENVIRONMENT_VARIABLE_UDP_PORT)
        password = password or os.environ.get(constants.ENVIRONMENT_VARIABLE_UDP_PASSWORD)

        if not server_host or not server_port:
            raise ValueError(
                "UDP relay server host/port must be provided via arguments or the "
                f"{constants.ENVIRONMENT_VARIABLE_UDP_HOST}/{constants.ENVIRONMENT_VARIABLE_UDP_PORT} "
                "environment variables."
            )
        if not password:
            raise ValueError(
                "UDP relay session password must be provided via the `password` argument "
                f"or the {constants.ENVIRONMENT_VARIABLE_UDP_PASSWORD} environment variable."
            )

        self.server_addr = (server_host, int(server_port))
        self.password = password
        self.pub_channels = pub_channels
        self.sub_channels = sub_channels

        local_redis_config = local_redis_config or {}
        self.local_client = redis.Redis(
            host=local_redis_config.get("host", "localhost"),
            port=local_redis_config.get("port", 6379),
            db=local_redis_config.get("db", 0),
            password=local_redis_config.get("password", ""),
        )

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(self.socket_timeout)

        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []

        if self.sub_channels:
            self._threads.append(
                threading.Thread(target=self._register_loop, daemon=True)
            )
            self._threads.append(
                threading.Thread(target=self._receive_loop, daemon=True)
            )
        for channel in self.pub_channels:
            self._threads.append(
                threading.Thread(
                    target=self._publish_loop, args=(channel,), daemon=True
                )
            )

        for thread in self._threads:
            thread.start()

    def _send(self, msg_type: str, **fields: Any) -> None:
        packet = encode_message(self.password, msg_type, **fields)
        if len(packet) > MAX_UDP_PAYLOAD_BYTES:
            logger.warning(
                f"Dropping oversized UDP packet ({len(packet)} bytes) for type '{msg_type}'"
            )
            return
        self.socket.sendto(packet, self.server_addr)

    def _register_loop(self) -> None:
        logger.info(
            f"Registering for channels {self.sub_channels} with relay server {self.server_addr}"
        )
        while not self._stop_event.is_set():
            self._send(MSG_TYPE_REGISTER, channels=self.sub_channels)
            self._stop_event.wait(self.register_interval)

    def _publish_loop(self, channel: str) -> None:
        logger.info(f"Publishing local Redis key '{channel}' to relay server {self.server_addr}")
        prev_timestamp = None
        while not self._stop_event.is_set():
            message = self.local_client.get(channel)
            if message is not None:
                data = json.loads(message)
                assert (
                    "header" in data
                ), f"Key 'header' is not in the value of channel '{channel}'"
                timestamp = data["header"]["timestamp"]
                if prev_timestamp is None or prev_timestamp != timestamp:
                    prev_timestamp = timestamp
                    self._send(MSG_TYPE_PUBLISH, channel=channel, data=message.decode())
            time.sleep(self.publish_poll_interval)

    def _receive_loop(self) -> None:
        logger.info(f"Listening for relayed UDP messages from {self.server_addr}")
        while not self._stop_event.is_set():
            try:
                raw, _ = self.socket.recvfrom(MAX_UDP_PAYLOAD_BYTES)
            except socket.timeout:
                continue
            except OSError:
                break
            body = decode_message(self.password, raw)
            if body is None:
                logger.warning("Dropping UDP message that failed authentication")
                continue
            if body.get("type") != MSG_TYPE_PUBLISH:
                continue
            channel = body.get("channel")
            data = body.get("data")
            if channel not in self.sub_channels or data is None:
                continue
            self.local_client.set(channel, data)

    def close(self) -> None:
        """Stop all background threads and close the UDP socket."""
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=self.socket_timeout + 1)
        self.socket.close()


def create_udp_client(
    server_host: Optional[str] = None,
    server_port: Optional[int] = None,
    password: Optional[str] = None,
    pub_channels: List[str] = [],
    sub_channels: List[str] = [],
    local_redis_config: Optional[dict] = None,
) -> TeraSimUDPClient:
    """Helper function to create a TeraSim UDP bridge client.

    Args:
        server_host (str, optional): Relay server host. Defaults to TERASIM_UDP_HOST.
        server_port (int, optional): Relay server port. Defaults to TERASIM_UDP_PORT.
        password (str, optional): Static session password. Defaults to TERASIM_UDP_PASSWORD.
        pub_channels (list, optional): Local Redis keys to forward to the relay server. Defaults to [].
        sub_channels (list, optional): Channels to receive and write into local Redis. Defaults to [].
        local_redis_config (dict, optional): Connection config for the local Redis instance.

    Returns:
        TeraSimUDPClient: UDP bridge client for TeraSim co-simulation.
    """
    return TeraSimUDPClient(
        server_host=server_host,
        server_port=server_port,
        password=password,
        pub_channels=pub_channels,
        sub_channels=sub_channels,
        local_redis_config=local_redis_config,
    )
