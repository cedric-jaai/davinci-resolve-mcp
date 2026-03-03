"""
TCP Bridge client for DaVinci Resolve.

Connects to the Lua bridge server running inside Resolve's Fusion Console
and provides a transparent proxy that can replace the native resolve object.
"""

import json
import socket
import struct
import logging
import threading

logger = logging.getLogger("davinci-resolve-mcp.bridge")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
CONNECT_TIMEOUT = 2.0
RECV_TIMEOUT = 30.0
MAX_MESSAGE_SIZE = 16 * 1024 * 1024  # 16 MB


class ResolveBridge:
    """TCP client for the Resolve Lua bridge server."""

    def __init__(self, sock):
        self._sock = sock
        self._lock = threading.Lock()
        self._pending_releases = []

    @classmethod
    def connect(cls, host=DEFAULT_HOST, port=DEFAULT_PORT):
        """Attempt to connect to the bridge server. Returns a ResolveBridge or None."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((host, port))
            sock.settimeout(RECV_TIMEOUT)
            logger.info(f"Connected to Resolve bridge at {host}:{port}")
            return cls(sock)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.debug(f"Bridge connection failed: {e}")
            return None

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass

    def call(self, obj_id, method, args=None):
        """Send an RPC call and return the response dict."""
        if args is None:
            args = []

        # Serialize proxy args
        serialized_args = []
        for arg in args:
            if isinstance(arg, ResolveProxy):
                serialized_args.append({"__resolve_obj__": arg._obj_id})
            else:
                serialized_args.append(arg)

        request = {
            "obj_id": obj_id,
            "method": method,
            "args": serialized_args,
        }

        # Attach pending releases
        with self._lock:
            if self._pending_releases:
                request["_release"] = self._pending_releases
                self._pending_releases = []

        return self._send_recv(request)

    def schedule_release(self, obj_id):
        """Schedule a remote object for release on the next RPC call."""
        if obj_id == 1:
            return  # never release the root object
        with self._lock:
            self._pending_releases.append(obj_id)

    def _send_recv(self, request):
        """Send a length-prefixed JSON request and read the response."""
        data = json.dumps(request, separators=(",", ":")).encode("utf-8")
        header = struct.pack("!I", len(data))

        with self._lock:
            try:
                self._sock.sendall(header + data)
                return self._read_response()
            except (OSError, struct.error) as e:
                logger.error(f"Bridge communication error: {e}")
                return {"type": "error", "message": str(e)}

    def _read_response(self):
        """Read a length-prefixed JSON response."""
        header = self._recv_exact(4)
        if header is None:
            return {"type": "error", "message": "connection closed"}

        msg_len = struct.unpack("!I", header)[0]
        if msg_len > MAX_MESSAGE_SIZE:
            return {"type": "error", "message": "response too large"}

        data = self._recv_exact(msg_len)
        if data is None:
            return {"type": "error", "message": "connection closed during read"}

        return json.loads(data.decode("utf-8"))

    def _recv_exact(self, n):
        """Read exactly n bytes from the socket."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)


class ResolveProxy:
    """Transparent proxy for a remote Resolve API object."""

    def __init__(self, bridge, obj_id):
        object.__setattr__(self, "_bridge", bridge)
        object.__setattr__(self, "_obj_id", obj_id)

    def __getattr__(self, name):
        # Return a callable that performs the RPC
        def method_call(*args):
            resp = self._bridge.call(self._obj_id, name, list(args))
            return _unwrap_response(self._bridge, resp)
        return method_call

    def __bool__(self):
        return True

    def __repr__(self):
        return f"<ResolveProxy obj_id={self._obj_id}>"

    def __del__(self):
        try:
            bridge = object.__getattribute__(self, "_bridge")
            obj_id = object.__getattribute__(self, "_obj_id")
            bridge.schedule_release(obj_id)
        except Exception:
            pass


def _unwrap_response(bridge, resp):
    """Convert a bridge response into a Python value or proxy."""
    resp_type = resp.get("type")

    if resp_type == "error":
        msg = resp.get("message", "unknown error")
        logger.error(f"Bridge RPC error: {msg}")
        return None

    if resp_type == "object":
        return ResolveProxy(bridge, resp["id"])

    if resp_type == "value":
        return _unwrap_value(bridge, resp.get("value"))

    return None


def _unwrap_value(bridge, val):
    """Recursively unwrap values, converting object markers to proxies."""
    if val is None:
        return None

    if isinstance(val, dict):
        if "__resolve_obj__" in val:
            return ResolveProxy(bridge, val["__resolve_obj__"])
        return {k: _unwrap_value(bridge, v) for k, v in val.items()}

    if isinstance(val, list):
        return [_unwrap_value(bridge, item) for item in val]

    return val
