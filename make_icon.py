# GIF ループツールのアイコンを作る（ステップ21）
# 緑の角丸の四角に「GIF」の文字、そのまわりを2本の矢印がぐるっと回る形（＝くり返し再生）
#
# 必要なもの：Pillow（画像を作る部品。入れ方：python -m pip install pillow）
# 使い方：python make_icon.py
#   → icon.ico（exe と画面に付けるアイコン）と images/icon.png（README 用）ができる

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SIZE = 512                 # 大きく描いてから縮めると、ふちがなめらかになる
GREEN = "#059669"
FONT = "C:/Windows/Fonts/segoeuib.ttf"  # Windows に入っている太い文字
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def arrow_arc(draw, box, start, end, width):
    """box の円に沿って start 度から end 度まで線を引き、end 側に矢じりを付ける（時計回り）"""
    draw.arc(box, start, end, fill="white", width=width)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    r = (box[2] - box[0]) / 2 - width / 2
    a = math.radians(end)
    px, py = cx + r * math.cos(a), cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)   # 進む向き
    nx, ny = math.cos(a), math.sin(a)    # 外向き
    length, half = width * 1.7, width * 1.4
    draw.polygon([(px + tx * length, py + ty * length),
                  (px + nx * half, py + ny * half),
                  (px - nx * half, py - ny * half)], fill="white")


def draw_icon():
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=96, fill=GREEN)
    ring = (70, 70, SIZE - 70, SIZE - 70)
    arrow_arc(draw, ring, 200, 330, 36)   # 上の矢印
    arrow_arc(draw, ring, 20, 150, 36)    # 下の矢印
    font = ImageFont.truetype(FONT, 150)
    box = draw.textbbox((0, 0), "GIF", font=font)
    draw.text((SIZE / 2 - (box[0] + box[2]) / 2, SIZE / 2 - (box[1] + box[3]) / 2), "GIF", font=font, fill="white")
    return image


def draw_small_icon(size):
    """16・24 ピクセル用の簡単な形。矢印まで入れると「GIF」の文字がつぶれて読めないので、文字だけを大きく描く"""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, SIZE, SIZE), radius=80, fill=GREEN)
    font = ImageFont.truetype(FONT, 250)
    box = draw.textbbox((0, 0), "GIF", font=font)
    draw.text((SIZE / 2 - (box[0] + box[2]) / 2, SIZE / 2 - (box[1] + box[3]) / 2), "GIF", font=font, fill="white")
    return image.resize((size, size), Image.LANCZOS)


def main():
    icon = draw_icon()
    # 1つのファイルに、いろいろな大きさを入れておく。小さい2つだけは、文字だけの形にする
    icon.save(HERE / "icon.ico", sizes=ICO_SIZES, append_images=[draw_small_icon(16), draw_small_icon(24)])
    (HERE / "images").mkdir(exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(HERE / "images" / "icon.png")
    print("icon.ico と images/icon.png を作りました")


if __name__ == "__main__":
    main()
