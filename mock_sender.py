"""
Send dummy Vive tracker frames over the same protobuf/TCP framing used by
`vive_stream_sender_win.py`, but without requiring OpenXR or real hardware.

Example:
    python mock_sender.py --host 127.0.0.1 --port 50051 --frames 5 --hz 10
"""

import argparse
import socket
import struct
import time
from typing import Iterable, List

from vive_stream_pb2 import ViveFrame

HEADER_STRUCT = struct.Struct(">I")


def build_dummy_frame(frame_idx: int, roles: List[str], base_time_ns: int) -> ViveFrame:
    """Create a synthetic frame with deterministic pose values."""
    frame = ViveFrame(timestamp_ns=base_time_ns + frame_idx * 1_000_000)
    for i, role in enumerate(roles):
        tracker = frame.trackers.add()
        tracker.role = role
        tracker.px = 0.1 * i + 0.001 * frame_idx
        tracker.py = 0.2 * i + 0.001 * frame_idx
        tracker.pz = 0.3 * i + 0.001 * frame_idx
        tracker.qw = 1.0
        tracker.qx = 0.0
        tracker.qy = 0.0
        tracker.qz = 0.0
    return frame


def send_frames(host: str, port: int, roles: Iterable[str], frames: int, hz: float):
    roles = list(roles)
    base_time_ns = time.time_ns()
    delay = 1.0 / hz if hz > 0 else 0.0
    with socket.create_connection((host, port), timeout=5) as sock:
        for idx in range(frames):
            frame = build_dummy_frame(idx, roles, base_time_ns)
            payload = frame.SerializeToString()
            sock.sendall(HEADER_STRUCT.pack(len(payload)) + payload)
            if delay:
                time.sleep(delay)


def parse_args():
    parser = argparse.ArgumentParser(description="Mock Vive sender without hardware")
    parser.add_argument("--host", default="127.0.0.1", help="Receiver host")
    parser.add_argument("--port", type=int, default=50051, help="Receiver port")
    parser.add_argument("--roles", nargs="+", default=["right_elbow", "left_elbow", "chest"])
    parser.add_argument("--frames", type=int, default=10, help="Number of frames to send")
    parser.add_argument("--hz", type=float, default=30.0, help="Send rate (Hz)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        send_frames(args.host, args.port, args.roles, args.frames, args.hz)
    except KeyboardInterrupt:
        print("Stopped by user")
