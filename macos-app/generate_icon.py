#!/usr/bin/env python3
"""Generate a high-resolution native macOS AppIcon.icns for LiteParse Studio."""

import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def create_icon_image(size: int = 1024) -> Image.Image:
    # 1024x1024 base canvas with transparency
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    scale = size / 1024.0

    # Apple squircle bounds: 824x824 centered inside 1024x1024
    pad = int(100 * scale)
    card_w = size - 2 * pad
    radius = int(185 * scale)

    # 1. Outer ambient shadow
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [pad + int(8 * scale), pad + int(16 * scale), pad + card_w - int(8 * scale), pad + card_w + int(24 * scale)],
        radius=radius,
        fill=(0, 0, 0, 110)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(28 * scale)))
    img = Image.alpha_composite(shadow, img)

    # 2. Main Squircle Card Background (Liquid Deep Navy/Cobalt Gradient)
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(card)

    for y in range(card_w):
        ratio = y / card_w
        r = int(10 + ratio * 12)
        g = int(22 + ratio * 32)
        b = int(45 + ratio * 85)
        color = (r, g, b, 255)
        c_draw.line(
            [(pad, pad + y), (pad + card_w, pad + y)],
            fill=color,
            width=1
        )

    # Squircle mask
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([pad, pad, pad + card_w, pad + card_w], radius=radius, fill=255)

    card.putalpha(mask)
    img = Image.alpha_composite(img, card)

    # 3. Inner Glass Refraction & Rim Light
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r_draw = ImageDraw.Draw(rim)
    # Bright top-left rim highlight
    r_draw.rounded_rectangle(
        [pad + 1, pad + 1, pad + card_w - 1, pad + card_w - 1],
        radius=radius,
        outline=(255, 255, 255, 60),
        width=int(3 * scale)
    )
    # Top highlight curve
    r_draw.arc(
        [pad + int(20 * scale), pad + int(15 * scale), pad + card_w - int(20 * scale), pad + int(180 * scale)],
        start=190,
        end=350,
        fill=(255, 255, 255, 35),
        width=int(2 * scale)
    )
    img = Image.alpha_composite(img, rim)

    # 4. Central Motif: Floating Translucent Liquid Glass Document with Dual Prismatic Beams
    fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    f_draw = ImageDraw.Draw(fg)

    # Floating Document Plate
    doc_w = int(420 * scale)
    doc_h = int(520 * scale)
    doc_x = (size - doc_w) // 2
    doc_y = (size - doc_h) // 2 - int(10 * scale)
    doc_radius = int(36 * scale)

    # Document Glass Fill
    f_draw.rounded_rectangle(
        [doc_x, doc_y, doc_x + doc_w, doc_y + doc_h],
        radius=doc_radius,
        fill=(255, 255, 255, 22),
        outline=(140, 210, 255, 120),
        width=int(3 * scale)
    )

    # Folded corner in top-right of document
    fold_size = int(80 * scale)
    f_draw.polygon(
        [
            (doc_x + doc_w - fold_size, doc_y),
            (doc_x + doc_w, doc_y + fold_size),
            (doc_x + doc_w - fold_size, doc_y + fold_size)
        ],
        fill=(80, 160, 255, 140)
    )

    # Prismatic Dual-Track Beams (Laser Cyan & Emerald)
    # Track 1: Cyan Vector Beam
    cx, cy = size // 2, size // 2
    f_draw.line(
        [(doc_x + int(60 * scale), cy - int(60 * scale)), (doc_x + doc_w - int(60 * scale), cy - int(60 * scale))],
        fill=(56, 189, 248, 220),
        width=int(12 * scale)
    )
    # Track 2: Emerald Scan Beam
    f_draw.line(
        [(doc_x + int(60 * scale), cy + int(10 * scale)), (doc_x + doc_w - int(120 * scale), cy + int(10 * scale))],
        fill=(52, 211, 153, 220),
        width=int(12 * scale)
    )
    # Track 3: Indigo Publication Beam
    f_draw.line(
        [(doc_x + int(60 * scale), cy + int(80 * scale)), (doc_x + doc_w - int(80 * scale), cy + int(80 * scale))],
        fill=(168, 85, 247, 220),
        width=int(12 * scale)
    )

    # Sparkle Accent (Center-right)
    sparkle_x = doc_x + doc_w - int(55 * scale)
    sparkle_y = cy - int(60 * scale)
    sp_r = int(18 * scale)
    f_draw.ellipse(
        [sparkle_x - sp_r, sparkle_y - sp_r, sparkle_x + sp_r, sparkle_y + sp_r],
        fill=(255, 255, 255, 240)
    )

    img = Image.alpha_composite(img, fg)
    return img


def build_icns(output_icns_path: Path):
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

    for filename, s in sizes:
        resized = base_img.resize((s, s), Image.Resampling.LANCZOS)
        resized.save(iconset_dir / filename, "PNG")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns_path)],
        check=True
    )
    # Clean up iconset folder
    for f in iconset_dir.iterdir():
        f.unlink()
    iconset_dir.rmdir()
    print(f"✅ 生成高分辨率 macOS 图标成功: {output_icns_path}")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "AppIcon.icns"
    build_icns(out)
