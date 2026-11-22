# ToolLab

一个小工具库：每个文件夹都是一个独立项目，有自己的说明和依赖，可以单独使用。

*Some tools I developed just making my life easier. Each folder is an independent project.*

## 工具目录 Tools

| 项目 Project | 用途 Purpose | 平台 Platform |
|---|---|---|
| [PS_DualSound](PS_DualSound/) | DualSense 震动留在手柄，游戏声音分到任意音箱<br>*Keep DualSense haptics on the pad, send game audio to any speaker* | Windows |

## 结构 Structure

```text
ToolLab/
├── README.md        工具目录
├── LICENSE          所有项目共用的许可证
└── PS_DualSound/    一个项目一个文件夹
```

添加新工具时，在根目录新建一个文件夹，放入代码和它自己的 README，再到上面的目录里加一行。

## License

[MIT](LICENSE)
