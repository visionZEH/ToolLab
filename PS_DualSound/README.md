<img src="ps_dualsound.png" width="96" alt="PS_DualSound icon">

# PS_DualSound

**震动留在手柄，声音去你想要的音箱。**

*PS_DualSound keeps DualSense audio haptics on the controller while game audio plays on any speaker.
USB: native haptics plus optional boost. Bluetooth: audio-driven haptics, no driver or admin rights
(native game haptics still need USB). Windows tray app; the UI is currently in Chinese.*

## 解决什么问题

DualSense 有线连接 Windows 时是一个 4 声道声卡：1/2 声道是耳机孔，3/4 声道是震动马达。
很多情况下，想要游戏的音频震动就得把默认输出设成手柄，于是音箱就没声音了。
（有些游戏会自己找到手柄声卡。如果你的游戏在输出为音箱时也有原生震动，就不需要本工具。）

PS_DualSound 录下手柄声卡的输出，把 1/2 声道实时转发到你选的音箱，3/4 声道的原生震动保持原样。

## 有线和蓝牙

插着 USB 就用有线，否则自动用蓝牙，不需要手动切换。

| | USB 有线 | 蓝牙 |
|---|---|---|
| 游戏原生细腻震动（3/4 声道） | ✅ | ❌ |
| 仿原生 + 四档增强震动 | ✅ | ✅ |
| Windows 默认输出 | 设为 DualSense | 保持你的音箱或耳机 |
| 扬声器 | 在托盘菜单里选 | 跟随 Windows 默认输出 |
| 驱动、管理员权限 | 不需要 | 不需要 |

蓝牙时，程序录下默认输出正在播放的声音，取低频后用 HID 报告 `0x32` 发给手柄。它会对所有声音起反应，音乐和视频也会震。

## 功能

- 托盘线条图标，跟随系统深浅色和缩放
- 单击选择扬声器和震动强度，立即切换
- 六档震动：原生、仿原生、轻微、中度、强、超强
- 手柄或音箱断开后自动重连
- 可选开机自启（默认关闭）

## 要求

- Windows 10 1903+ 或 Windows 11（只在 Windows 11 上测试过）
- Python 3.9+（只在 3.11 上测试过）
- DualSense，USB 有线或蓝牙连接（不支持 DualSense Edge 的蓝牙模式）

## 安装和使用

```
git clone https://github.com/visionZEH/ToolLab.git
cd ToolLab/PS_DualSound
python -m pip install -r requirements.txt
```

1. 双击 `start.bat`，右下角出现手柄图标。
2. **有线**：把 Windows 默认输出设为 DualSense，单击图标选择扬声器和震动强度。
3. **蓝牙**：在 Windows 里配对手柄（按住 PS + Create），默认输出保持音箱，单击图标选 1~5 档（想接近有线手感选 1 仿原生）。

命令行版：

```
python ps_dualsound.py --list
python ps_dualsound.py --out Realtek --level 4
```

## 震动强度

| 档位 | 强度倍数 | 增强指数 | 低通 |
|---|--:|--:|--:|
| 0 原生（不增强）；蓝牙时为关闭增强 | 不叠加 | — | — |
| 1 仿原生（细腻） | 0.8 | 0.8 | 150 Hz |
| 2 轻微增强 | 1.0 | 0.8 | 150 Hz |
| 3 中度增强 | 2.0 | 0.6 | 120 Hz |
| 4 强 | 3.0 | 0.5 | 100 Hz |
| 5 超强 | 5.0 | 0.4 | 90 Hz |

「仿原生」比轻微增强轻 20%，是用游戏声音的低频近似有线手感，**不是游戏真正的原生震动信号**。
从旧版升级时，已保存的档位会自动对应到新编号，强度不变。

增强是在原生震动之上，叠加一层由游戏声音低频生成的震动。它不会放大原生震动信号本身。蓝牙时只有这一层震动。

## 已知限制

- **蓝牙下没有游戏原生震动**：此时 Windows 里没有那个 4 声道声卡，游戏不会输出这两个声道。
- **蓝牙增强和游戏普通震动同一时间只能有一个**：音频震动够强（≥ 8/127，仿原生档为 6/127）时由它接管，较弱时让位给游戏的普通震动。
  所以低音强的时候会盖掉游戏自己的震动；只想要游戏自己的普通震动时，请选 0 档。
- 约 30 Hz 以下的低频，手柄马达本身响应很弱。
- 蓝牙模式会让手柄进入完整报告模式，少数只支持 DirectInput 的老游戏可能认不出按键，关掉手柄重连即可恢复。
- 蓝牙模式只在一只 DualSense 和一块 Intel 蓝牙网卡上测试过，在一款游戏里短时间试用过，尚未长时间验证。「仿原生」档只做过离线测试，手感尚未真机验证。
- 同时连着多只蓝牙手柄时，只使用找到的第一只。
- 转发会带来少量音频延迟，蓝牙音箱还有自身延迟。
- 转发期间音频流保持打开，可能阻止电脑自动睡眠，可以在菜单里暂停。
- 作者已在真实 DualSense 上做过基本测试；档位切换和断线重连主要用虚拟声卡测试，尚未在真机上逐档或长时间验证。
- 删除文件夹或移动位置之前，请先在菜单里关闭「开机自启」。

## 同类项目

PS_DualSound 只做一件事，是一个轻量替代方案，原理并非首创。有其他需求时可以看看：

- [DS5Dongle](https://github.com/awalol/DS5Dongle)：用 Raspberry Pi Pico 2 W 做无线接收器，让手柄在电脑上显示为有线连接
- [DS5 Bridge](https://github.com/SundayMoments/DS5_Bridge)：同类无线方案，带 Windows 配置软件和音频转震动
- [DualSense Client](https://github.com/DualSenseClient/DualSenseClient)：综合手柄管理、虚拟手柄、音频转发

本项目没有使用上述三个项目的代码，也没有和它们一起测试过。

## 致谢和第三方代码

- [DualSense Companion](https://github.com/vingt-2/dualsense-companion)（MIT，Copyright (c) 2026 vingt-2）：
  `dualsense_bt.py` 的报告格式和调校值改写自它，完整许可声明在该文件开头。想在蓝牙下得到游戏原生震动，
  可以使用这个项目（需要安装驱动）。
- [SAxense](https://github.com/egormanga/SAxense)：最早逆向出 DualSense 蓝牙震动协议。

## 隐私

没有任何网络请求，不保存音频。设备名和选项只保存在本地的 `settings.json`，它不会被 Git 提交。

## 许可证

[MIT](../LICENSE)。依赖项 SoundCard 和 NumPy 使用 BSD 许可证，本仓库不包含它们的代码。`dualsense_bt.py` 另含上述 MIT 第三方声明。

本项目与 Sony Interactive Entertainment 无关，未获其认可或赞助。
DualSense 和 PlayStation 是其各自权利人的商标，这里仅用于说明兼容性。
