"""
Linux-side receiver for Vive tracker protobuf stream from Windows.

Example:
    python vive_stream_receiver.py --host 0.0.0.0 --port 50051 --redis-host localhost
"""

import argparse
import json
import socket
import struct
import time
from typing import Optional

from vive_stream_pb2 import ViveFrame

try:
    import redis  # type: ignore
except ImportError:
    redis = None


HEADER_STRUCT = struct.Struct(">I")


def recvall(conn: socket.socket, length: int) -> Optional[bytes]:
    data = b""
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def log_frame(frame: ViveFrame, frame_idx: int):
    tracker_summary = ", ".join(
        f"{t.role}: pos=({t.px:.3f},{t.py:.3f},{t.pz:.3f})"
        for t in frame.trackers
    )
    print(f"[{frame_idx}] ts={frame.timestamp_ns} trackers={len(frame.trackers)} {tracker_summary}")


def to_json(frame: ViveFrame) -> str:
    return json.dumps(
        {
            "timestamp_ns": frame.timestamp_ns,
            "trackers": [
                {
                    "role": t.role,
                    "px": t.px,
                    "py": t.py,
                    "pz": t.pz,
                    "qw": t.qw,
                    "qx": t.qx,
                    "qy": t.qy,
                    "qz": t.qz,
                }
                for t in frame.trackers
            ],
        }
    )


def serve(args: argparse.Namespace):
    pub = None
    if args.redis_host:
        if redis is None:
            raise ImportError("redis is not installed; pip install redis")
        pub = redis.Redis(host=args.redis_host, port=args.redis_port, db=0)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(1)
        print(f"Listening on {args.host}:{args.port}")
        frame_idx = 0
        while True:
            conn, addr = server.accept()
            print(f"Client connected: {addr}")
            with conn:
                while True:
                    header = recvall(conn, HEADER_STRUCT.size)
                    if header is None:
                        print("Connection closed by peer")
                        break
                    (length,) = HEADER_STRUCT.unpack(header)
                    payload = recvall(conn, length)
                    if payload is None:
                        print("Connection closed mid-frame")
                        break
                    frame = ViveFrame()
                    frame.ParseFromString(payload)
                    frame_idx += 1
                    if args.print_every and frame_idx % args.print_every == 0:
                        log_frame(frame, frame_idx)
                    if pub:
                        pub.publish(args.redis_channel, to_json(frame))
            time.sleep(0.5)


def parse_args():
    parser = argparse.ArgumentParser(description="Linux receiver for Vive protobuf stream")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=50051, help="Bind port")
    parser.add_argument("--print-every", type=int, default=10, help="Log every N frames")
    parser.add_argument("--redis-host", help="Redis host to publish JSON (optional)")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--redis-channel", default="vive/trackers", help="Redis pubsub channel name")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        serve(parse_args())
    except KeyboardInterrupt:
        print("Stopped by user")
