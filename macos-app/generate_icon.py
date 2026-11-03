#!/usr/bin/env python3
"""Generate a high-resolution native macOS AppIcon.icns for LiteParse Studio.

设计：深墨蓝圆角底 + 轻斜的暖白纸页，右上角折起露出青色纸背，
页尾用一个青色光标收束文本，折角旁一颗小火花。目标是比“居中厚文档”
更轻、更像正在被解析的纸页，同时在 16px 下仍保留清楚的斜向轮廓。
"""

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


# 以 2048 绘制后下采样，保证 Retina / 小尺寸边缘干净。
_SUPERSAMPLE = 2048


def _sc(value: float, size: int = _SUPERSAMPLE) -> int:
    return int(round(value * size / 1024.0))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255
    )
    return mask


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    gradient = Image.new("RGB", (1, size))
    draw = ImageDraw.Draw(gradient)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.point(
            (0, y),
            fill=tuple(
                int(top[channel] + (bottom[channel] - top[channel]) * t)
                for channel in range(3)
            ),
        )
    return gradient.resize((size, size), Image.Resampling.BICUBIC)


def _background() -> Image.Image:
    pad = _sc(98)
    card = _SUPERSAMPLE - pad * 2
    radius = _sc(188)

    bg = _vertical_gradient(card, (39, 100, 131), (12, 42, 62)).convert("RGBA")

    # 左上冷光 + 右下青色回光，制造纸页被托起的空气感。
    top_glow = Image.new("RGBA", (card, card), (0, 0, 0, 0))
    ImageDraw.Draw(top_glow).ellipse(
        [-card * 0.35, -card * 0.45, card * 0.75, card * 0.55],
        fill=(134, 210, 220, 58),
    )
    bg = Image.alpha_composite(
        bg, top_glow.filter(ImageFilter.GaussianBlur(card * 0.18))
    )

    bottom_glow = Image.new("RGBA", (card, card), (0, 0, 0, 0))
    ImageDraw.Draw(bottom_glow).ellipse(
        [card * 0.35, card * 0.55, card * 1.25, card * 1.25],
        fill=(27, 132, 137, 55),
    )
    bg = Image.alpha_composite(
        bg, bottom_glow.filter(ImageFilter.GaussianBlur(card * 0.18))
    )

    bg.putalpha(_rounded_mask(card, radius))
    canvas = Image.new("RGBA", (_SUPERSAMPLE, _SUPERSAMPLE), (0, 0, 0, 0))
    canvas.alpha_composite(bg, (pad, pad))

    # 极细内缘高光，让图标在浅色 Dock 上仍有边界。
    rim = Image.new("RGBA", (_SUPERSAMPLE, _SUPERSAMPLE), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle(
        [pad, pad, pad + card - 1, pad + card - 1],
        radius=radius,
        outline=(255, 255, 255, 40),
        width=_sc(2),
    )
    return Image.alpha_composite(canvas, rim)


def _draw_star(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    fill: tuple,
    inner: float = 0.24,
) -> None:
    points = []
    for index in range(8):
        angle = -math.pi / 2 + index * math.pi / 4
        point_radius = radius if index % 2 == 0 else radius * inner
        points.append(
            (cx + math.cos(angle) * point_radius, cy + math.sin(angle) * point_radius)
        )
    draw.polygon(points, fill=fill)


def _page_layer() -> Image.Image:
    page_w, page_h = _sc(322), _sc(428)
    radius = _sc(26)
    fold = _sc(82)
    margin = _sc(40)
    page = Image.new(
        "RGBA", (page_w + margin * 2, page_h + margin * 2), (0, 0, 0, 0)
    )
    origin_x, origin_y = margin, margin

    # 1. 纸页主体：暖白，不做过厚的卡片圆角。
    body = Image.new("RGBA", (page_w, page_h), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle(
        [0, 0, page_w - 1, page_h - 1], radius=radius, fill=(252, 250, 243, 255)
    )

    # 2. 切掉右上角，给折页留出真实的缺口。
    cut_mask = Image.new("L", (page_w, page_h), 255)
    ImageDraw.Draw(cut_mask).polygon(
        [(page_w - fold, 0), (page_w, 0), (page_w, fold)], fill=0
    )
    body.putalpha(
        Image.composite(
            body.getchannel("A"), Image.new("L", (page_w, page_h), 0), cut_mask
        )
    )

    # 3. 纸页底部极轻的暖灰阴影，避免整张纸发平。
    shade = Image.new("RGBA", (page_w, page_h), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle(
        [0, page_h * 0.72, page_w, page_h], fill=(214, 204, 183, 22)
    )
    shade = shade.filter(ImageFilter.GaussianBlur(_sc(30)))
    shade.putalpha(
        Image.composite(
            shade.getchannel("A"),
            Image.new("L", (page_w, page_h), 0),
            body.getchannel("A"),
        )
    )
    body = Image.alpha_composite(body, shade)

    # 4. 折角露出青色纸背：一个向内折的三角形，沿切口加亮边与投影。
    flap = Image.new("RGBA", (page_w, page_h), (0, 0, 0, 0))
    flap_draw = ImageDraw.Draw(flap)
    flap_draw.polygon(
        [(page_w - fold, 0), (page_w, fold), (page_w - fold, fold)],
        fill=(34, 112, 121, 255),
    )
    flap_draw.line(
        [(page_w - fold, 0), (page_w, fold)],
        fill=(116, 214, 210, 180),
        width=_sc(4),
    )
    flap_draw.line(
        [(page_w - fold, fold), (page_w, fold)],
        fill=(10, 35, 43, 90),
        width=_sc(7),
    )
    body = Image.alpha_composite(body, flap)

    page.alpha_composite(body, (origin_x, origin_y))

    # 5. 三条细墨线 + 页尾青色光标；线比旧版更细，留白更多。
    text_x = origin_x + int(page_w * 0.17)
    text_y = origin_y + int(page_h * 0.35)
    widths = (0.60, 0.46, 0.27)
    line_height = _sc(9)
    line_gap = _sc(37)
    page_draw = ImageDraw.Draw(page)
    for index, width in enumerate(widths):
        y = text_y + index * line_gap
        page_draw.rounded_rectangle(
            [text_x, y, text_x + int(page_w * width), y + line_height],
            radius=line_height // 2,
            fill=(31, 95, 138, 245) if index < 2 else (88, 145, 162, 235),
        )

    cursor_y = text_y + 2 * line_gap + line_height // 2
    cursor_x = text_x + int(page_w * widths[-1]) + _sc(18)
    page_draw.rounded_rectangle(
        [cursor_x, cursor_y - _sc(8), cursor_x + _sc(16), cursor_y + _sc(8)],
        radius=_sc(3),
        fill=(42, 150, 151, 255),
    )

    # 6. 折角旁的小火花：外圈先做柔光，再叠四角星，避免像一颗硬点。
    star_x = origin_x + page_w - _sc(6)
    star_y = origin_y + _sc(18)
    star_glow = Image.new("RGBA", page.size, (0, 0, 0, 0))
    _draw_star(
        ImageDraw.Draw(star_glow),
        star_x,
        star_y,
        _sc(54),
        fill=(67, 190, 184, 80),
    )
    page = Image.alpha_composite(
        page, star_glow.filter(ImageFilter.GaussianBlur(_sc(16)))
    )
    _draw_star(
        ImageDraw.Draw(page), star_x, star_y, _sc(28), fill=(155, 240, 231, 255)
    )

    return page


def _compose_icon() -> Image.Image:
    canvas = _background()
    page = _page_layer()

    # 纸页投影跟着纸页一起旋转，避免出现“纸在飘、影子没动”的穿帮。
    alpha = page.getchannel("A").point(lambda value: int(value * 0.38))
    shadow_solid = Image.new("RGBA", page.size, (8, 24, 32, 255))
    shadow_solid.putalpha(alpha)
    shadow = shadow_solid.filter(ImageFilter.GaussianBlur(_sc(28)))

    pivot = (page.width // 2, page.height // 2)
    tilt = -8
    shadow = shadow.rotate(tilt, resample=Image.Resampling.BICUBIC, center=pivot)
    page = page.rotate(tilt, resample=Image.Resampling.BICUBIC, center=pivot)

    # 纸页中心略向左上偏，让右上折角和火花有呼吸空间。
    x = int(_SUPERSAMPLE / 2 - page.width / 2 - _sc(8))
    y = int(_SUPERSAMPLE / 2 - page.height / 2 - _sc(14))
    canvas.alpha_composite(shadow, (x + _sc(2), y + _sc(26)))
    canvas.alpha_composite(page, (x, y))
    return canvas


def create_icon_image(size: int = 1024) -> Image.Image:
    """Return the icon at the requested square size, with transparent corners."""
    icon = _compose_icon()
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def build_icns(output_icns_path: Path) -> None:
    iconset_dir = output_icns_path.parent / "AppIcon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    base_img = create_icon_image(1024)

    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    for filename, size in sizes:
        base_img.resize((size, size), Image.Resampling.LANCZOS).save(
            iconset_dir / filename, "PNG"
        )

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns_path)],
        check=True,
    )
    for file in iconset_dir.iterdir():
        file.unlink()
    iconset_dir.rmdir()
    print(f"✅ 生成高分辨率 macOS 图标成功: {output_icns_path}")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "AppIcon.icns"
    build_icns(out)
