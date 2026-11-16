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
DESKTOP_DIR = Path(r"D:\Escritorio")

README_ROOT_TEXT = """================================================================================
          F1 25 / F1 26 - AI RACE ENGINEER (VOICE + TELEMETRY + F1 TV HUD)
                                By JorgeDelo · Overtake.gg
================================================================================

Este archivo comprimido contiene 2 OPCIONES para que elijas la que prefieras:
This package includes 2 OPTIONS depending on your preference:

--------------------------------------------------------------------------------
📁 CARPETA 1: "1_Standalone_Version (Sin Swofty)"
--------------------------------------------------------------------------------
[ES] Versión estándar completa e independiente. NO necesitas instalar nada más.
     Incluye la app con interfaz gráfica, reconocimiento de voz (Pulsar para hablar
     con tecla o botón de volante/mando), HUD de radio oficial de F1 en pantalla,
     y servidor de streaming para OBS Studio.
     -> Para usarlo: Abre la carpeta y ejecuta "Start_AI_Race_Engineer.bat".

[EN] Full standalone application. NO other software or launcher required.
     Includes GUI, push-to-talk voice recognition (keyboard / steering wheel / gamepad),
     live F1 TV broadcast radio HUD overlay, and OBS browser source.
     -> To use: Open the folder and run "Start_AI_Race_Engineer.bat".

--------------------------------------------------------------------------------
📁 CARPETA 2: "2_Swofty_Addon_Version"
--------------------------------------------------------------------------------
[ES] Si ya utilizas el launcher Swofty HUD (ecosistema Swofty), aquí tienes el
     archivo empaquetado "ai_engineer.swoftyaddon".
     -> Para usarlo: Haz doble clic en el archivo o arrástralo a tu Swofty.

[EN] For users who already use the Swofty HUD ecosystem.
     Contains the packaged "ai_engineer.swoftyaddon".
     -> To use: Double click the addon or drag & drop it into Swofty Launcher.

================================================================================
* Creado por JorgeDelo / Created by JorgeDelo
* Sugerencias, feedback y mejoras en los comentarios de Overtake.gg / RaceDepartment!
================================================================================
"""

README_STANDALONE_TEXT = """================================================================================
                     AI RACE ENGINEER - STANDALONE VERSION
                                By JorgeDelo
================================================================================

[ESPAÑOL]
1. Descomprime todo el archivo ZIP en una carpeta de tu ordenador.
2. Haz doble clic en "Start_AI_Race_Engineer.bat" para iniciar la aplicación.
3. En F1 25, ve a:
   - Opciones de juego -> Ajustes de telemetría:
     * Telemetría UDP: ACTIVADA
     * Dirección IP UDP: 127.0.0.1 (o 0.0.0.0)
     * Puerto UDP: 20777
     * Frecuencia de envío UDP: 60Hz
     * Formato UDP: 2025 (o 2024)
   - Opciones de vídeo -> Pantalla:
     * Modo de visualización: "Ventana sin bordes" (para ver el HUD de radio sobre el juego).
4. Elige tu micrófono en los ajustes y pulsa F9, detecta el botón de tu volante con el botón de ajustes,
   o di "Ingeniero" por voz para hablar por radio.

OBS STUDIO (PARA STREAMERS):
- Añade una fuente de navegador (Browser Source) en OBS.
- URL: http://localhost:8088/overlay
- Ancho: 1920, Alto: 1080.
- ¡Aparecerá el HUD de radio de F1 en tus transmisiones con fondo transparente!

--------------------------------------------------------------------------------
[ENGLISH]
1. Extract this entire folder on your PC.
2. Double-click "Start_AI_Race_Engineer.bat" to start.
3. In F1 25 Telemetry Settings:
   - UDP Telemetry: ON
   - UDP Port: 20777
   - UDP Send Rate: 60Hz
   - Display Mode: Borderless Windowed (for the radio HUD).
4. Select your mic, press F9 or bind your steering wheel / gamepad button to talk!
"""

README_SWOFTY_TEXT = """================================================================================
                     AI RACE ENGINEER - SWOFTY ADDON
                                By JorgeDelo
================================================================================

[ESPAÑOL]
Instalación en Swofty Launcher:
1. Haz doble clic en "ai_engineer.swoftyaddon" o arrástralo directamente a la ventana
   de Swofty Launcher.
2. Swofty instalará y activará automáticamente el widget del ingeniero de pista con IA.
3. Asegúrate de tener activada la telemetría UDP en el juego F1 (Puerto 20777).

[ENGLISH]
Installation for Swofty Launcher:
1. Double-click "ai_engineer.swoftyaddon" or drag and drop it into Swofty Launcher.
2. Swofty will automatically register and launch the AI Race Engineer widget.
3. Ensure F1 UDP Telemetry is enabled in game (Port 20777).
"""


def build(rebuild_binary: bool = False):
    print("=== 1. Empaquetando addon de Swofty (.swoftyaddon) ===")
    subprocess.run([str(VENV_PY), str(ROOT_DIR / "package_addon.py")], check=True)
    addon_file = ROOT_DIR.parent / "ai_engineer.swoftyaddon"
    if not addon_file.exists():
        addon_file = ROOT_DIR / "ai_engineer.swoftyaddon"

    app_dist_dir = DIST_DIR / "AI_Race_Engineer"
    vosk_src = ROOT_DIR / ".venv" / "Lib" / "site-packages" / "vosk"

    if rebuild_binary or not (app_dist_dir / "AI_Race_Engineer.exe").exists():
        print("=== 2. Compilando binario con PyInstaller ===")
        entry_script = ROOT_DIR / "entrypoint.py"
        entry_script.write_text(
            'import sys\nimport PIL\nimport PIL.Image\nimport PIL.ImageTk\nimport engineer.gui\nimport engineer.overlay\nfrom engineer.app import main\n\nif __name__ == "__main__":\n    if "--gui" not in sys.argv and "--daemon" not in sys.argv and "--demo" not in sys.argv:\n        sys.argv.append("--gui")\n    main()\n',
            encoding="utf-8"
        )
        assets_src = ROOT_DIR / "engineer" / "assets"
        cmd = [
            str(PYINSTALLER_EXE),
            "--noconfirm",
            "--onedir",
            "--windowed",
            "--name=AI_Race_Engineer",
            f"--add-data={assets_src};engineer/assets",
            f"--add-binary={vosk_src / 'libvosk.dll'};vosk",
            f"--add-binary={vosk_src / 'libgcc_s_seh-1.dll'};vosk",
            f"--add-binary={vosk_src / 'libstdc++-6.dll'};vosk",
            f"--add-binary={vosk_src / 'libwinpthread-1.dll'};vosk",
            "--collect-all=vosk",
            "--collect-all=sounddevice",
            "--collect-all=soundfile",
            "--collect-all=PIL",
            "--hidden-import=PIL",
            "--hidden-import=PIL.Image",
            "--hidden-import=PIL.ImageTk",
            "--hidden-import=engineer.gui",
            "--hidden-import=engineer.overlay",
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
    else:
        print("=== 2. Usando binario existente en dist/AI_Race_Engineer ===")

    # Asegurar DLLs en dist
    v_internal = app_dist_dir / "_internal" / "vosk"
    v_internal.mkdir(parents=True, exist_ok=True)
    for item in vosk_src.iterdir():
        if item.is_file():
            shutil.copy2(item, v_internal / item.name)

    sys32 = Path(r"C:\Windows\System32")
    for msvc_dll in ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll"]:
        p_dll = sys32 / msvc_dll
        if p_dll.exists():
            shutil.copy2(p_dll, app_dist_dir / "_internal" / msvc_dll)

    print("=== 3. Estructurando release con 2 CARPETAS SEPARADAS ===")
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    folder_standalone = RELEASE_DIR / "1_Standalone_Version (Sin Swofty)"
    folder_swofty = RELEASE_DIR / "2_Swofty_Addon_Version"
    folder_standalone.mkdir(parents=True)
    folder_swofty.mkdir(parents=True)

    # 1. Standalone Version
    target_app_dir = folder_standalone / "AI_Race_Engineer"
    shutil.copytree(app_dist_dir, target_app_dir)

    cfg_file = ROOT_DIR / "config.json"
    if cfg_file.exists():
        shutil.copy2(cfg_file, folder_standalone / "config.json")
        shutil.copy2(cfg_file, target_app_dir / "config.json")
        shutil.copy2(cfg_file, folder_swofty / "config.json")

    bat_content = (
        '@echo off\r\n'
        'setlocal\r\n'
        'cd /d "%~dp0"\r\n'
        'if not exist "AI_Race_Engineer\\AI_Race_Engineer.exe" (\r\n'
        '    echo.\r\n'
        '    echo ======================================================================\r\n'
        '    echo  ERROR: No se encuentra AI_Race_Engineer\\AI_Race_Engineer.exe\r\n'
        '    echo ======================================================================\r\n'
        '    echo  Por favor, asegurate de DESCOMPRIMIR (Extraer todo) el archivo ZIP\r\n'
        '    echo  antes de ejecutar el programa. No lo abras directamente dentro del ZIP.\r\n'
        '    echo ======================================================================\r\n'
        '    echo.\r\n'
        '    pause\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'cd "AI_Race_Engineer"\r\n'
        'start "" "AI_Race_Engineer.exe"\r\n'
    )
    (folder_standalone / "Start_AI_Race_Engineer.bat").write_text(bat_content, encoding="utf-8")

    debug_bat = (
        '@echo off\r\n'
        'setlocal\r\n'
        'cd /d "%~dp0"\r\n'
        'if not exist "AI_Race_Engineer\\AI_Race_Engineer.exe" (\r\n'
        '    echo [ERROR] No se encuentra AI_Race_Engineer\\AI_Race_Engineer.exe.\r\n'
        '    echo Asegurate de descomprimir todo el ZIP antes de iniciar.\r\n'
        '    pause\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'echo Iniciando AI Race Engineer en modo consola...\r\n'
        'cd "AI_Race_Engineer"\r\n'
        '"AI_Race_Engineer.exe"\r\n'
        'if %errorlevel% neq 0 (\r\n'
        '    echo.\r\n'
        '    echo [AVISO] La aplicacion se cerro con codigo %errorlevel%.\r\n'
        '    pause\r\n'
        ')\r\n'
    )
    (folder_standalone / "Debug_Start_AI_Race_Engineer.bat").write_text(debug_bat, encoding="utf-8")
    (folder_standalone / "README_STANDALONE.txt").write_text(README_STANDALONE_TEXT, encoding="utf-8")

    # 2. Swofty Addon Version
    if addon_file.exists():
        shutil.copy2(addon_file, folder_swofty / "ai_engineer.swoftyaddon")
    (folder_swofty / "README_SWOFTY.txt").write_text(README_SWOFTY_TEXT, encoding="utf-8")

    # 3. Archivo explicativo en la raíz
    (RELEASE_DIR / "README_FIRST.txt").write_text(README_ROOT_TEXT, encoding="utf-8")

    print("=== 4. Creando archivo comprimido ZIP para Overtake.gg ===")
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
    print(f" -> ZIP local: {zip_path} ({size_mb:.2f} MB)")

    # Copiar a D:\Escritorio
    if DESKTOP_DIR.exists():
        dest_zip = DESKTOP_DIR / "F1_25_AI_Race_Engineer_v1.0.3_Overtake.zip"
        shutil.copy2(zip_path, dest_zip)
        print(f" -> Copiado a Escritorio: {dest_zip}")

        dest_folder = DESKTOP_DIR / "F1_25_AI_Race_Engineer_v1.0.3_Overtake"
        if dest_folder.exists():
            shutil.rmtree(dest_folder)
        shutil.copytree(RELEASE_DIR, dest_folder)
        print(f" -> Carpeta en Escritorio sincronizada: {dest_folder}")

    descargas_dir = Path(r"D:\Descargas\F1_25_AI_Race_Engineer_v1.0.3_Overtake")
    if descargas_dir.parent.exists():
        try:
            if descargas_dir.exists():
                shutil.rmtree(descargas_dir)
            shutil.copytree(RELEASE_DIR, descargas_dir)
            print(f" -> Carpeta en Descargas sincronizada: {descargas_dir}")
        except Exception as e:
            print(f" [!] Aviso sync Descargas: {e}")


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    build(rebuild_binary=rebuild)
