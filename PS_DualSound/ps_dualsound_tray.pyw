"""PS_DualSound —— 右下角托盘版。

单击图标弹出原生菜单：震动强度、扬声器、暂停、开机自启、退出。
只用 Python 标准库 ctypes 调用 Win32，不需要额外的界面库。
"""
import ctypes
import os
import sys
import threading
import time
import traceback
import winreg
from ctypes import wintypes as W
from pathlib import Path

import ps_dualsound as bridge

APP_NAME = "PS_DualSound"
WINDOW_CLASS = "PSDualSoundTray"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RUN_VALUE = "PSDualSound"
THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
GLYPH = ""  # Segoe Fluent Icons: Game

WM_NULL, WM_DESTROY, WM_CLOSE, WM_SETTINGCHANGE = 0x00, 0x02, 0x10, 0x1A
WM_DISPLAYCHANGE, WM_CONTEXTMENU, WM_TIMER = 0x7E, 0x7B, 0x113
WM_TRAY, WM_SHOW_MENU = 0x8001, 0x8002
NIN_SELECT, NIN_KEYSELECT = 0x400, 0x401
NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0, 0x1, 0x8, 0x800

CMD_SOUND, CMD_PAUSE, CMD_AUTOSTART, CMD_QUIT = 1, 2, 3, 4
CMD_LEVEL, CMD_DEVICE = 100, 200

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
shell32 = ctypes.WinDLL("shell32")
kernel32 = ctypes.WinDLL("kernel32")
ole32 = ctypes.WinDLL("ole32")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", W.INT),
                ("cbWndExtra", W.INT), ("hInstance", W.HANDLE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", W.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG),
                ("biPlanes", W.WORD), ("biBitCount", W.WORD), ("biCompression", W.DWORD),
                ("biSizeImage", W.DWORD), ("biXPels", W.LONG), ("biYPels", W.LONG),
                ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", W.BOOL), ("xHotspot", W.DWORD), ("yHotspot", W.DWORD),
                ("hbmMask", W.HBITMAP), ("hbmColor", W.HBITMAP)]


def declare(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype, f.argtypes = restype, argtypes


# 64 位 Windows 下句柄是 64 位，必须逐个声明类型
declare(kernel32, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)
declare(user32, "DefWindowProcW", LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
declare(user32, "RegisterClassW", W.ATOM, ctypes.POINTER(WNDCLASS))
declare(user32, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, W.INT,
        W.INT, W.INT, W.INT, W.HWND, W.HMENU, W.HANDLE, W.LPVOID)
declare(user32, "DestroyWindow", W.BOOL, W.HWND)
declare(user32, "FindWindowW", W.HWND, W.LPCWSTR, W.LPCWSTR)
declare(user32, "PostMessageW", W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
declare(user32, "SetForegroundWindow", W.BOOL, W.HWND)
declare(user32, "SetTimer", ctypes.c_size_t, W.HWND, ctypes.c_size_t, W.UINT, W.LPVOID)
declare(user32, "GetDpiForWindow", W.UINT, W.HWND)
declare(user32, "GetSystemMetricsForDpi", W.INT, W.INT, W.UINT)
declare(user32, "CreatePopupMenu", W.HMENU)
declare(user32, "AppendMenuW", W.BOOL, W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR)
declare(user32, "CheckMenuRadioItem", W.BOOL, W.HMENU, W.UINT, W.UINT, W.UINT, W.UINT)
declare(user32, "TrackPopupMenuEx", W.INT, W.HMENU, W.UINT, W.INT, W.INT, W.HWND, W.LPVOID)
declare(user32, "DestroyMenu", W.BOOL, W.HMENU)
declare(user32, "DrawTextW", W.INT, W.HDC, W.LPCWSTR, W.INT, ctypes.POINTER(W.RECT), W.UINT)
declare(user32, "CreateIconIndirect", W.HICON, ctypes.POINTER(ICONINFO))
declare(user32, "DestroyIcon", W.BOOL, W.HICON)
declare(gdi32, "CreateCompatibleDC", W.HDC, W.HDC)
declare(gdi32, "CreateDIBSection", W.HBITMAP, W.HDC, ctypes.POINTER(BITMAPINFOHEADER), W.UINT,
        ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD)
declare(gdi32, "CreateBitmap", W.HBITMAP, W.INT, W.INT, W.UINT, W.UINT, W.LPVOID)
declare(gdi32, "CreateFontW", W.HFONT, *([W.INT] * 5), *([W.DWORD] * 8), W.LPCWSTR)
declare(gdi32, "SelectObject", W.HANDLE, W.HDC, W.HANDLE)
declare(gdi32, "SetTextColor", W.DWORD, W.HDC, W.DWORD)
declare(gdi32, "SetBkMode", W.INT, W.HDC, W.INT)
declare(gdi32, "GdiFlush", W.BOOL)
declare(gdi32, "DeleteObject", W.BOOL, W.HANDLE)
declare(gdi32, "DeleteDC", W.BOOL, W.HDC)
declare(shell32, "Shell_NotifyIconW", W.BOOL, W.DWORD, ctypes.POINTER(NOTIFYICONDATA))


def read_reg(key, name, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def autostart_command():
    exe = Path(sys.executable).with_name("pythonw.exe")
    return f'"{exe}" "{Path(__file__).resolve()}"'


def autostart_blocked():
    """在 Windows「启动应用」里被关掉时，第一个字节是奇数。"""
    flag = read_reg(APPROVED_KEY, RUN_VALUE)
    return bool(flag and flag[0] & 1)


def autostart_enabled():
    return bool(read_reg(RUN_KEY, RUN_VALUE)) and not autostart_blocked()


def toggle_autostart():
    """只在用户点击菜单里的「开机自启」时调用。"""
    if autostart_blocked():
        os.startfile("ms-settings:startupapps")  # 尊重用户在系统设置里的选择
        return
    enable = not autostart_enabled()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enable:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            winreg.DeleteValue(k, RUN_VALUE)


def enable_native_look():
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # Per-monitor V2
    if sys.getwindowsversion().build >= 18362:
        try:  # 让右键菜单跟随系统深色模式
            ux = ctypes.WinDLL("uxtheme")
            ux[135](1)  # SetPreferredAppMode(AllowDark)
            ux[136]()   # FlushMenuThemes
        except (OSError, AttributeError):
            pass


def render_glyph(size):
    """用系统图标字体按实际像素大小绘制，返回每个像素的不透明度。"""
    font_name = "Segoe Fluent Icons" if sys.getwindowsversion().build >= 22000 else "Segoe MDL2 Assets"
    dc = gdi32.CreateCompatibleDC(None)
    hdr = BITMAPINFOHEADER(40, size, -size, 1, 32)
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(dc, ctypes.byref(hdr), 0, ctypes.byref(bits), None, 0)
    font = gdi32.CreateFontW(-size, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 4, 0, font_name)
    old_bmp, old_font = gdi32.SelectObject(dc, bmp), gdi32.SelectObject(dc, font)
    ctypes.memset(bits, 0, size * size * 4)
    gdi32.SetTextColor(dc, 0xFFFFFF)
    gdi32.SetBkMode(dc, 1)
    rect = W.RECT(0, 0, size, size)
    user32.DrawTextW(dc, GLYPH, 1, ctypes.byref(rect), 0x1 | 0x4 | 0x20 | 0x100)
    gdi32.GdiFlush()
    coverage = ctypes.string_at(bits, size * size * 4)[1::4]
    gdi32.SelectObject(dc, old_bmp)
    gdi32.SelectObject(dc, old_font)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteObject(font)
    gdi32.DeleteDC(dc)
    return coverage


def make_icon(size, light_taskbar, dim):
    shade = 0 if light_taskbar else 255
    opacity = 0.45 if dim else 1.0
    pixels = b"".join(bytes((shade, shade, shade, round(a * opacity))) for a in render_glyph(size))
    hdr = BITMAPINFOHEADER(40, size, -size, 1, 32)
    bits = ctypes.c_void_p()
    color = gdi32.CreateDIBSection(None, ctypes.byref(hdr), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, pixels, len(pixels))
    mask_bits = ctypes.create_string_buffer(((size + 15) // 16) * 2 * size)
    mask = gdi32.CreateBitmap(size, size, 1, 1, mask_bits)
    icon = user32.CreateIconIndirect(ctypes.byref(ICONINFO(True, 0, 0, mask, color)))
    gdi32.DeleteObject(color)
    gdi32.DeleteObject(mask)
    return icon


class AudioWorker(threading.Thread):
    """后台音频线程：等待设备、转发、断开后自动重连。"""

    def __init__(self, gain=1.0):
        super().__init__(daemon=True)
        st = bridge.load_settings()
        level = st.get("level", 0)
        self.level = level if level in range(len(bridge.LEVELS)) else 0
        self.out_name = st.get("out")
        self.paused = bool(st.get("paused", False))
        self.gain = gain
        self.status = "正在启动"
        self.running = False
        self.quitting = False
        self.changed = threading.Event()

    def update(self, **changes):
        for key, value in changes.items():
            setattr(self, {"out": "out_name"}.get(key, key), value)
        bridge.save_settings(**changes)
        self.changed.set()

    def shutdown(self):
        self.quitting = True
        self.changed.set()

    def _set(self, status, running=False):
        self.status, self.running = status, running

    def run(self):
        ole32.CoInitializeEx(None, 0)  # COM 需要在每个线程单独初始化
        try:
            while not self.quitting:
                self.changed.clear()
                if self.quitting:
                    break
                retry = 3
                try:
                    if self.paused:
                        self._set("已暂停")
                        retry = None
                    else:
                        ds, outs = bridge.list_devices()
                        path = None if ds else bridge.bt.find()
                        level = self.level
                        name, strength, *_ = bridge.LEVELS[level]
                        out = next((s for s in outs if bridge.same_device(
                            bridge.device_name(s), self.out_name)), None)
                        if path and strength:
                            bridge.run_bluetooth(
                                path, level, self.changed.is_set,
                                lambda src: self._set(f"蓝牙运行中 · {name}", True))
                            continue
                        elif path:
                            self._set("蓝牙已连接 · 增强已关")
                        elif not ds:
                            self._set("等待手柄连接（USB 或蓝牙）")
                        elif not self.out_name:
                            self._set("请选择扬声器")
                        elif not out:
                            self._set("等待扬声器连接")
                        else:
                            bridge.run(ds, out, level, self.gain, self.changed.is_set,
                                       lambda: self._set(f"有线运行中 · {name}", True))
                            continue
                except Exception as e:
                    self._set(f"音频设备重连中（{str(e) or type(e).__name__}）")
                    retry = 2
                self.changed.wait(retry)
        finally:
            self._set("已停止")
            ole32.CoUninitialize()


class TrayApp:
    def __init__(self, worker):
        self.worker = worker
        self.icon = None
        self.look = None
        self.added = False
        self.menu_open = False
        self.devices = []
        self._proc = WNDPROC(self._window_proc)  # 必须保留引用
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        wc = WNDCLASS(lpfnWndProc=self._proc, hInstance=kernel32.GetModuleHandleW(None),
                      lpszClassName=WINDOW_CLASS)
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = user32.CreateWindowExW(0, WINDOW_CLASS, APP_NAME, 0, 0, 0, 0, 0,
                                           None, None, wc.hInstance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.nid = NOTIFYICONDATA(cbSize=ctypes.sizeof(NOTIFYICONDATA), hWnd=self.hwnd, uID=1,
                                  uFlags=0x1 | 0x2 | 0x4 | 0x80, uCallbackMessage=WM_TRAY)
        self.refresh(force=True)
        user32.SetTimer(self.hwnd, 1, 1000, None)

    def refresh(self, force=False):
        size = user32.GetSystemMetricsForDpi(49, user32.GetDpiForWindow(self.hwnd))  # SM_CXSMICON
        light = bool(read_reg(THEME_KEY, "SystemUsesLightTheme", 0))
        look = (size, light, not self.worker.running)
        tip = f"{APP_NAME}\n{self.worker.status}"[:127]
        if not force and self.added and look == self.look and tip == self.nid.szTip:
            return
        old = None
        if look != self.look:
            old, self.icon = self.icon, make_icon(*look)
            self.look = look
        self.nid.hIcon, self.nid.szTip = self.icon, tip
        if not (self.added and shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))):
            # 开机时任务栏可能还没准备好，失败了下一秒会再试
            self.added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid)))
            if self.added:
                self.nid.uVersion = 4
                shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(self.nid))
        if old:
            user32.DestroyIcon(old)

    def build_menu(self):
        w, menu = self.worker, user32.CreatePopupMenu()

        def add(text, cmd=0, flags=MF_STRING):
            # & 在菜单里是快捷键标记，需要转义
            user32.AppendMenuW(menu, flags, cmd, text.replace("&", "&&"))

        def separator():
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        try:
            ds, outs = bridge.list_devices()
            self.devices = [bridge.device_name(s) for s in outs]
            wireless = ds is None and bridge.bt.find() is not None
            default = bridge.sc.default_speaker()
            wrong_default = ds is not None and default.id != ds.id
            following = bridge.device_name(default)
        except Exception:
            self.devices, wrong_default, wireless = [], False, False

        add(w.status, flags=MF_GRAYED)
        if wrong_default:
            add("⚠ Windows 输出不是手柄，点此设置", CMD_SOUND)
        separator()
        add("震动", flags=MF_GRAYED)
        for i, (name, *_) in enumerate(bridge.LEVELS):
            add("关闭增强（原生震动需有线）" if wireless and i == 0 else name, CMD_LEVEL + i)
        user32.CheckMenuRadioItem(menu, CMD_LEVEL, CMD_LEVEL + len(bridge.LEVELS) - 1,
                                  CMD_LEVEL + w.level, 0)
        separator()
        if wireless:  # 蓝牙时声音本来就在音箱里，不需要转发
            self.devices = []
            add("扬声器（跟随 Windows 输出）", flags=MF_GRAYED)
            add(following, CMD_SOUND, MF_CHECKED)
        else:
            add("扬声器", flags=MF_GRAYED)
            selected = None
            for i, name in enumerate(self.devices):
                add(name, CMD_DEVICE + i)
                if selected is None and bridge.same_device(name, w.out_name):
                    selected = i
            if selected is not None:
                user32.CheckMenuRadioItem(menu, CMD_DEVICE, CMD_DEVICE + len(self.devices) - 1,
                                          CMD_DEVICE + selected, 0)
            elif w.out_name:
                add(f"{w.out_name}（未连接）", flags=MF_GRAYED | MF_CHECKED)
        separator()
        add("暂停", CMD_PAUSE, MF_CHECKED if w.paused else MF_STRING)
        add("开机自启", CMD_AUTOSTART, MF_CHECKED if autostart_enabled() else MF_STRING)
        add("退出", CMD_QUIT)
        return menu

    def show_menu(self):
        if self.menu_open:
            return
        self.menu_open = True
        try:
            menu = self.build_menu()
            pt = W.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)  # 否则点菜单外面时菜单不会关闭
            # RIGHTBUTTON | BOTTOMALIGN | RETURNCMD
            cmd = user32.TrackPopupMenuEx(menu, 0x2 | 0x20 | 0x100, pt.x, pt.y, self.hwnd, None)
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
            user32.DestroyMenu(menu)
        finally:
            self.menu_open = False
        if cmd:
            self.dispatch(cmd)

    def dispatch(self, cmd):
        w = self.worker
        if cmd == CMD_SOUND:
            os.startfile("ms-settings:sound")
        elif cmd == CMD_PAUSE:
            w.update(paused=not w.paused)
        elif cmd == CMD_AUTOSTART:
            toggle_autostart()
        elif cmd == CMD_QUIT:
            user32.DestroyWindow(self.hwnd)
        elif CMD_DEVICE <= cmd < CMD_DEVICE + len(self.devices):
            w.update(out=self.devices[cmd - CMD_DEVICE], paused=False)
        elif CMD_LEVEL <= cmd < CMD_LEVEL + len(bridge.LEVELS):
            w.update(level=cmd - CMD_LEVEL, paused=False)

    def _window_proc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_TRAY:
                if lp & 0xFFFF in (NIN_SELECT, NIN_KEYSELECT, WM_CONTEXTMENU):
                    self.show_menu()
                return 0
            if msg == WM_SHOW_MENU:
                self.show_menu()
                return 0
            if msg == WM_TIMER and wp == 1:
                self.refresh()
                return 0
            if msg == self.taskbar_created:  # 资源管理器重启后要重新添加图标
                self.added = False
                self.refresh(force=True)
                return 0
            if msg in (WM_SETTINGCHANGE, WM_DISPLAYCHANGE) and hasattr(self, "nid"):
                self.refresh()
            elif msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
                self.worker.shutdown()
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            log_error()
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def loop(self):
        msg = W.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self.worker.join(2)


def log_error():
    """没有控制台，错误写到脚本旁边（只保留最近一次）。"""
    try:
        Path(__file__).with_name("tray_error.log").write_text(
            f"{time.ctime()}\n{traceback.format_exc()}", encoding="utf-8")
    except OSError:
        pass


def main():
    if not bridge.claim_single_instance():
        hwnd = user32.FindWindowW(WINDOW_CLASS, None)
        if hwnd:  # 已在运行：让它弹出菜单
            user32.AllowSetForegroundWindow(-1)
            user32.PostMessageW(hwnd, WM_SHOW_MENU, 0, 0)
        else:
            user32.MessageBoxW(None, "命令行版 PS_DualSound 正在运行，请先关掉那个窗口。", APP_NAME, 0x40)
        return
    enable_native_look()
    worker = AudioWorker()
    app = TrayApp(worker)
    worker.start()
    if "--menu" in sys.argv:  # 从桌面快捷方式启动时直接弹出选项
        user32.PostMessageW(app.hwnd, WM_SHOW_MENU, 0, 0)
    app.loop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error()
        user32.MessageBoxW(None, "启动失败，详情见 tray_error.log", APP_NAME, 0x10)
