import queue
import socket
import struct
import threading
import unittest

import mock_sender
from vive_stream_pb2 import ViveFrame

HEADER_STRUCT = struct.Struct(">I")


def recvall(conn: socket.socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return data


class MockStreamTest(unittest.TestCase):
    def test_mock_sender_to_receiver(self):
        expected_frames = 3
        roles = ["right_elbow", "chest"]
        port_queue: queue.Queue[int] = queue.Queue()
        received = []

        def receiver():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
            port_queue.put(server.getsockname()[1])
            server.listen(1)
            server.settimeout(5)
            try:
                conn, _ = server.accept()
            except socket.timeout:
                server.close()
                return
            with conn:
                conn.settimeout(5)
                for _ in range(expected_frames):
                    header = recvall(conn, HEADER_STRUCT.size)
                    if not header:
                        break
                    (length,) = HEADER_STRUCT.unpack(header)
                    payload = recvall(conn, length)
                    if not payload:
                        break
                    frame = ViveFrame()
                    frame.ParseFromString(payload)
                    received.append(frame)
            server.close()

        thread = threading.Thread(target=receiver, daemon=True)
        thread.start()
        port = port_queue.get(timeout=2)

        mock_sender.send_frames("127.0.0.1", port, roles, expected_frames, hz=5)
        thread.join(timeout=5)

        self.assertEqual(len(received), expected_frames)
        for idx, frame in enumerate(received):
            self.assertEqual(len(frame.trackers), len(roles))
            for t_idx, role in enumerate(roles):
                tracker = frame.trackers[t_idx]
                self.assertEqual(tracker.role, role)
                self.assertAlmostEqual(tracker.px, 0.1 * t_idx + 0.001 * idx)
                self.assertAlmostEqual(tracker.qw, 1.0)


if __name__ == "__main__":
    unittest.main()
