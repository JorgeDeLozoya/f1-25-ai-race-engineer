"""Script de empaquetado y distribucion para Overtake.gg (RaceDepartment) y Swofty Launcher."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
RELEASE_DIR = ROOT_DIR / "release_overtake"
VENV_PY = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
PYINSTALLER_EXE = ROOT_DIR / ".venv" / "Scripts" / "pyinstaller.exe"

README_TEXT = """================================================================================
          F1 25 / F1 26 - AI RACE ENGINEER (VOICE + TELEMETRY + F1 TV HUD)
                             F1 Community · Overtake.gg
================================================================================

[ENGLISH]
An authentic, real-time AI Race Engineer for EA Sports F1 25 and F1 26.
Features real-time UDP telemetry analysis, F1 TV broadcast radio graphics overlay,
OBS Studio Browser Source for streamers, Steering Wheel / Gamepad PTT support,
neural voices in 6 languages (EN, ES, DE, FR, IT, PT), dynamic sprint & full race
strategies, and realistic pit wall dialogue.

1. QUICK START (STANDALONE)
--------------------------------------------------------------------------------
1. Extract this entire folder anywhere on your PC (e.g. C:\\Games\\AIRaceEngineer).
2. Launch "AI_Race_Engineer.exe" (or "Start_AI_Race_Engineer.bat").
3. In F1 25, go to:
   - Game Options -> Settings -> Telemetry Settings:
     * UDP Telemetry: ON
     * UDP IP Address: 127.0.0.1 (or 0.0.0.0)
     * UDP Port: 20777
     * UDP Send Rate: 60Hz
     * UDP Format: 2025 (or 2024)
   - Video Settings -> Display Mode:
     * Set to "Borderless Windowed" (allows the F1 TV Radio HUD overlay to render smoothly).
4. In the app, select your preferred microphone. You can press F9, use the "Detect Wheel Button"
   feature to bind your steering wheel / gamepad button, or simply say "Engineer" to open the radio!

2. OBS STUDIO / STREAMLABS BROWSER SOURCE (FOR STREAMERS)
--------------------------------------------------------------------------------
Want the F1 TV radio graphic to show up on your Twitch / YouTube stream even in full screen?
In OBS Studio:
- Add a new "Browser Source"
- URL: http://localhost:8088/overlay
- Width: 1920
- Height: 1080
- Done! The radio graphic will pop up with transparent background whenever the pit wall talks!

3. FOR SWOFTY LAUNCHER USERS
--------------------------------------------------------------------------------
If you use Swofty Launcher, simply double-click "jorge.ai-race-engineer.swoftyaddon"
or drop it into Swofty to install it with one click!

4. POPULAR RADIO VOICE COMMANDS
--------------------------------------------------------------------------------
* Retirements / DNFs:
  - "How many cars are out?" / "Who is out?" / "Any retirements?"
  - "¿Cuántos coches están fuera?" / "¿Quién está fuera?" / "¿Quién ha abandonado?"
* Leaders & Positions:
  - "Who is leading?" / "Who is P1?" / "What is my position?"
  - "¿Quién va primero?" / "¿Quién lidera?" / "¿En qué posición voy?"
* Gaps & Traffic:
  - "Who is behind me?" / "Gap behind?" / "Who is in front?" / "Gap ahead?"
  - "¿Quién viene detrás?" / "¿A cuánto está el de detrás?" / "¿A cuánto está el de delante?"
* Pit Stop & Strategy:
  - "What is our strategy?" / "Should I box now?" / "Plan A or Plan B?"
  - "¿Cuál es la estrategia?" / "¿Cuándo paramos en boxes?" / "¿Hacemos undercut?"
* Setup & Car Advice:
  - "What brake bias should I run?" / "Differential advice?"
  - "¿Qué reparto de frenada pongo?" / "¿Qué diferencial pongo?"
* Tyres & Wear:
  - "How are my tyres?" / "Tyre degradation status?"
  - "¿Cómo van los neumáticos?" / "¿Cuánto desgaste tengo?"
* Weather & Rain:
  - "Is it going to rain?" / "Weather radar forecast?"
  - "¿Va a llover?" / "¿Cuál es la previsión del tiempo?"
* Damage & Radio Check:
  - "Damage check?" / "Check front wing" / "Radio check!"
  - "¿Tengo daños?" / "Revisa el coche" / "Radio check, ¿me recibes?"


================================================================================
[ESPAÑOL]
Ingeniero de pista hiperrealista con IA para EA Sports F1 25 y F1 26.
Incluye análisis de telemetría UDP a 60Hz, HUD gráfico de radio estilo F1 TV,
fuente de navegador web para OBS Studio (streamers), soporte de botón PTT para
volantes (Logitech, Fanatec, Thrustmaster, Moza) y mandos, voces neuronales en 6
idiomas, y detección automática del piloto oficial que lleves.

1. GUÍA RÁPIDA DE INSTALACIÓN
--------------------------------------------------------------------------------
1. Descomprime este archivo ZIP en cualquier carpeta de tu ordenador.
2. Ejecuta "AI_Race_Engineer.exe".
3. En F1 25, entra en:
   - Opciones de juego -> Ajustes de telemetría:
     * Telemetría UDP: ACTIVADA
     * Dirección IP UDP: 127.0.0.1 (o 0.0.0.0)
     * Puerto UDP: 20777
     * Frecuencia de envío UDP: 60Hz
   - Opciones de vídeo -> Pantalla:
     * Modo de visualización: "Ventana sin bordes" (necesario para ver el HUD de radio en pantalla).
4. Elige tu micrófono en los ajustes y pulsa F9, detecta el botón de tu volante con el botón de ajustes,
   o di "Ingeniero" por voz para hablar por radio.

================================================================================
¡Disfruta de tus carreras y nos vemos en lo más alto del podio!
"""

def build():
    print("=== 1. Empaquetando addon de Swofty (.swoftyaddon) ===")
    subprocess.run([str(VENV_PY), str(ROOT_DIR / "package_addon.py")], check=True)
    addon_file = ROOT_DIR.parent / "jorge.ai-race-engineer.swoftyaddon"
    if not addon_file.exists():
        addon_file = ROOT_DIR / "jorge.ai-race-engineer.swoftyaddon"

    print("=== 2. Preparando punto de entrada main.py ===")
    entry_script = ROOT_DIR / "entrypoint.py"
    entry_script.write_text(
        'import sys\nfrom engineer.app import main\n\nif __name__ == "__main__":\n    if "--gui" not in sys.argv and "--daemon" not in sys.argv and "--demo" not in sys.argv:\n        sys.argv.append("--gui")\n    main()\n',
        encoding="utf-8"
    )

    print("=== 3. Compilando binario con PyInstaller ===")
    assets_src = ROOT_DIR / "engineer" / "assets"
    add_data_arg = f"{assets_src};engineer/assets"

    cmd = [
        str(PYINSTALLER_EXE),
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name=AI_Race_Engineer",
        f"--add-data={add_data_arg}",
        "--hidden-import=sounddevice",
        "--hidden-import=soundfile",
        "--hidden-import=edge_tts",
        "--hidden-import=pynput",
        "--hidden-import=pynput.keyboard",
        "--hidden-import=pynput.keyboard._win32",
        "--hidden-import=requests",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=engineer.web_overlay",
        str(entry_script),
    ]
    subprocess.run(cmd, check=True)

    print("=== 4. Estructurando release para Overtake.gg ===")
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    app_dist_dir = DIST_DIR / "AI_Race_Engineer"
    target_app_dir = RELEASE_DIR / "AI_Race_Engineer"
    shutil.copytree(app_dist_dir, target_app_dir)

    # Copiar config.json y archivo de arranque rapido
    cfg_file = ROOT_DIR / "config.json"
    if cfg_file.exists():
        shutil.copy2(cfg_file, target_app_dir / "config.json")
        shutil.copy2(cfg_file, RELEASE_DIR / "config.json")

    # Copiar el addon de Swofty empaquetado
    if addon_file.exists():
        shutil.copy2(addon_file, RELEASE_DIR / "jorge.ai-race-engineer.swoftyaddon")

    # Escribir README para Overtake
    (RELEASE_DIR / "README_OVERTAKE.txt").write_text(README_TEXT, encoding="utf-8")
    (target_app_dir / "README_OVERTAKE.txt").write_text(README_TEXT, encoding="utf-8")

    # Bat de lanzamiento directo
    bat_content = '@echo off\ncd /d "%~dp0\\AI_Race_Engineer"\nstart "" "AI_Race_Engineer.exe"\n'
    (RELEASE_DIR / "Start_AI_Race_Engineer.bat").write_text(bat_content, encoding="utf-8")

    print("=== 5. Creando archivo comprimido ZIP para Overtake.gg ===")
    zip_path = ROOT_DIR / "F1_25_AI_Race_Engineer_v1.0.3_Overtake.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(RELEASE_DIR):
            for file in files:
                p = Path(root) / file
                arcname = p.relative_to(RELEASE_DIR)
                zf.write(p, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\n[OK] Release para Overtake.gg creada con éxito:")
    print(f" -> ZIP: {zip_path} ({size_mb:.2f} MB)")
    print(f" -> Carpeta lista: {RELEASE_DIR}")

if __name__ == "__main__":
    build()
