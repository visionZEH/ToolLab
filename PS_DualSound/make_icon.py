"""生成 PS_DualSound 像素图标（需要 Pillow）-> ps_dualsound.ico / ps_dualsound.png"""
from pathlib import Path
from PIL import Image

PIXELS = [
    "................",
    "....DDDDDDDD....",
    "...D........D...",
    ".....DDDDDD.....",
    "....D......D....",
    ".......DD.......",
    "................",
    "..GGGGGGGGGGGG..",
    ".GKKKKKKKKKKKKG.",
    ".GKgKKKKKKKgKKG.",
    ".GgggKgKKgKgKgG.",
    ".GKgKKKKKKKKgKG.",
    ".GKKKGGGGGGKKKG.",
    ".GKKG......GKKG.",
    "..GG........GG..",
    "................",
]
COLORS = {
    ".": (0, 0, 0, 0),           # 透明
    "D": (24, 52, 150, 255),     # 深蓝声波
    "K": (12, 12, 16, 255),      # 黑色手柄
    "G": (52, 54, 64, 255),      # 深灰轮廓（让黑手柄在深色桌面上也看得见）
    "g": (92, 94, 108, 255),     # 灰色按键
}

base = Image.new("RGBA", (16, 16))
base.putdata([COLORS[c] for row in PIXELS for c in row])

here = Path(__file__).parent
sizes = [256, 128, 64, 48, 32, 16]
frames = [base.resize((s, s), Image.NEAREST) for s in sizes]
frames[0].save(here / "ps_dualsound.png")
frames[0].save(here / "ps_dualsound.ico", format="ICO",
               sizes=[(s, s) for s in sizes], append_images=frames[1:])
print("ok")
