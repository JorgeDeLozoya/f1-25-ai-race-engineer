"""Generador de capturas de promocion oficiales con HUD F1 TV en ingles."""
from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
LOGOS_DIR = ROOT / "engineer" / "assets" / "logos"
DESKTOP_DIR = Path(r"D:\Escritorio")


def blend_color(c1: tuple[int, int, int], c2: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * alpha),
        int(c1[1] + (c2[1] - c1[1]) * alpha),
        int(c1[2] + (c2[2] - c1[2]) * alpha),
    )


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def draw_f1_radio_hud(
    driver_name: str,
    car_number: str,
    team_color_hex: str,
    badge_file: str,
    driver_query: str,
    engineer_reply: str,
    width: int = 420,
) -> Image.Image:
    # Fuentes del sistema
    try:
        font_f1 = ImageFont.truetype("seguisb.ttf", 15)
        font_team_radio = ImageFont.truetype("segoeui.ttf", 9)
        font_num = ImageFont.truetype("seguisb.ttf", 32)
        font_drv = ImageFont.truetype("seguisb.ttf", 22)
        font_radio = ImageFont.truetype("seguisb.ttf", 21)
        font_msg = ImageFont.truetype("segoeuii.ttf", 13)
        font_eng = ImageFont.truetype("segoeuib.ttf", 13)
    except Exception:
        font_f1 = ImageFont.load_default()
        font_team_radio = font_f1
        font_num = font_f1
        font_drv = font_f1
        font_radio = font_f1
        font_msg = font_f1
        font_eng = font_f1

    bg_header = hex_to_rgb("#0D0F14")
    bg_body = hex_to_rgb("#151821")
    team_rgb = hex_to_rgb(team_color_hex)
    border_rgb = hex_to_rgb("#2A3042")

    # Word wrap del texto del ingeniero
    max_text_width = width - 36
    dummy_img = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    def wrap_text(text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
        words = text.split()
        lines = []
        cur = []
        for w in words:
            test_line = " ".join(cur + [w])
            bbox = dummy_draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_w:
                cur.append(w)
            else:
                if cur:
                    lines.append(" ".join(cur))
                    cur = [w]
                else:
                    lines.append(w)
        if cur:
            lines.append(" ".join(cur))
        return lines

    eng_lines = wrap_text(f'"{engineer_reply}"', font_eng, max_text_width)
    drv_lines = wrap_text(f'"{driver_query}"', font_msg, max_text_width) if driver_query else []

    header_h = 118
    body_h = 16 + (len(drv_lines) * 20 + 8 if drv_lines else 0) + len(eng_lines) * 20 + 16
    total_h = header_h + body_h

    card = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # Fondo general con borde
    draw.rounded_rectangle([0, 0, width - 1, total_h - 1], radius=8, fill=(*bg_body, 240), outline=(*border_rgb, 255), width=2)
    # Fondo cabecera
    draw.rounded_rectangle([1, 1, width - 2, header_h], radius=7, fill=(*bg_header, 255))

    # Franjas escalonadas de escudería detrás del número
    c_dark = blend_color(bg_header, team_rgb, 0.26)
    c_mid = blend_color(bg_header, team_rgb, 0.16)
    c_light = blend_color(bg_header, team_rgb, 0.08)

    draw.rectangle([1, 52, 170, 78], fill=(*c_dark, 255))
    draw.rectangle([1, 62, 240, 78], fill=(*c_mid, 255))
    draw.rectangle([1, 70, width - 2, 78], fill=(*c_light, 255))

    # F1 TEAM RADIO
    draw.text((16, 14), "F1", fill=(190, 196, 208, 255), font=font_f1)
    draw.text((44, 18), "TEAM RADIO", fill=(120, 130, 148, 255), font=font_team_radio)

    # Car Number
    draw.text((16, 36), str(car_number), fill=(*team_rgb, 255), font=font_num)

    # Driver Name
    bbox_drv = draw.textbbox((0, 0), driver_name, font=font_drv)
    drv_w = bbox_drv[2] - bbox_drv[0]
    draw.text((width - 16 - drv_w, 8), driver_name, fill=(*team_rgb, 255), font=font_drv)

    # "RADIO" + Logo
    bbox_rad = draw.textbbox((0, 0), "RADIO", font=font_radio)
    rad_w = bbox_rad[2] - bbox_rad[0]
    rx = width - 16 - rad_w
    draw.text((rx, 38), "RADIO", fill=(255, 255, 255, 255), font=font_radio)

    # Pegar logo
    logo_path = LOGOS_DIR / badge_file
    if logo_path.exists():
        try:
            with Image.open(logo_path) as logo:
                ratio = min(46.0 / max(1, logo.width), 26.0 / max(1, logo.height))
                nw, nh = max(1, int(logo.width * ratio)), max(1, int(logo.height * ratio))
                resized = logo.resize((nw, nh), Image.Resampling.LANCZOS).convert("RGBA")
                card.paste(resized, (rx - nw - 10, 48 - nh // 2), resized)
        except Exception:
            pass

    # Ecualizador de ondas (36 barras)
    n_bars = 36
    pad_x = 14
    usable_w = width - 2 * pad_x
    step = usable_w / n_bars
    bar_w = max(4.0, step - 3.0)
    base_y = header_h - 6

    for i in range(n_bars):
        bx = pad_x + i * step
        center_weight = 0.40 + 0.60 * math.sin(math.pi * (i + 0.5) / n_bars)
        wave = 0.35 + 0.65 * abs(math.sin(1.2 + i * 0.42))
        bh = max(4.0, wave * center_weight * 26.0)
        draw.rounded_rectangle([bx, base_y - bh, bx + bar_w, base_y], radius=2, fill=(*team_rgb, 240))

    # Cuerpo de texto
    cy = header_h + 12
    if drv_lines:
        for line in drv_lines:
            bbox_line = draw.textbbox((0, 0), line, font=font_msg)
            lw = bbox_line[2] - bbox_line[0]
            draw.text((width - 18 - lw, cy), line, fill=(*team_rgb, 255), font=font_msg)
            cy += 20
        cy += 6

    for line in eng_lines:
        draw.text((18, cy), line, fill=(255, 255, 255, 255), font=font_eng)
        cy += 20

    return card
