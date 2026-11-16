"""Genera capturas promocionales con el HUD de Radio F1 TV en ingles y las guarda en el Escritorio."""
from __future__ import annotations

from pathlib import Path
from PIL import Image
from make_promo_screenshots import draw_f1_radio_hud

DESKTOP_DIR = Path(r"D:\Escritorio")
BRAIN_DIR = Path(r"C:\Users\Jorge\.gemini\antigravity\brain\17759d81-ba4b-4147-a3d6-3106ea9e1770")

# 1. Captura 1: Red Bull / Max Verstappen - "HOW ARE MY TYRES?" -> "BOX THIS LAP..."
bg1_path = BRAIN_DIR / "f1_gameplay_redbull_bg_1794866530802.jpg"
if bg1_path.exists():
    with Image.open(bg1_path) as im:
        bg1 = im.convert("RGBA")
        # HUD Red Bull
        hud1 = draw_f1_radio_hud(
            driver_name="VERSTAPPEN",
            car_number="1",
            team_color_hex="#3671C6",
            badge_file="redbull.png",
            driver_query="HOW ARE MY TYRES?",
            engineer_reply="Box this lap, box for Hards. Norris is 2.1s ahead, we have an undercut window!",
            width=430,
        )
        # Pegar en la esquina superior derecha con margen
        pos_x = bg1.width - hud1.width - 48
        pos_y = 48
        bg1.paste(hud1, (pos_x, pos_y), hud1)

        out1 = DESKTOP_DIR / "screenshot_1_f1_radio_redbull_en.png"
        bg1.convert("RGB").save(out1, "PNG", quality=95)
        print(f"[OK] Creada captura 1: {out1}")

# 2. Captura 2: Ferrari / Charles Leclerc - "IS IT GOING TO RAIN?" -> "WEATHER RADAR..."
bg2_path = BRAIN_DIR / "f1_gameplay_redbull_bg_1794866530802.jpg"
if bg2_path.exists():
    with Image.open(bg2_path) as im:
        # Voltear horizontalmente o recortar para variar la escena
        bg2 = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert("RGBA")
        # HUD Ferrari
        hud2 = draw_f1_radio_hud(
            driver_name="LECLERC",
            car_number="16",
            team_color_hex="#FF1E27",
            badge_file="ferrari.png",
            driver_query="WHAT IS OUR STRATEGY?",
            engineer_reply="Plan A is solid. Rain intensity increasing in 5 laps, we stay out on Inters.",
            width=430,
        )
        pos_x = bg2.width - hud2.width - 48
        pos_y = 48
        bg2.paste(hud2, (pos_x, pos_y), hud2)

        out2 = DESKTOP_DIR / "screenshot_2_f1_radio_ferrari_en.png"
        bg2.convert("RGB").save(out2, "PNG", quality=95)
        print(f"[OK] Creada captura 2: {out2}")

# 3. Captura 3: McLaren / Lando Norris - "RADIO CHECK" -> "FIVE BY FIVE..."
if bg1_path.exists():
    with Image.open(bg1_path) as im:
        bg3 = im.convert("RGBA")
        hud3 = draw_f1_radio_hud(
            driver_name="NORRIS",
            car_number="4",
            team_color_hex="#FF8000",
            badge_file="mclaren.png",
            driver_query="HOW MANY CARS ARE OUT?",
            engineer_reply="Two cars out: Hamilton and Gasly are DNF. Safety Car deployed, delta positive!",
            width=430,
        )
        pos_x = bg3.width - hud3.width - 48
        pos_y = 48
        bg3.paste(hud3, (pos_x, pos_y), hud3)

        out3 = DESKTOP_DIR / "screenshot_3_f1_radio_mclaren_en.png"
        bg3.convert("RGB").save(out3, "PNG", quality=95)
        print(f"[OK] Creada captura 3: {out3}")
