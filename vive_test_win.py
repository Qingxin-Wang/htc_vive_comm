"""
vive_test_win.py
适配 Windows SteamVR 的 Vive Tracker 获取脚本
"""

import ctypes
import time
import xr
import glfw
from OpenGL.GL import *
from OpenGL.WGL import *
from ctypes import cast, byref, POINTER, c_void_p
from open3d_vis_obj import VIVEOpen3DVisualizer

print("正在初始化 OpenXR (Windows OpenGL)...")

def requested_api_version():
    """Force OpenXR 1.0 for SteamVR compatibility."""
    # pyopenxr wants a .number(); use xr.Version when it exists
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


class ContextObject:
    def __init__(self):
        self.instance = None
        self.session = None
        self.system_id = None
        self.space = None
        self.window = None
        self.action_set = None
        self.pose_action = None
        self.session_state = xr.SessionState.IDLE
        self.default_action_set = None
        self.action_sets = []
        self.graphics_binding = None
        
    def __enter__(self):
        # 1. 创建 Instance
        api_version = requested_api_version()
        extensions = [
            xr.KHR_OPENGL_ENABLE_EXTENSION_NAME, 
            xr.extension.HTCX_vive_tracker_interaction.NAME
        ]
        
        self.instance = xr.create_instance(
            create_info=xr.InstanceCreateInfo(
                enabled_extension_names=extensions,
                application_info=xr.ApplicationInfo(
                    application_name="ViveTrackerReader",
                    application_version=1,
                    engine_name="PyOpenXR",
                    engine_version=1,
                    # 【关键修复】: 强制请求 OpenXR 1.0.x 版本，兼容 SteamVR
                    api_version=api_version,
                ),
            )
        )
        
        # 2. 获取 System ID
        self.system_id = xr.get_system(
            instance=self.instance,
            get_info=xr.SystemGetInfo(
                form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY
            ),
        )
        
        # 3. Get graphics requirements (must run before create_session)
        get_gl_req = cast(
            xr.get_instance_proc_addr(self.instance, "xrGetOpenGLGraphicsRequirementsKHR"),
            xr.PFN_xrGetOpenGLGraphicsRequirementsKHR,
        )
        graphics_requirements = xr.GraphicsRequirementsOpenGLKHR()
        result = get_gl_req(self.instance, self.system_id, byref(graphics_requirements))
        if xr.check_result(result).is_exception():
            raise result

        # 4. 初始化 GLFW 隐藏窗口
        if not glfw.init():
            raise Exception("GLFW initialization failed")
            
        glfw.window_hint(glfw.VISIBLE, False)
        glfw.window_hint(glfw.DOUBLEBUFFER, False)
        self.window = glfw.create_window(640, 480, "Hidden Window", None, None)
        if not self.window:
            raise Exception("Failed to create GLFW window")
            
        glfw.make_context_current(self.window)
        
        # 5. 绑定图形上下文
        hwnd = glfw.get_win32_window(self.window)
        hglrc = wglGetCurrentContext()
        hdc = wglGetCurrentDC()
        
        self.graphics_binding = xr.GraphicsBindingOpenGLWin32KHR(
            h_dc=hdc,
            h_glrc=hglrc
        )
        
        # 6. 创建 Session
        self.session = xr.create_session(
            instance=self.instance,
            create_info=xr.SessionCreateInfo(
                system_id=self.system_id,
                next=cast(byref(self.graphics_binding), c_void_p)
            ),
        )
        
        # 7. 创建 Reference Space
        self.space = xr.create_reference_space(
            session=self.session,
            create_info=xr.ReferenceSpaceCreateInfo(
                reference_space_type=xr.ReferenceSpaceType.STAGE,
                pose_in_reference_space=xr.Posef()
            )
        )
        
        # 初始化 Action Set
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
        if self.session: xr.destroy_session(self.session)
        if self.instance: xr.destroy_instance(self.instance)
        if self.window: glfw.terminate()

    # 帧循环
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
                    # Some runtimes emit extension events with unknown type ids; skip those.
                    try:
                        event_type = xr.StructureType(event_buffer.type)
                    except ValueError:
                        continue
                    if event_type == xr.StructureType.EVENT_DATA_SESSION_STATE_CHANGED:
                        event = cast(byref(event_buffer), POINTER(xr.EventDataSessionStateChanged)).contents
                        state = xr.SessionState(event.state)
                        self.session_state = state
                        if state == xr.SessionState.READY:
                            xr.begin_session(self.session, xr.SessionBeginInfo(xr.ViewConfigurationType.PRIMARY_STEREO))
                            session_running = True
                            print("VR Session Ready! 开始接收数据...")
                        elif state == xr.SessionState.STOPPING:
                            xr.end_session(self.session)
                            session_running = False
                        elif state == xr.SessionState.EXITING:
                            return
                except xr.EventUnavailable:
                    break
            
            if not session_running:
                time.sleep(0.1)
                continue

            # 隐藏窗口的 GL 上下文要保持当前，再调 frame API
            glfw.make_context_current(self.window)

            frame_state = xr.wait_frame(self.session)
            xr.begin_frame(self.session)
            yield frame_state
            # Open3D 可能切了上下文，end_frame 前再设回
            glfw.make_context_current(self.window)
            xr.end_frame(self.session, xr.FrameEndInfo(
                display_time=frame_state.predicted_display_time,
                environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE
            ))

def main():
    visualizer = VIVEOpen3DVisualizer()
    first_flags = {'right_elbow': True, 'left_elbow': True, 'chest': True}

    with ContextObject() as context:
        instance = context.instance
        session = context.session

        # 获取扩展函数
        enumerateViveTrackerPathsHTCX = cast(
            xr.get_instance_proc_addr(instance, "xrEnumerateViveTrackerPathsHTCX"),
            xr.PFN_xrEnumerateViveTrackerPathsHTCX
        )

        # 定义角色
        role_strings = [
            "handheld_object", "left_foot", "right_foot", "left_shoulder",
            "right_shoulder", "left_elbow", "right_elbow", "left_knee",
            "right_knee", "waist", "chest", "camera", "keyboard"
        ]
        
        # 创建 Action
        role_paths = [xr.string_to_path(instance, f"/user/vive_tracker_htcx/role/{role}") for role in role_strings]
        pose_action = xr.create_action(
            action_set=context.default_action_set,
            create_info=xr.ActionCreateInfo(
                action_type=xr.ActionType.POSE_INPUT,
                action_name="tracker_pose",
                localized_action_name="Tracker Pose",
                count_subaction_paths=len(role_paths),
                subaction_paths=(xr.Path * len(role_paths))(*role_paths)
            )
        )
        
        # 建议绑定
        bindings = []
        for role in role_strings:
            bindings.append(xr.ActionSuggestedBinding(pose_action, xr.string_to_path(instance, f"/user/vive_tracker_htcx/role/{role}/input/grip/pose")))
        
        xr.suggest_interaction_profile_bindings(
            instance=instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(instance, "/interaction_profiles/htc/vive_tracker_htcx"),
                count_suggested_bindings=len(bindings),
                suggested_bindings=(xr.ActionSuggestedBinding * len(bindings))(*bindings)
            )
        )

        tracker_spaces = [xr.create_action_space(session=session, create_info=xr.ActionSpaceCreateInfo(action=pose_action, subaction_path=path)) for path in role_paths]

        # === 主循环 ===
        print("进入主循环，请确保 SteamVR 中 Tracker 图标为绿色...")
        for frame_state in context.frame_loop():
            if context.session_state != xr.SessionState.FOCUSED:
                # 等待头显进入 FOCUSED，避免 SessionNotFocused 错误
                continue
            if not frame_state.should_render:
                continue
            active_set = xr.ActiveActionSet(context.default_action_set, xr.NULL_PATH)
            xr.sync_actions(session, xr.ActionsSyncInfo(count_active_action_sets=1, active_action_sets=ctypes.pointer(active_set)))
            
            for i, space in enumerate(tracker_spaces):
                location = xr.locate_space(space, context.space, frame_state.predicted_display_time)
                if location.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT:
                    role = role_strings[i]
                    pose = location.pose
                    
                    # Visualizer 更新
                    p = [pose.position.x, pose.position.y, pose.position.z]
                    q = [pose.orientation.w, pose.orientation.x, pose.orientation.y, pose.orientation.z]
                    
                    idx = -1
                    if role == 'right_elbow': idx = 0
                    elif role == 'left_elbow': idx = 1
                    elif role == 'chest': idx = 2
                    
                    # 实时打印坐标/四元数
                    print(f"{role}: "
                          f"pos=({pose.position.x:.4f}, {pose.position.y:.4f}, {pose.position.z:.4f}) "
                          f"quat=({pose.orientation.w:.4f}, {pose.orientation.x:.4f}, "
                          f"{pose.orientation.y:.4f}, {pose.orientation.z:.4f})")

                    if idx != -1:
                        if first_flags.get(role, False):
                            visualizer.set_pose_first(p, q, idx)
                            first_flags[role] = False
                        else:
                            visualizer.set_pose(p, q, idx)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"程序错误: {e}")
        import traceback
        traceback.print_exc()
    except KeyboardInterrupt:
        print("用户终止")
