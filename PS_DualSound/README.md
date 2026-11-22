<img src="ps_dualsound.png" width="96" alt="PS_DualSound icon">

# PS_DualSound

**震动留在手柄，声音去你想要的音箱。**

*PS_DualSound keeps DualSense (USB) audio haptics on the controller while sending game audio to any
speaker, with optional audio-driven rumble boost. Windows tray app; the UI is currently in Chinese.*

## 解决什么问题

DualSense 有线连接 Windows 时是一个 4 声道声卡：1/2 声道是耳机孔，3/4 声道是震动马达。
很多情况下，想要游戏的音频震动就得把默认输出设成手柄，于是音箱就没声音了。
（有些游戏会自己找到手柄声卡。如果你的游戏在输出为音箱时也有原生震动，就不需要本工具。）

PS_DualSound 录下手柄声卡的输出，把 1/2 声道实时转发到你选的音箱，3/4 声道的原生震动保持原样。

## 功能

- 托盘线条图标，跟随系统深浅色和缩放
- 单击选择扬声器和震动强度，立即切换
- 五档震动：原生、轻度、中度、强、超强
- 手柄或音箱断开后自动重连
- 可选开机自启（默认关闭）

## 要求

- Windows 10 1903+ 或 Windows 11（只在 Windows 11 上测试过）
- Python 3.9+（只在 3.11 上测试过）
- DualSense，**USB 有线连接**

## 安装和使用

```
git clone https://github.com/visionZEH/ToolLab.git
cd ToolLab/PS_DualSound
python -m pip install -r requirements.txt
```

1. 双击 `start.bat`，右下角出现手柄图标。
2. 把 Windows 默认输出设为 DualSense。
3. 单击图标，选择扬声器和震动强度。

命令行版：

```
python ps_dualsound.py --list
python ps_dualsound.py --out Realtek --level 3
```

## 震动强度

| 档位 | 强度倍数 | 增强指数 | 低通 |
|---|--:|--:|--:|
| 0 原生（细腻） | 不叠加 | — | — |
| 1 轻度增强 | 1.0 | 0.8 | 150 Hz |
| 2 中度增强 | 2.0 | 0.6 | 120 Hz |
| 3 强 | 3.0 | 0.5 | 100 Hz |
| 4 超强 | 5.0 | 0.4 | 90 Hz |

增强是在原生震动之上，叠加一层由游戏声音低频生成的震动。它不会放大原生震动信号本身。

## 已知限制

- **不支持蓝牙连接的手柄**：此时 Windows 里没有这个 4 声道声卡。蓝牙音箱可以正常作为输出。
- 转发会带来少量音频延迟，蓝牙音箱还有自身延迟。
- 转发期间音频流保持打开，可能阻止电脑自动睡眠，可以在菜单里暂停。
- 作者已在真实 DualSense 上做过基本测试；档位切换和断线重连主要用虚拟声卡测试，尚未在真机上逐档或长时间验证。
- 删除文件夹或移动位置之前，请先在菜单里关闭「开机自启」。

## 同类项目

PS_DualSound 只做一件事，是一个轻量替代方案，原理并非首创。有其他需求时可以看看：

- [DS5Dongle](https://github.com/awalol/DS5Dongle)：用 Raspberry Pi Pico 2 W 做无线接收器，让手柄在电脑上显示为有线连接
- [DS5 Bridge](https://github.com/SundayMoments/DS5_Bridge)：同类无线方案，带 Windows 配置软件和音频转震动
- [DualSense Client](https://github.com/DualSenseClient/DualSenseClient)：综合手柄管理、虚拟手柄、音频转发

本项目没有使用上述项目的代码，也没有和它们一起测试过。

## 隐私

没有任何网络请求，不保存音频。设备名和选项只保存在本地的 `settings.json`，它不会被 Git 提交。

## 许可证

[MIT](../LICENSE)。依赖项 SoundCard 和 NumPy 使用 BSD 许可证，本仓库不包含它们的代码。

本项目与 Sony Interactive Entertainment 无关，未获其认可或赞助。
DualSense 和 PlayStation 是其各自权利人的商标，这里仅用于说明兼容性。
