# DexCap Vive Communication Demo (Standalone)

This folder mirrors the DexCap Vive streaming scripts and adds a mock sender so you can validate the protobuf/TCP pipeline without real Vive hardware.

## Files
- `vive_stream_sender_win.py`: Windows SteamVR sender (real trackers, OpenXR).
- `vive_stream_receiver.py`: Linux/any receiver that logs frames and can publish to Redis.
- `vive_stream_pb2.py` + `protos/vive_stream.proto`: Protobuf schema and generated helper.
- `mock_sender.py`: Sends synthetic tracker poses over the same wire format (no OpenXR needed).
- `test_mock_stream.py`: Unit test that round-trips mock frames through a local TCP socket.

## Quick start (no Vive required)
1) Install deps (Python 3.8+):
   ```bash
   pip install protobuf
   ```
   For the real Windows sender you also need `pyopenxr`, `glfw`, and OpenGL bindings per DexCap install docs.
2) In one terminal, run a receiver:
   ```bash
   python vive_stream_receiver.py --host 0.0.0.0 --port 50051 --print-every 1
   ```
3) In another terminal, send mock data:
   ```bash
   python mock_sender.py --host 127.0.0.1 --port 50051 --frames 5 --hz 10
   ```
   You should see frames printed by the receiver; Redis publishing is optional via `--redis-host`.

## Real Vive streaming (with hardware)
- Start receiver on Linux/target:
  ```bash
  python vive_stream_receiver.py --host 0.0.0.0 --port 50051 --print-every 1
  ```
- Start sender on Windows (SteamVR running, trackers paired, VIVE Business Streaming disabled):
  ```bash
  python vive_stream_sender_win.py --host <receiver_ip> --port 50051 --roles right_elbow left_elbow chest --verbose
  ```
- SteamVR 无头模式参考：<https://github.com/username223/SteamVRNoHeadset>

## Running the unit test
The test spins up a local TCP server and uses `mock_sender` to verify framing and payloads:
```bash
python -m unittest test_mock_stream
```
No Vive hardware or OpenXR is needed for this test.

## SteamVR troubleshooting (VIVE Ultimate Tracker)
- Disable VIVE Business Streaming driver to avoid OpenXR conflicts: edit `C:\Program Files (x86)\Steam\config\steamvr.vrsettings`, find `driver_vive_business_streaming` (or add it) and set `"enable": false` (leave `"loadPriority": -999`). Do this with SteamVR fully closed.
- If the block is missing, add before the final `}`:
  ```json
  "driver_vive_business_streaming" : {
     "enable" : false,
     "loadPriority" : -999
  }
  ```
- Check SteamVR logs for driver load/skip details: open `C:\Program Files (x86)\Steam\logs\vrserver.txt` and search for `Loading driver vive_business_streaming`, `Skipping driver vive_business_streaming`, or errors/failures to confirm the driver is disabled and to spot OpenXR issues.
