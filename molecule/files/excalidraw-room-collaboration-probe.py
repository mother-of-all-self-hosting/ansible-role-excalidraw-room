#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Exercises an Excalidraw collaboration server the way Excalidraw itself does.

A plain `GET /` against this server answers `Excalidraw collaboration server is
up :)` from a two-line Express handler that knows nothing about collaboration.
It would keep answering that with Socket.IO completely broken, so it proves very
little on its own. This probe instead speaks the protocol: it opens two
independent Socket.IO clients, puts them in the same room and makes the server
relay a message from one to the other, which is the entire job of this service.

It speaks Engine.IO v4 over RFC 6455 WebSockets with nothing but the Python
standard library, because the Molecule test images have no `python-socketio` and
the CI lint environment has no extra Ansible collections to install one with.

What each step establishes (see `src/index.ts` of excalidraw/excalidraw-room):

  http_root          The Express app is serving.
  engineio_handshake The Socket.IO endpoint answers with an Engine.IO v4 OPEN
                     packet carrying a session id, so something is listening
                     which is more than an HTTP server.
  socketio_connect   The Socket.IO layer completes a CONNECT for two separate
                     clients and issues each one a socket id.
  init_room          The server pushes `init-room` on connection without being
                     asked. That handler is excalidraw-room's own; a stock
                     Socket.IO server would stay silent.
  first_in_room      The first client to `join-room` is told `first-in-room`,
                     so the server is tracking room membership rather than
                     accepting the event and discarding it.
  new_user           The second client joining causes the first one to be told
                     `new-user` with the second one's socket id - the server
                     knows which sockets belong to the room and can address
                     them separately.
  room_user_change   Both clients are told the room now holds both socket ids.
  client_broadcast   A `server-broadcast` from one client arrives at the other
                     as `client-broadcast`, with the binary attachments intact
                     byte for byte. This is the collaboration path itself:
                     Excalidraw sends the encrypted scene and its IV exactly
                     this way, as two Socket.IO binary attachments.
  room_isolation     A `server-broadcast` addressed to a room nobody is in does
                     not arrive anywhere. Without this the check above would
                     also pass against a server that blindly echoed everything
                     to everyone, which is the failure this probe most needs to
                     be able to see.
"""

import argparse
import base64
import binascii
import http.client
import json
import os
import socket
import struct
import sys
import time

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

# Engine.IO packet types (the first character of a WebSocket text frame).
EIO_OPEN = "0"
EIO_CLOSE = "1"
EIO_PING = "2"
EIO_PONG = "3"
EIO_MESSAGE = "4"

# Socket.IO packet types (the character after the Engine.IO MESSAGE type).
SIO_CONNECT = "0"
SIO_EVENT = "2"
SIO_BINARY_EVENT = "5"


class ProbeError(Exception):
    pass


class SocketIOClient:
    """A minimal Socket.IO v4 client over a raw WebSocket transport."""

    def __init__(self, name, host, port, path, timeout):
        self.name = name
        self.host = host
        self.port = port
        self.path = path
        self.timeout = timeout
        self.sock = None
        self.sid = None
        self.socket_id = None
        self._recv_buffer = b""
        self._events = []
        self._pending_binary_event = None
        self._pending_attachments = []

    # -- WebSocket plumbing ------------------------------------------------

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET {path}?EIO=4&transport=websocket HTTP/1.1\r\n"
            "Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: http://{host}:{port}\r\n"
            "\r\n"
        ).format(path=self.path, host=self.host, port=self.port, key=key)
        self.sock.sendall(request.encode("ascii"))

        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ProbeError(
                    "%s: the server closed the connection during the WebSocket "
                    "handshake. Received so far: %r" % (self.name, header)
                )
            header += chunk

        head, _, rest = header.partition(b"\r\n\r\n")
        status_line = head.split(b"\r\n")[0].decode("latin-1")
        if "101" not in status_line:
            raise ProbeError(
                "%s: expected a `101 Switching Protocols` response from "
                "%s?EIO=4&transport=websocket, got `%s`. Full response head:\n%s"
                % (self.name, self.path, status_line, head.decode("latin-1"))
            )
        self._recv_buffer = rest

    def close(self):
        if self.sock is None:
            return
        try:
            self._send_frame(OPCODE_CLOSE, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None

    def _send_frame(self, opcode, payload):
        header = bytearray()
        header.append(0x80 | opcode)
        length = len(payload)
        # Client-to-server frames must be masked (RFC 6455 section 5.3).
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read_exactly(self, count, deadline):
        while len(self._recv_buffer) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("deadline reached")
            self.sock.settimeout(remaining)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ProbeError("%s: the server closed the connection" % self.name)
            self._recv_buffer += chunk
        taken, self._recv_buffer = self._recv_buffer[:count], self._recv_buffer[count:]
        return taken

    def _read_frame(self, deadline):
        """Returns a single (opcode, payload) pair, reassembling fragments."""
        frames = []
        first_opcode = None
        while True:
            head = self._read_exactly(2, deadline)
            fin = bool(head[0] & 0x80)
            opcode = head[0] & 0x0F
            masked = bool(head[1] & 0x80)
            length = head[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exactly(2, deadline))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exactly(8, deadline))[0]
            if masked:
                mask = self._read_exactly(4, deadline)
                payload = self._read_exactly(length, deadline)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            else:
                payload = self._read_exactly(length, deadline)

            if opcode == OPCODE_PING:
                self._send_frame(OPCODE_PONG, payload)
                continue
            if opcode == OPCODE_PONG:
                continue
            if opcode == OPCODE_CLOSE:
                raise ProbeError("%s: the server sent a WebSocket CLOSE frame" % self.name)

            if opcode != OPCODE_CONTINUATION:
                first_opcode = opcode
            frames.append(payload)
            if fin:
                return first_opcode, b"".join(frames)

    # -- Engine.IO / Socket.IO layer ---------------------------------------

    def _ingest(self, opcode, payload):
        if opcode == OPCODE_BINARY:
            if self._pending_binary_event is None:
                # A stray binary frame with no binary event awaiting it.
                return
            self._pending_attachments.append(payload)
            name, args, expected = self._pending_binary_event
            if len(self._pending_attachments) >= expected:
                args = _substitute_placeholders(args, self._pending_attachments)
                self._pending_binary_event = None
                self._pending_attachments = []
                self._events.append((name, args))
            return

        text = payload.decode("utf-8", "replace")
        if not text:
            return
        if text[0] == EIO_PING:
            self._send_frame(OPCODE_TEXT, EIO_PONG.encode("ascii"))
            return
        if text[0] == EIO_OPEN:
            self.sid = json.loads(text[1:])["sid"]
            return
        if text[0] == EIO_CLOSE:
            raise ProbeError("%s: the server sent an Engine.IO CLOSE packet" % self.name)
        if text[0] != EIO_MESSAGE:
            return

        body = text[1:]
        if not body:
            return
        if body[0] == SIO_CONNECT:
            payload_json = body[1:]
            if payload_json:
                self.socket_id = json.loads(payload_json).get("sid")
            return
        if body[0] == SIO_EVENT:
            decoded = json.loads(body[1:])
            self._events.append((decoded[0], decoded[1:]))
            return
        if body[0] == SIO_BINARY_EVENT:
            count_text, _, rest = body[1:].partition("-")
            decoded = json.loads(rest)
            self._pending_binary_event = (decoded[0], decoded[1:], int(count_text))
            self._pending_attachments = []
            return

    def pump(self, deadline):
        opcode, payload = self._read_frame(deadline)
        self._ingest(opcode, payload)

    def open_session(self, deadline):
        try:
            while self.sid is None:
                self.pump(deadline)
        except socket.timeout:
            raise ProbeError(
                "%s: no Engine.IO OPEN packet arrived from %s?EIO=4&transport=websocket"
                % (self.name, self.path)
            )
        self._send_frame(OPCODE_TEXT, (EIO_MESSAGE + SIO_CONNECT).encode("ascii"))
        try:
            while self.socket_id is None:
                self.pump(deadline)
        except socket.timeout:
            raise ProbeError(
                "%s: the Socket.IO CONNECT was never acknowledged with a socket id"
                % self.name
            )

    def emit(self, name, *args):
        attachments = [a for a in args if isinstance(a, (bytes, bytearray))]
        if not attachments:
            packet = EIO_MESSAGE + SIO_EVENT + json.dumps([name] + list(args))
            self._send_frame(OPCODE_TEXT, packet.encode("utf-8"))
            return
        placeheld = []
        index = 0
        for arg in args:
            if isinstance(arg, (bytes, bytearray)):
                placeheld.append({"_placeholder": True, "num": index})
                index += 1
            else:
                placeheld.append(arg)
        packet = "%s%s%d-%s" % (
            EIO_MESSAGE,
            SIO_BINARY_EVENT,
            len(attachments),
            json.dumps([name] + placeheld),
        )
        self._send_frame(OPCODE_TEXT, packet.encode("utf-8"))
        for attachment in attachments:
            self._send_frame(OPCODE_BINARY, bytes(attachment))

    def take_event(self, name, deadline):
        """Waits for the named event, returning its arguments."""
        while True:
            for i, (event_name, args) in enumerate(self._events):
                if event_name == name:
                    del self._events[i]
                    return args
            try:
                self.pump(deadline)
            except socket.timeout:
                raise ProbeError(
                    "%s: waited for the `%s` event and it never arrived. "
                    "Events received meanwhile: %r"
                    % (self.name, name, [n for n, _ in self._events])
                )

    def drain(self, until):
        """Reads whatever arrives until the given moment, discarding nothing."""
        while True:
            remaining = until - time.monotonic()
            if remaining <= 0:
                return
            try:
                self.pump(until)
            except socket.timeout:
                return

    def seen(self, name):
        return [args for event_name, args in self._events if event_name == name]


def _substitute_placeholders(value, attachments):
    if isinstance(value, list):
        return [_substitute_placeholders(item, attachments) for item in value]
    if isinstance(value, dict):
        if value.get("_placeholder") is True:
            return attachments[value["num"]]
        return {k: _substitute_placeholders(v, attachments) for k, v in value.items()}
    return value


def check_http_root(host, port, timeout, expected_body):
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8", "replace")
        status = response.status
    finally:
        connection.close()
    if status != 200:
        raise ProbeError("GET / answered %d, expected 200" % status)
    if expected_body not in body:
        raise ProbeError(
            "GET / answered 200 but its body does not contain %r. Body: %r"
            % (expected_body, body)
        )
    return {"status": status, "body": body}


def run(args):
    results = {}
    deadline = time.monotonic() + args.timeout

    results["http_root"] = check_http_root(
        args.host, args.port, args.timeout, args.expect_body
    )

    alice = SocketIOClient("client-a", args.host, args.port, args.path, args.timeout)
    bob = SocketIOClient("client-b", args.host, args.port, args.path, args.timeout)

    try:
        alice.connect()
        alice.open_session(deadline)
        if not alice.sid:
            raise ProbeError("client-a: the Engine.IO handshake produced no session id")
        results["engineio_handshake"] = {"sid_length": len(alice.sid)}
        results["socketio_connect"] = {"client_a_socket_id": alice.socket_id}

        alice.take_event("init-room", deadline)
        results["init_room"] = {"client_a": True}

        alice.emit("join-room", args.room)
        alice.take_event("first-in-room", deadline)
        alone = alice.take_event("room-user-change", deadline)[0]
        if alone != [alice.socket_id]:
            raise ProbeError(
                "client-a joined %r alone but the server reported the room as %r "
                "instead of just its own socket id %r"
                % (args.room, alone, alice.socket_id)
            )
        results["first_in_room"] = {"room": args.room, "members": alone}

        bob.connect()
        bob.open_session(deadline)
        bob.take_event("init-room", deadline)
        results["socketio_connect"]["client_b_socket_id"] = bob.socket_id

        bob.emit("join-room", args.room)
        announced = alice.take_event("new-user", deadline)[0]
        if announced != bob.socket_id:
            raise ProbeError(
                "client-a was told `new-user` %r but client-b's socket id is %r"
                % (announced, bob.socket_id)
            )
        results["new_user"] = {"announced_to_client_a": announced}

        members = alice.take_event("room-user-change", deadline)[0]
        if sorted(members) != sorted([alice.socket_id, bob.socket_id]):
            raise ProbeError(
                "the server reported room %r as holding %r, expected exactly %r"
                % (args.room, members, [alice.socket_id, bob.socket_id])
            )
        results["room_user_change"] = {"members": sorted(members)}

        # The collaboration path proper. Excalidraw sends the encrypted scene
        # and its initialisation vector as two Socket.IO binary attachments;
        # send bytes that could not have been produced by anything else.
        scene = args.payload.encode("utf-8")
        iv = bytes(range(12))
        bob.emit("server-broadcast", args.room, scene, iv)

        relayed = alice.take_event("client-broadcast", deadline)
        if len(relayed) < 2:
            raise ProbeError(
                "client-broadcast arrived with %d argument(s), expected the "
                "scene and the IV" % len(relayed)
            )
        if bytes(relayed[0]) != scene:
            raise ProbeError(
                "the relayed scene differs from what was sent: %r != %r"
                % (bytes(relayed[0]), scene)
            )
        if bytes(relayed[1]) != iv:
            raise ProbeError(
                "the relayed IV differs from what was sent: %r != %r"
                % (bytes(relayed[1]), iv)
            )
        results["client_broadcast"] = {
            "bytes": len(scene),
            "scene_sha_prefix": binascii.hexlify(scene[:8]).decode("ascii"),
        }

        # Negative control: nobody is in this room, so nothing may come out of
        # it. A server that echoed every broadcast to every client would pass
        # every check above and fail here.
        other_room = args.room + "-nobody-is-here"
        bob.emit("server-broadcast", other_room, b"must-not-be-relayed", iv)
        settle = time.monotonic() + args.isolation_wait
        alice.drain(settle)
        bob.drain(time.monotonic() + 0.2)
        leaked = alice.seen("client-broadcast")
        if leaked:
            raise ProbeError(
                "a broadcast addressed to room %r, which client-a is not in, "
                "was delivered to client-a anyway: %r" % (other_room, leaked)
            )
        results["room_isolation"] = {"unjoined_room": other_room, "leaked": False}
    finally:
        alice.close()
        bob.close()

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--path", default="/socket.io/")
    parser.add_argument("--room", default="molecule-probe-room")
    parser.add_argument(
        "--payload",
        default="excalidraw-room-molecule-probe",
        help="the scene bytes to relay from one client to the other",
    )
    parser.add_argument(
        "--expect-body",
        default="Excalidraw collaboration server is up",
        help="a string that GET / must answer with",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--isolation-wait",
        type=float,
        default=2.0,
        help="how long to wait for a broadcast that must never arrive",
    )
    args = parser.parse_args()

    try:
        results = run(args)
    except (ProbeError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        return 1

    print(json.dumps({"ok": True, "checks": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
