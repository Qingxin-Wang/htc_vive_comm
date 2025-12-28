"""
Stream Vive tracker poses from Windows to a Linux host over TCP using protobuf.

Usage example:
    python vive_stream_sender_win.py --host 192.168.1.20 --port 50051

The Linux side can run vive_stream_receiver.py to accept and republish the data.
"""

import argparse
import ctypes
import socket
import struct
import time
from ctypes import POINTER, byref, cast, c_void_p
from typing import Dict, List

import glfw
import xr
from OpenGL.WGL import wglGetCurrentContext, wglGetCurrentDC

from vive_stream_pb2 import TrackerPose, ViveFrame


def requested_api_version():
    """Force OpenXR 1.0 for SteamVR compatibility."""
    if hasattr(xr, "Version"):
        return xr.Version(1, 0, 0)
    if hasattr(xr, "XR_MAKE_VERSION"):
        val = xr.XR_MAKE_VERSION(1, 0, 0)
    elif hasattr(xr, "make_version"):
        val = xr.make_version(1, 0, 0)
    else:
        val = (1 << 48)

    class _CompatVersion(int):
        def number(self):
            return int(self)

    return _CompatVersion(val)


class WinViveContext:
    """Minimal OpenXR context for SteamVR trackers on Windows."""

    def __init__(self):
        self.instance = None
        self.session = None
        self.system_id = None
        self.space = None
        self.window = None
        self.default_action_set = None
        self.action_sets: List[xr.ActionSet] = []
        self.session_state = xr.SessionState.IDLE
        self.graphics_binding = None

    def __enter__(self):
        extensions = [
            xr.KHR_OPENGL_ENABLE_EXTENSION_NAME,
            xr.extension.HTCX_vive_tracker_interaction.NAME,
        ]
        api_version = requested_api_version()
        self.instance = xr.create_instance(
            create_info=xr.InstanceCreateInfo(
                enabled_extension_names=extensions,
                application_info=xr.ApplicationInfo(
                    application_name="DexCapViveStream",
                    application_version=1,
                    engine_name="PyOpenXR",
                    engine_version=1,
                    api_version=api_version,
                ),
            )
        )

        self.system_id = xr.get_system(
            instance=self.instance,
            get_info=xr.SystemGetInfo(
                form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY,
            ),
        )

        get_gl_req = cast(
            xr.get_instance_proc_addr(self.instance, "xrGetOpenGLGraphicsRequirementsKHR"),
            xr.PFN_xrGetOpenGLGraphicsRequirementsKHR,
        )
        graphics_requirements = xr.GraphicsRequirementsOpenGLKHR()
        result = get_gl_req(self.instance, self.system_id, byref(graphics_requirements))
        if xr.check_result(result).is_exception():
            raise result

        if not glfw.init():
            raise RuntimeError("GLFW initialization failed")
        glfw.window_hint(glfw.VISIBLE, False)
        glfw.window_hint(glfw.DOUBLEBUFFER, False)
        self.window = glfw.create_window(640, 480, "Hidden Window", None, None)
        if not self.window:
            raise RuntimeError("Failed to create GLFW window")
        glfw.make_context_current(self.window)

        hwnd = glfw.get_win32_window(self.window)
        hglrc = wglGetCurrentContext()
        hdc = wglGetCurrentDC()
        if not hwnd or not hglrc or not hdc:
            raise RuntimeError("Failed to acquire GL/WGL handles for OpenXR session")

        self.graphics_binding = xr.GraphicsBindingOpenGLWin32KHR(
            h_dc=hdc,
            h_glrc=hglrc,
        )

        self.session = xr.create_session(
            instance=self.instance,
            create_info=xr.SessionCreateInfo(
                system_id=self.system_id,
                next=cast(byref(self.graphics_binding), c_void_p),
            ),
        )
        self.space = xr.create_reference_space(
            session=self.session,
            create_info=xr.ReferenceSpaceCreateInfo(
                reference_space_type=xr.ReferenceSpaceType.STAGE,
                pose_in_reference_space=xr.Posef(),
            ),
        )
        self.default_action_set = xr.create_action_set(
            instance=self.instance,
            create_info=xr.ActionSetCreateInfo(
                action_set_name="default_action_set",
                localized_action_set_name="Default Action Set",
                priority=0,
            ),
        )
        self.action_sets.append(self.default_action_set)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            xr.destroy_session(self.session)
        if self.instance:
            xr.destroy_instance(self.instance)
        if self.window:
            glfw.terminate()

    def frame_loop(self):
        xr.attach_session_action_sets(
            session=self.session,
            attach_info=xr.SessionActionSetsAttachInfo(
                count_action_sets=len(self.action_sets),
                action_sets=(xr.ActionSet * len(self.action_sets))(*self.action_sets),
            ),
        )

        session_running = False
        while True:
            glfw.poll_events()
            while True:
                try:
                    event_buffer = xr.poll_event(self.instance)
                    try:
                        event_type = xr.StructureType(event_buffer.type)
                    except ValueError:
                        continue
                    if event_type == xr.StructureType.EVENT_DATA_SESSION_STATE_CHANGED:
                        event = cast(byref(event_buffer), POINTER(xr.EventDataSessionStateChanged)).contents
                        self.session_state = xr.SessionState(event.state)
                        if self.session_state == xr.SessionState.READY:
                            xr.begin_session(
                                self.session,
                                xr.SessionBeginInfo(xr.ViewConfigurationType.PRIMARY_STEREO),
                            )
                            session_running = True
                        elif self.session_state == xr.SessionState.STOPPING:
                            xr.end_session(self.session)
                            session_running = False
                        elif self.session_state == xr.SessionState.EXITING:
                            return
                except xr.EventUnavailable:
                    break

            if not session_running:
                time.sleep(0.05)
                continue

            glfw.make_context_current(self.window)
            frame_state = xr.wait_frame(self.session)
            xr.begin_frame(self.session)
            yield frame_state
            glfw.make_context_current(self.window)
            xr.end_frame(
                self.session,
                xr.FrameEndInfo(
                    display_time=frame_state.predicted_display_time,
                    environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE,
                ),
            )


HEADER_STRUCT = struct.Struct(">I")


def send_frame(sock: socket.socket, frame: ViveFrame):
    payload = frame.SerializeToString()
    sock.sendall(HEADER_STRUCT.pack(len(payload)) + payload)


def build_frame(
    role_strings: List[str],
    tracker_spaces: List[xr.Space],
    context: WinViveContext,
    locate_time,
    timestamp_ns: int,
) -> ViveFrame:
    frame = ViveFrame(timestamp_ns=timestamp_ns)
    for idx, space in enumerate(tracker_spaces):
        location = xr.locate_space(
            space=space,
            base_space=context.space,
            time=locate_time,
        )
        if location.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT:
            pose = location.pose
            tracker = frame.trackers.add()
            tracker.role = role_strings[idx]
            tracker.px = pose.position.x
            tracker.py = pose.position.y
            tracker.pz = pose.position.z
            tracker.qw = pose.orientation.w
            tracker.qx = pose.orientation.x
            tracker.qy = pose.orientation.y
            tracker.qz = pose.orientation.z
    return frame


def stream(args: argparse.Namespace):
    role_strings = args.roles
    print(f"Connecting to Linux host {args.host}:{args.port} ...")
    while True:
        try:
            with socket.create_connection((args.host, args.port), timeout=5) as sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print("TCP connection established, starting Vive capture...")
                run_stream_loop(sock, role_strings, args)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            print(f"Connection failed: {exc}; retrying in {args.reconnect_delay}s")
            time.sleep(args.reconnect_delay)


def run_stream_loop(sock: socket.socket, role_strings: List[str], args: argparse.Namespace):
    with WinViveContext() as context:
        instance = context.instance
        session = context.session

        enumerate_vive_paths = cast(
            xr.get_instance_proc_addr(instance, "xrEnumerateViveTrackerPathsHTCX"),
            xr.PFN_xrEnumerateViveTrackerPathsHTCX,
        )

        role_paths = [
            xr.string_to_path(instance, f"/user/vive_tracker_htcx/role/{role}")
            for role in role_strings
        ]
        pose_action = xr.create_action(
            action_set=context.default_action_set,
            create_info=xr.ActionCreateInfo(
                action_type=xr.ActionType.POSE_INPUT,
                action_name="tracker_pose",
                localized_action_name="Tracker Pose",
                count_subaction_paths=len(role_paths),
                subaction_paths=(xr.Path * len(role_paths))(*role_paths),
            ),
        )

        bindings = [
            xr.ActionSuggestedBinding(
                pose_action,
                xr.string_to_path(instance, f"/user/vive_tracker_htcx/role/{role}/input/grip/pose"),
            )
            for role in role_strings
        ]
        xr.suggest_interaction_profile_bindings(
            instance=instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(
                    instance, "/interaction_profiles/htc/vive_tracker_htcx"
                ),
                count_suggested_bindings=len(bindings),
                suggested_bindings=(xr.ActionSuggestedBinding * len(bindings))(*bindings),
            ),
        )

        tracker_spaces = [
            xr.create_action_space(
                session=session,
                create_info=xr.ActionSpaceCreateInfo(action=pose_action, subaction_path=path),
            )
            for path in role_paths
        ]

        print("Waiting for headset to enter FOCUSED state (wear HMD)...")
        for frame_state in context.frame_loop():
            if context.session_state != xr.SessionState.FOCUSED:
                continue
            active_set = xr.ActiveActionSet(context.default_action_set, xr.NULL_PATH)
            xr.sync_actions(
                session,
                xr.ActionsSyncInfo(
                    count_active_action_sets=1, active_action_sets=ctypes.pointer(active_set)
                ),
            )
            timestamp_ns = time.time_ns()
            frame = build_frame(
                role_strings,
                tracker_spaces,
                context,
                frame_state.predicted_display_time,
                timestamp_ns,
            )
            if not frame.trackers:
                continue
            try:
                send_frame(sock, frame)
            except OSError as exc:
                print(f"Socket send failed: {exc}; reconnecting...")
                return
            if args.verbose:
                print(
                    f"sent {len(frame.trackers)} trackers at {timestamp_ns} ns "
                    f"first={frame.trackers[0].role if frame.trackers else 'none'}"
                )


def parse_args():
    parser = argparse.ArgumentParser(description="Windows Vive tracker sender over protobuf/TCP")
    parser.add_argument("--host", required=True, help="Linux receiver IP/hostname")
    parser.add_argument("--port", type=int, default=50051, help="TCP port on Linux receiver")
    parser.add_argument(
        "--roles",
        nargs="+",
        default=[
            "right_elbow",
            "left_elbow",
            "chest",
        ],
        help="Vive tracker roles to stream",
    )
    parser.add_argument("--verbose", action="store_true", help="Print each frame summary")
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=2.0,
        help="Seconds to wait before retrying TCP connection",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        stream(args)
    except KeyboardInterrupt:
        print("Stopped by user")
