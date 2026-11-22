"""DualSense 蓝牙震动传输：只用 Python 标准库，不需要驱动和管理员权限。

报告格式和调校值改写自 DualSense Companion 的 haptics.py / bridge.py
(https://github.com/vingt-2/dualsense-companion，提交 6840578)，协议最初由
SAxense (https://github.com/egormanga/SAxense) 逆向得出。

以下许可声明适用于取自 DualSense Companion 的部分：

MIT License

Copyright (c) 2026 vingt-2

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import ctypes
import struct
import time
import zlib
from ctypes import wintypes as W

import numpy as np

DECIMATE = 16         # 48000 -> 3000 Hz
FRAMES = 32           # 每个报告 32 帧；更小时手柄会周期性抖动
BLOCK = DECIMATE * FRAMES  # 每个报告对应 512 个 48 kHz 采样（10.7 ms）
OVERRIDE_PEAK = 8     # 音频震动弱于 8/127 时让位给游戏的普通震动，否则会削弱它
OVERRIDE_HOLD = 9     # 够强之后再保持约 0.1 秒，免得低频波形过零时断续
DEPTH = 0x20          # 手柄端缓冲，约 39 ms
SILENT_TAIL = 23      # 声音停止后再发约 0.25 秒静音，否则最后一下会一直震

_hid = ctypes.WinDLL("hid")
_cfg = ctypes.WinDLL("cfgmgr32")
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", W.BYTE * 8)]


class CAPS(ctypes.Structure):
    _fields_ = [("usage", W.WORD), ("page", W.WORD), ("input", W.WORD), ("output", W.WORD),
                ("feature", W.WORD), ("rest", W.WORD * 27)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("internal", ctypes.c_size_t), ("internal_high", ctypes.c_size_t),
                ("offset", W.DWORD), ("offset_high", W.DWORD), ("event", W.HANDLE)]


def _declare(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype, f.argtypes = restype, argtypes


_declare(_hid, "HidD_GetHidGuid", None, ctypes.POINTER(GUID))
_declare(_hid, "HidD_GetPreparsedData", W.BOOLEAN, W.HANDLE, ctypes.POINTER(W.LPVOID))
_declare(_hid, "HidD_FreePreparsedData", W.BOOLEAN, W.LPVOID)
_declare(_hid, "HidP_GetCaps", W.LONG, W.LPVOID, ctypes.POINTER(CAPS))
_declare(_hid, "HidD_GetFeature", W.BOOLEAN, W.HANDLE, W.LPVOID, W.ULONG)
_declare(_cfg, "CM_Get_Device_Interface_List_SizeW", W.ULONG, ctypes.POINTER(W.ULONG),
         ctypes.POINTER(GUID), W.LPCWSTR, W.ULONG)
_declare(_cfg, "CM_Get_Device_Interface_ListW", W.ULONG, ctypes.POINTER(GUID), W.LPCWSTR,
         W.LPWSTR, W.ULONG, W.ULONG)
_declare(_k32, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD,
         W.HANDLE)
_declare(_k32, "CreateEventW", W.HANDLE, W.LPVOID, W.BOOL, W.BOOL, W.LPCWSTR)
_declare(_k32, "WriteFile", W.BOOL, W.HANDLE, W.LPVOID, W.DWORD, W.LPVOID,
         ctypes.POINTER(OVERLAPPED))
_declare(_k32, "WaitForSingleObject", W.DWORD, W.HANDLE, W.DWORD)
_declare(_k32, "CancelIoEx", W.BOOL, W.HANDLE, ctypes.POINTER(OVERLAPPED))
_declare(_k32, "GetOverlappedResult", W.BOOL, W.HANDLE, ctypes.POINTER(OVERLAPPED),
         ctypes.POINTER(W.DWORD), W.BOOL)
_declare(_k32, "CloseHandle", W.BOOL, W.HANDLE)


def find():
    """返回蓝牙 DualSense 的 HID 路径，没有时返回 None。"""
    guid, size = GUID(), W.ULONG()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    if _cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(guid), None, 0):
        return None
    buf = ctypes.create_unicode_buffer(size.value)
    if _cfg.CM_Get_Device_Interface_ListW(ctypes.byref(guid), None, buf, size.value, 0):
        return None
    for path in buf[:].split("\0"):
        low = path.lower()
        if "{00001124-" in low and "054c_pid&0ce6" in low:
            return path
    return None


def _seal(body):
    return bytes(body) + struct.pack("<I", zlib.crc32(b"\xa2" + body))


def haptics_report(samples, counter):
    """只有震动数据（0x32）：用来发静音，不干扰游戏自己的普通震动。"""
    body = bytearray(142 - 4)
    body[0] = 0x32
    body[1] = (counter & 0x0F) << 4
    body[2:11] = bytes((0x91, 7, 0xFE, 0, 0, 0, 0, DEPTH, counter & 0xFF))
    body[11:13] = bytes((0x92, len(samples)))
    body[13:13 + len(samples)] = samples
    return _seal(body)


def override_report(samples, counter):
    """震动数据 + 一个所有标志为 0 的效果块，放在同一个报告里（0x33）。

    Steam Input 和游戏会持续发普通震动指令（强度为 0 也算），手柄一收到就忽略音频震动。
    分开发恢复报告会被它们插队：每秒恢复一次时只剩约 5% 的强度。放进同一个报告后，
    每一包震动都自带恢复。标志全为 0，所以不改变扳机效果和灯光。
    """
    body = bytearray(206 - 4)
    body[0] = 0x33
    body[1] = (counter & 0x0F) << 4
    body[2:11] = bytes((0x91, 7, 0xFE, 0, 0, 0, 0, DEPTH, counter & 0xFF))
    body[11:13] = bytes((0x90, 63))  # 效果块：63 个 0
    body[76:78] = bytes((0x92, len(samples)))
    body[78:78 + len(samples)] = samples
    return _seal(body)


def to_packet(haptic):
    """48 kHz 双声道 float（BLOCK 帧）-> 3 kHz int8 交错。"""
    v = haptic.reshape(FRAMES, DECIMATE, 2).mean(axis=1) * 127
    out = (np.sign(v) * np.floor(np.abs(v) + 0.5)).clip(-128, 127).astype(np.int8)
    if np.abs(out.astype(np.int16)).max() <= 1:
        out[:] = 0
    return out.tobytes()


class Controller:
    def __init__(self, path):
        h = _k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0x40000000, None)
        if h == W.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle, self.event = h, _k32.CreateEventW(None, True, False, None)
        self.counter, self.last, self.silent = 0, 0.0, SILENT_TAIL
        self.hold = 0
        self.gate = OVERRIDE_PEAK
        try:
            pre, caps = W.LPVOID(), CAPS()
            if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pre)):
                raise OSError("读不到手柄信息")
            _hid.HidP_GetCaps(pre, ctypes.byref(caps))
            _hid.HidD_FreePreparsedData(pre)
            self.input_size, self.output_size = caps.input, caps.output
            # 读一次校准数据会切到完整蓝牙模式；手柄已关机但仍被系统列出时，这里会失败
            buf = ctypes.create_string_buffer(b"\x05", caps.feature)
            if not _hid.HidD_GetFeature(h, buf, caps.feature):
                raise OSError("手柄未响应")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.handle:
            _k32.CloseHandle(self.handle)
            _k32.CloseHandle(self.event)
            self.handle = None

    def write(self, report):
        # Windows 要求缓冲区等于最长报告的长度，实际只发送该报告声明的长度
        buf = ctypes.create_string_buffer(report, max(len(report), self.output_size))
        ov, done = OVERLAPPED(event=self.event), W.DWORD()
        if _k32.WriteFile(self.handle, buf, len(buf), None, ctypes.byref(ov)):
            return
        err = ctypes.get_last_error()
        if err != 997:  # ERROR_IO_PENDING
            raise ctypes.WinError(err)
        timed_out = _k32.WaitForSingleObject(self.event, 500) != 0
        if timed_out:
            _k32.CancelIoEx(self.handle, ctypes.byref(ov))
        # 必须等系统用完 buf 和 ov 才能返回
        ok = _k32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(done), True)
        if timed_out or not ok:
            raise OSError("手柄蓝牙发送失败")

    def send(self, samples):
        """发送一包震动；持续静音时不占用蓝牙带宽。"""
        audible = any(samples)
        if audible:
            self.silent = 0
            if np.abs(np.frombuffer(samples, np.int8).astype(np.int16)).max() >= self.gate:
                self.hold = OVERRIDE_HOLD
            elif self.hold:
                self.hold -= 1
        elif self.silent >= SILENT_TAIL:
            return
        else:
            self.silent += 1
        now = time.perf_counter()
        if now - self.last > 0.05:  # 每段新震动从 0 计数，否则会被拉长
            self.counter = 0
        self.last = now
        if not audible:
            self.hold = 0
        build = override_report if self.hold else haptics_report
        self.write(build(samples, self.counter))
        self.counter = (self.counter + 1) & 0xFF

    def stop(self):
        for _ in range(4):
            self.write(haptics_report(bytes(FRAMES * 2), self.counter))
            self.counter = (self.counter + 1) & 0xFF
            time.sleep(0.01)
