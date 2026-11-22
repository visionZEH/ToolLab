"""
PS_DualSound（音频引擎 + 命令行版）

日常使用请运行托盘版 ps_dualsound_tray.pyw；本文件也可以单独在命令行里用。

有线：DualSense 通过 USB 连接时是一个 4 声道声卡：
    声道 1/2 -> 手柄耳机孔
    声道 3/4 -> 左/右 音频震动马达 (haptics)

有线用法：Windows 默认输出设为 DualSense，然后：
  1. 选择声音输出设备（音箱）
  2. 选择震动强度
       0 原生     只保留游戏原生震动（细腻）
       1 仿原生   叠加一层很轻的低频震动；蓝牙下用来模拟有线的原生震感
       2~5 增强   在原生震动之上，再叠加由游戏声音低频生成的震动（更猛）
  游戏声音（声道1/2）实时转发到音箱；增强震动只写声道 3/4，不会形成回环。

蓝牙：不用改默认输出。录下 Windows 默认输出正在播放的声音，把低频作为震动直接发给手柄。
      游戏原生的 3/4 声道震动只有有线时才有。

命令行：
    python ps_dualsound.py --out Realtek --level 3
    python ps_dualsound.py --list
按 Ctrl+C 退出。
"""
import argparse
import ctypes
import json
import math
import os
import re
import sys
import time
import warnings
from pathlib import Path

# numpy 默认按 CPU 核心数预留线程和缓冲区（20 核约 1.3 GB 提交内存）。
# 本脚本用不到多核线性代数，限制为单线程。必须放在 import numpy 之前。
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np
import soundcard as sc

import dualsense_bt as bt

warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)


def _device_id_without_leak(self, device_ptr):
    """修正 soundcard：IMMDevice::GetId 返回的字符串必须用 CoTaskMemFree 释放。

    原版不释放，托盘程序每 3 秒找一次手柄，一天会泄漏十几 MB。
    """
    mf = sc.mediafoundation
    pp_id = mf._ffi.new("LPWSTR *")
    mf._com.check_error(device_ptr[0][0].lpVtbl.GetId(device_ptr[0], pp_id))
    try:
        return mf._ffi.string(pp_id[0])
    finally:
        mf._ole32.CoTaskMemFree(pp_id[0])


sc.mediafoundation._DeviceEnumerator._device_id = _device_id_without_leak

RATE = 48000
BLOCK = 480  # 10 ms
SETTINGS = Path(__file__).with_name("settings.json")

# 强度档位: (名称, 强度倍数, 增强指数, 低通截止 Hz)
LEVELS = [
    ("原生（不增强）", 0, 1.0, 0),
    ("仿原生（细腻）", 0.8, 0.8, 150),
    ("轻微增强", 1.0, 0.8, 150),
    ("中度增强", 2.0, 0.6, 120),
    ("强", 3.0, 0.5, 100),
    ("超强", 5.0, 0.4, 90),
]

_names = {}
_channels = {}
_instance = None


def claim_single_instance():
    """托盘版和命令行版只能同时运行一个，否则声音和震动会叠加两次。"""
    global _instance
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    _instance = k32.CreateMutexW(None, False, "Local\\PSDualSound")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def load_settings():
    try:
        data = dict(json.loads(SETTINGS.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return {"version": 2}
    if "version" not in data:  # 旧版没有「仿原生」，原来的 1~4 档现在是 2~5 档
        if data.get("level") in (1, 2, 3, 4):
            data["level"] += 1
        data["version"] = 2
    return data


def save_settings(**changes):
    data = {**load_settings(), **changes}
    try:
        tmp = SETTINGS.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SETTINGS)
    except OSError:
        pass


def device_name(dev):
    # 缓存名字：soundcard 每次读取名字都会漏掉一小块内存，常驻时不能反复读。
    if dev.id not in _names:
        _names[dev.id] = dev.name
    return _names[dev.id]


def same_device(a, b):
    """忽略 Windows 重新识别时加上的序号，如 "(5- DualSense ...)"。"""
    def norm(s):
        return re.sub(r"\(\d+- ", "(", s or "")
    return norm(a) == norm(b)


def is_dualsense(dev):
    name = device_name(dev).lower()
    if "dualsense" in name:
        return True
    if "wireless controller" not in name:
        return False
    # DualShock 4、Xbox 手柄耳机也叫 Wireless Controller，但只有两个声道
    if dev.id not in _channels:
        try:
            _channels[dev.id] = dev.channels
        except (RuntimeError, AssertionError):
            return False
    return _channels[dev.id] >= 4


def list_devices():
    """返回 (手柄或 None, 其他输出设备列表)。"""
    ds, outs = None, []
    for s in sc.all_speakers():
        if is_dualsense(s):
            ds = ds or s
        else:
            outs.append(s)
    return ds, outs


class LowPass:
    """四阶 Butterworth 低通，按块计算，只依赖 numpy。

    先逐点模拟一次单位响应，之后每块只做一次卷积和两次矩阵乘法，结果和逐点滤波一致。
    """

    def __init__(self, cutoff, channels=2, block=BLOCK):
        self.block = block
        w = 2 * math.pi * cutoff / RATE
        sections = []
        for q in (1 / (2 * math.cos(math.pi / 8)), 1 / (2 * math.cos(3 * math.pi / 8))):
            alpha, c, a0 = math.sin(w) / (2 * q), math.cos(w), 1 + math.sin(w) / (2 * q)
            b = (1 - c) / 2 / a0
            sections.append((b, 2 * b, b, -2 * c / a0, (1 - alpha) / a0))

        def simulate(state, impulse):
            s, out, track = list(state), [], []
            for n in range(block):
                x = impulse if n == 0 else 0.0
                for i, (b0, b1, b2, a1, a2) in enumerate(sections):
                    y = b0 * x + s[2 * i]
                    s[2 * i] = b1 * x - a1 * y + s[2 * i + 1]
                    s[2 * i + 1] = b2 * x - a2 * y
                    x = y
                out.append(x)
                track.append(list(s))
            return np.array(out), np.array(track).T

        self.h, track = simulate([0.0] * 4, 1.0)
        self.input_to_state = track[:, ::-1]
        basis = [simulate(row, 0.0) for row in np.eye(4).tolist()]
        self.state_to_out = np.column_stack([out for out, _ in basis])
        self.state_to_state = np.column_stack([tr[:, -1] for _, tr in basis])
        self.state = np.zeros((4, channels))

    def __call__(self, x):
        y = self.state_to_out @ self.state
        for ch in range(x.shape[1]):
            y[:, ch] += np.convolve(x[:, ch], self.h)[:self.block]
        self.state = self.state_to_state @ self.state + self.input_to_state @ x.astype(np.float64)
        self.state[np.abs(self.state) < 1e-20] = 0.0  # 静音时避免极小数拖慢 CPU
        return y


def shape_haptic(x, strength, curve):
    """先按指数曲线放大弱信号（curve<1），再乘强度倍数。"""
    if curve != 1.0:
        x = np.sign(x) * np.abs(x) ** curve
    return np.clip(x * strength, -1, 1)


def run(ds, out, level, gain, stop=lambda: False, started=lambda: None):
    """一直转发，直到 stop() 为真；设备断开时抛出异常，由调用方重连。"""
    _, strength, curve, cutoff = LEVELS[level]
    lowpass = LowPass(cutoff) if strength else None
    mic = sc.get_microphone(ds.id, include_loopback=True)
    with mic.recorder(samplerate=RATE, channels=4, blocksize=BLOCK) as rec, \
         out.player(samplerate=RATE, channels=2, blocksize=BLOCK) as ply:
        if not lowpass:
            started()
            while not stop():
                data = rec.record(numframes=BLOCK)
                ply.play(np.clip(data[:, :2] * gain, -1, 1))
            return

        buf = np.zeros((BLOCK, 4), dtype=np.float32)
        with ds.player(samplerate=RATE, channels=4, blocksize=BLOCK) as hap:
            started()
            while not stop():
                game = rec.record(numframes=BLOCK)[:, :2]
                ply.play(np.clip(game * gain, -1, 1))
                buf[:, 2:] = shape_haptic(lowpass(game), strength, curve)  # 只写震动声道
                hap.play(buf)


def run_bluetooth(path, level, stop=lambda: False, started=lambda name: None):
    """把默认输出里的低频发给蓝牙手柄；默认输出变了或插上了 USB 时返回，由调用方重新选择。"""
    _, strength, curve, cutoff = LEVELS[level]
    src = sc.default_speaker()
    lowpass = LowPass(cutoff, block=bt.BLOCK)
    mic = sc.get_microphone(src.id, include_loopback=True)
    with bt.Controller(path) as pad, \
         mic.recorder(samplerate=RATE, channels=2, blocksize=BLOCK) as rec:
        pad.gate = round(bt.OVERRIDE_PEAK * min(strength, 1))  # 震动调轻时门槛同比降低，否则轻的声音会消失
        started(device_name(src))
        pending = np.zeros((0, 2), dtype=np.float32)
        heard = checked = time.perf_counter()
        try:
            while not stop():
                now = time.perf_counter()
                if now - checked >= 2:
                    checked = now
                    if sc.default_speaker().id != src.id or bt.find() != path or list_devices()[0]:
                        return
                # 没声音时 record() 会每 0.75 ms 轮询一次，所以先自己查一下有没有数据
                if rec._capture_available_frames():
                    pending = np.concatenate((pending, rec.record(numframes=None)))
                    heard = now
                    if len(pending) > bt.BLOCK * 8:  # 系统卡顿后丢掉积压，避免延迟越来越大
                        pending = pending[-bt.BLOCK * 2:]
                    while len(pending) >= bt.BLOCK:
                        game, pending = pending[:bt.BLOCK], pending[bt.BLOCK:]
                        haptic = shape_haptic(lowpass(game), strength, curve)
                        if np.abs(game).max() < 1e-4:  # 别把声卡底噪放大成震动
                            haptic[:] = 0
                        pad.send(bt.to_packet(haptic))
                elif now - heard < 0.05:
                    time.sleep(0.003)
                elif pad.silent < bt.SILENT_TAIL:  # 声音停了：补一小段静音让马达停下
                    pending = pending[:0]
                    lowpass.state[:] = 0
                    pad.send(bytes(bt.FRAMES * 2))
                    time.sleep(bt.BLOCK / RATE)
                else:
                    time.sleep(0.01)
        finally:
            try:
                if pad.silent < bt.SILENT_TAIL:
                    pad.stop()
            except OSError:  # 手柄已经断开
                pass


def ask(prompt, n, last):
    hint = f"（回车 = 上次的 {last}）" if last is not None and 0 <= last < n else ""
    while True:
        raw = input(f"{prompt}{hint}: ").strip()
        if raw == "" and hint:
            return last
        if raw.isdigit() and 0 <= int(raw) < n:
            return int(raw)
        print("无效编号，再试一次。")


def main():
    p = argparse.ArgumentParser(description="PS_DualSound")
    p.add_argument("--out", help="有线时的声音输出设备（名字关键字），不填则弹出菜单")
    p.add_argument("--level", type=int, choices=range(len(LEVELS)),
                   help="震动强度 0~5，不填则弹出菜单")
    p.add_argument("--gain", type=float, default=1.0, help="音箱音量倍数（默认 1）")
    p.add_argument("--list", action="store_true", help="列出输出设备")
    a = p.parse_args()

    if a.list:
        default = sc.default_speaker().id
        for s in sc.all_speakers():
            print(("* " if s.id == default else "  ") + f"{device_name(s)}  ({s.channels}ch)")
        print("* = 当前 Windows 默认输出")
        return

    if not claim_single_instance():
        sys.exit("PS_DualSound 已经在运行，请先从右下角托盘图标退出。")

    try:
        ds, outs = list_devices()
        if not ds and not bt.find():
            sys.exit("没找到 DualSense，请用 USB 连接，或者先在 Windows 蓝牙里配对。")
        st = load_settings()
        out_name = st.get("out")
        if a.out:
            out = next((s for s in outs if a.out.lower() in device_name(s).lower()), None)
            if not out:
                sys.exit(f"没有找到名字包含 “{a.out}” 的输出设备，用 --list 查看。")
            out_name = device_name(out)
        elif ds:
            print("\n【1】选择声音输出设备：")
            for i, s in enumerate(outs):
                print(f"  [{i}] {device_name(s)}")
            last = next((i for i, s in enumerate(outs)
                         if same_device(device_name(s), out_name)), None)
            out_name = device_name(outs[ask("编号", len(outs), last)])
        level = a.level
        if level is None:
            print("\n选择震动强度：")
            for i, (name, *_) in enumerate(LEVELS):
                print(f"  [{i}] {name}")
            level = ask("编号", len(LEVELS), st.get("level"))

        save_settings(out=out_name, level=level)
        name, strength, *_ = LEVELS[level]
        if ds and sc.default_speaker().id != ds.id:
            print("\n⚠ 请在 Windows 声音设置里把默认输出设为 DualSense。")
        print(f"\n{name}。Ctrl+C 退出。")
        shown = None

        def show(text):
            nonlocal shown
            if text != shown:
                shown = text
                print(text)

        while True:
            try:
                ds, outs = list_devices()
                path = None if ds else bt.find()
                out = next((s for s in outs if same_device(device_name(s), out_name)), None)
                if ds and out:
                    run(ds, out, level, a.gain, started=lambda: show(f"有线 -> {out_name}"))
                    continue
                if path and strength:
                    run_bluetooth(path, level, started=lambda src: show(f"蓝牙 <- {src}"))
                    continue
                show("等待扬声器连接" if ds else
                     "蓝牙下没有原生震动，请选 1~5 档" if path else "等待手柄连接")
            except (RuntimeError, AssertionError, OSError) as e:  # 设备断开或重新识别
                show(f"设备断开（{e}），自动重连中……")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
