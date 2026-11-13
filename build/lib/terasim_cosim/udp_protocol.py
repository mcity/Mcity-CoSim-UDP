"""Wire protocol shared by the UDP bridge client and the UDP relay server.

Every datagram is a JSON envelope ``{"body": {...}, "sig": "<hmac-sha256>"}``.
The signature is computed over the canonical JSON encoding of ``body`` using
the static shared-session password as an HMAC key, so the password itself is
never transmitted and forged/tampered datagrams are rejected. ``body`` also
carries a timestamp so stale/replayed datagrams can be dropped.

This module has no third-party dependencies and lives outside
`udp_client_wrapper` (whose `__init__` pulls in redis/loguru) so both the
UDP bridge client and the standalone relay server can import it without
requiring the client's dependencies to be installed.
"""

import hmac
import hashlib
import json
import time
from typing import Any, Dict, Optional

PROTOCOL_VERSION = 1

MSG_TYPE_REGISTER = "register"
MSG_TYPE_PUBLISH = "publish"
MSG_TYPE_PING = "ping"
MSG_TYPE_PONG = "pong"

DEFAULT_MAX_CLOCK_SKEW_SECONDS = 30
MAX_UDP_PAYLOAD_BYTES = 60000


def _sign(secret: str, body: Dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def encode_message(secret: str, msg_type: str, **fields: Any) -> bytes:
    """Build a signed datagram for `msg_type` with the given payload fields."""
    body = {"v": PROTOCOL_VERSION, "type": msg_type, "ts": time.time(), **fields}
    envelope = {"body": body, "sig": _sign(secret, body)}
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def decode_message(
    secret: str,
    raw: bytes,
    max_clock_skew: Optional[float] = DEFAULT_MAX_CLOCK_SKEW_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Decode and authenticate a datagram, returning its body or None if invalid."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
        body = envelope["body"]
        signature = envelope["sig"]
    except (ValueError, KeyError, UnicodeDecodeError, TypeError):
        return None

    if not isinstance(body, dict) or not isinstance(signature, str):
        return None

    if not hmac.compare_digest(signature, _sign(secret, body)):
        return None

    if body.get("v") != PROTOCOL_VERSION:
        return None

    if max_clock_skew is not None:
        ts = body.get("ts")
        if not isinstance(ts, (int, float)) or abs(time.time() - ts) > max_clock_skew:
            return None

    return body
