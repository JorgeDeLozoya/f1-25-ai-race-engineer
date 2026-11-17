"""Script de empaquetado y distribucion AV-clean para Overtake.gg (RaceDepartment).

Usa un runtime portable oficial de Python (firmado digitalmente por Python Software
Foundation) en lugar de PyInstaller para evitar falsos positivos en antivirus / VirusTotal.
Por defecto genera unicamente la version Standalone normal (sin Swofty Addon).
Usa --with-swofty para incluir tambien la carpeta del addon de Swofty Launcher.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "build"
RUNTIME_CACHE_DIR = BUILD_DIR / "portable_runtime"
RELEASE_DIR = ROOT_DIR / "release_overtake"
DESKTOP_DIR = Path(r"D:\Escritorio")
ZIP_NAME = "F1_25_AI_Race_Engineer_v1.0.3_Overtake.zip"

RUNTIME_PACKAGES = [
    "numpy>=2.0.0",
    "sounddevice>=0.5.0",
    "soundfile>=0.12.1",
    "vosk>=0.3.45",
    "edge-tts>=6.1.12",
    "google-genai>=1.0.0",
    "pillow>=10.0.0",
]

README_ROOT_TEXT = """================================================================================
          F1 25 / F1 26 - AI RACE ENGINEER (VOICE + TELEMETRY + F1 TV HUD)
                                By JorgeDelo · Overtake.gg
================================================================================

Este archivo comprimido contiene 2 OPCIONES para que elijas la que prefieras:
This package includes 2 OPTIONS depending on your preference:

--------------------------------------------------------------------------------
CARPETA 1: "1_Standalone_Version (Sin Swofty)"
--------------------------------------------------------------------------------
[ES] Version estandar completa e independiente. NO necesitas instalar nada mas.
     Incluye la app con interfaz grafica, reconocimiento de voz (Pulsar para hablar
     con tecla o boton de volante/mando), HUD de radio oficial de F1 en pantalla,
     y servidor de streaming para OBS Studio.
     -> Para usarlo: Abre la carpeta y ejecuta "Start_AI_Race_Engineer.bat".

[EN] Full standalone application. NO other software or launcher required.
     Includes GUI, push-to-talk voice recognition (keyboard / steering wheel / gamepad),
     live F1 TV broadcast radio HUD overlay, and OBS browser source.
     -> To use: Open the folder and run "Start_AI_Race_Engineer.bat".

--------------------------------------------------------------------------------
CARPETA 2: "2_Swofty_Addon_Version"
--------------------------------------------------------------------------------
[ES] Si ya utilizas el launcher Swofty HUD (ecosistema Swofty), aqui tienes el
     archivo empaquetado "ai_engineer.swoftyaddon".
     -> Para usarlo: Haz doble clic en el archivo o arrastralo a tu Swofty.

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

[ESPANOL]
1. Descomprime TODO el archivo ZIP en una carpeta de tu ordenador (por ejemplo C:\\Games\\AIRaceEngineer).
2. Haz doble clic en "Start_AI_Race_Engineer.bat" para iniciar la aplicacion.
   (No necesitas tener Python instalado; todo viene incluido y verificado en la carpeta "runtime").
   Si necesitas ver la consola de diagnostico, ejecuta "Debug_Start_AI_Race_Engineer.bat".
3. En F1 25 / F1 26, ve a:
   - Opciones de juego -> Ajustes de telemetria:
     * Telemetria UDP: ACTIVADA
     * Direccion IP UDP: 127.0.0.1 (o 0.0.0.0)
     * Puerto UDP: 20777
     * Frecuencia de envio UDP: 60Hz
     * Formato UDP: 2025 (o 2024)
   - Opciones de video -> Pantalla:
     * Modo de visualizacion: "Ventana sin bordes" (para ver el HUD de radio sobre el juego).
4. Elige tu microfono en los ajustes y pulsa F9, detecta el boton de tu volante en Ajustes,
   o di "Ingeniero" por voz para hablar por radio.

OBS STUDIO (PARA STREAMERS):
- Anade una fuente de navegador (Browser Source) en OBS.
- URL: http://localhost:8088/overlay
- Ancho: 1920, Alto: 1080.
- Aparecera el HUD de radio de F1 en tus transmisiones con fondo transparente.

--------------------------------------------------------------------------------
[ENGLISH]
1. Extract this ENTIRE ZIP archive to a folder on your PC (e.g. C:\\Games\\AIRaceEngineer).
2. Double-click "Start_AI_Race_Engineer.bat" to start.
   (No separate Python installation required; a signed portable runtime is bundled in "runtime").
   For console logs / troubleshooting, run "Debug_Start_AI_Race_Engineer.bat".
3. In F1 25 / F1 26 Telemetry Settings:
   - UDP Telemetry: ON
   - UDP IP Address: 127.0.0.1 (or 0.0.0.0)
   - UDP Port: 20777
   - UDP Send Rate: 60Hz
   - Display Mode: Borderless Windowed (required for the F1 TV Radio HUD overlay).
4. Select your mic in Settings, press F9 or bind your steering wheel / gamepad button to talk!

OBS STUDIO (FOR STREAMERS):
- Add a Browser Source in OBS -> URL: http://localhost:8088/overlay (1920x1080).

================================================================================
* Created by JorgeDelo · Feedback & suggestions welcome on Overtake.gg!
================================================================================
"""

README_SWOFTY_TEXT = """================================================================================
                     AI RACE ENGINEER - SWOFTY ADDON
                                By JorgeDelo
================================================================================

[ESPANOL]
Instalacion en Swofty Launcher:
1. Haz doble clic en "ai_engineer.swoftyaddon" o arrastralo directamente a la ventana
   de Swofty Launcher.
2. Swofty instalara y activara automaticamente el widget del ingeniero de pista con IA.
3. Asegurate de tener activada la telemetria UDP en el juego F1 (Puerto 20777).

[ENGLISH]
Installation for Swofty Launcher:
1. Double-click "ai_engineer.swoftyaddon" or drag and drop it into Swofty Launcher.
2. Swofty will automatically register and launch the AI Race Engineer widget.
3. Ensure F1 UDP Telemetry is enabled in game (Port 20777).
"""


def _find_python312_base() -> Path:
    """Localiza la instalacion oficial de Python 3.12 (firmada por Python Software Foundation)."""
    if sys.version_info[:2] == (3, 12):
        base = Path(sys.base_prefix)
        if (base / "pythonw.exe").exists() and (base / "DLLs" / "_tkinter.pyd").exists():
            return base

    for cmd in (["py", "-3.12", "-c", "import sys; print(sys.base_prefix)"],):
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            p = Path(out)
            if (p / "pythonw.exe").exists() and (p / "DLLs" / "_tkinter.pyd").exists():
                return p
        except Exception:
            pass

    raise RuntimeError(
        "No se encontro Python 3.12 oficial con Tkinter para construir el runtime portable."
    )


def _ignore_stdlib(dirpath: str, names: list[str]) -> set[str]:
    p = Path(dirpath)
    ignored: set[str] = set()
    for name in names:
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
        elif p.name == "Lib" and name in ("site-packages", "test", "idlelib", "ensurepip", "turtledemo", "venv"):
            ignored.add(name)
        elif p.name == "tkinter" and name == "test":
            ignored.add(name)
    return ignored


def _ignore_dlls(_dirpath: str, names: list[str]) -> set[str]:
    return {
        n for n in names
        if n.endswith((".pdb", ".lib", ".ico")) or "_test" in n
    }


def _strip_pycache(root: Path) -> None:
    for d in list(root.rglob("__pycache__")):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def build_portable_runtime(rebuild: bool = False) -> Path:
    """Construye un runtime portable de Python 3.12 firmado por PSF + dependencias sin PyInstaller."""
    if not rebuild and (RUNTIME_CACHE_DIR / "pythonw.exe").exists() and (
        RUNTIME_CACHE_DIR / "Lib" / "site-packages" / "vosk"
    ).exists():
        scripts_dir = RUNTIME_CACHE_DIR / "Scripts"
        if scripts_dir.exists():
            shutil.rmtree(scripts_dir, ignore_errors=True)
        print("=== 1. Usando runtime portable PSF existente en build/portable_runtime ===")
        return RUNTIME_CACHE_DIR

    print("=== 1. Construyendo runtime portable oficial de Python 3.12 (firmado por PSF) ===")
    base = _find_python312_base()
    if RUNTIME_CACHE_DIR.exists():
        shutil.rmtree(RUNTIME_CACHE_DIR)
    RUNTIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for fname in ("python.exe", "pythonw.exe", "python312.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        src = base / fname
        if src.exists():
            shutil.copy2(src, RUNTIME_CACHE_DIR / fname)

    sys32 = Path(r"C:\Windows\System32")
    for msvc_dll in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll"):
        p_dll = sys32 / msvc_dll
        if p_dll.exists():
            shutil.copy2(p_dll, RUNTIME_CACHE_DIR / msvc_dll)

    shutil.copytree(base / "DLLs", RUNTIME_CACHE_DIR / "DLLs", ignore=_ignore_dlls)

    tcl_dst = RUNTIME_CACHE_DIR / "tcl"
    tcl_dst.mkdir(parents=True, exist_ok=True)
    for sub in ("tcl8.6", "tk8.6"):
        src_sub = base / "tcl" / sub
        if src_sub.exists():
            shutil.copytree(src_sub, tcl_dst / sub)

    shutil.copytree(base / "Lib", RUNTIME_CACHE_DIR / "Lib", ignore=_ignore_stdlib)
    site_pkg = RUNTIME_CACHE_DIR / "Lib" / "site-packages"
    site_pkg.mkdir(parents=True, exist_ok=True)

    runtime_py = RUNTIME_CACHE_DIR / "python.exe"
    uv_exe = shutil.which("uv")
    if uv_exe:
        print(" -> Instalando dependencias en runtime/Lib/site-packages via uv...")
        subprocess.run(
            [uv_exe, "pip", "install", "--python", str(runtime_py), *RUNTIME_PACKAGES],
            check=True,
        )
    else:
        print(" -> Instalando dependencias en runtime/Lib/site-packages via pip...")
        subprocess.run(
            [
                str(base / "python.exe"),
                "-m",
                "pip",
                "install",
                "--target",
                str(site_pkg),
                "--upgrade",
                "--no-user",
                *RUNTIME_PACKAGES,
            ],
            check=True,
        )

    # Eliminar runtime/Scripts/*.exe (wrappers CLI sin firmar innecesarios en ejecucion)
    scripts_dir = RUNTIME_CACHE_DIR / "Scripts"
    if scripts_dir.exists():
        shutil.rmtree(scripts_dir, ignore_errors=True)

    _strip_pycache(RUNTIME_CACHE_DIR)
    return RUNTIME_CACHE_DIR


def _copy_app_sources(dest_app_dir: Path) -> None:
    """Copia el paquete engineer/ limpio (sin __pycache__ ni binarios temporales) a app/."""
    dest_eng = dest_app_dir / "engineer"
    shutil.copytree(
        ROOT_DIR / "engineer",
        dest_eng,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _write_standalone_folder(folder_standalone: Path, runtime_src: Path) -> None:
    folder_standalone.mkdir(parents=True, exist_ok=True)

    target_app_dir = folder_standalone / "app"
    _copy_app_sources(target_app_dir)

    target_runtime_dir = folder_standalone / "runtime"
    shutil.copytree(runtime_src, target_runtime_dir)

    cfg_file = ROOT_DIR / "config.json"
    if cfg_file.exists():
        shutil.copy2(cfg_file, folder_standalone / "config.json")

    bat_content = (
        '@echo off\r\n'
        'setlocal\r\n'
        'cd /d "%~dp0"\r\n'
        'if not exist "runtime\\pythonw.exe" (\r\n'
        '    echo.\r\n'
        '    echo ======================================================================\r\n'
        '    echo  ERROR: No se encuentra runtime\\pythonw.exe\r\n'
        '    echo ======================================================================\r\n'
        '    echo  Por favor, asegurate de DESCOMPRIMIR (Extraer todo) el archivo ZIP\r\n'
        '    echo  antes de ejecutar el programa. No lo abras directamente dentro del ZIP.\r\n'
        '    echo ======================================================================\r\n'
        '    echo.\r\n'
        '    pause\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'set "PYTHONNOUSERSITE=1"\r\n'
        'set "PYTHONPATH=%~dp0app"\r\n'
        'set "ENGINEER_CONFIG=%~dp0config.json"\r\n'
        'set "TCL_LIBRARY=%~dp0runtime\\tcl\\tcl8.6"\r\n'
        'set "TK_LIBRARY=%~dp0runtime\\tcl\\tk8.6"\r\n'
        'start "" "%~dp0runtime\\pythonw.exe" -s -m engineer --gui\r\n'
    )
    (folder_standalone / "Start_AI_Race_Engineer.bat").write_text(bat_content, encoding="utf-8")

    debug_bat = (
        '@echo off\r\n'
        'setlocal\r\n'
        'cd /d "%~dp0"\r\n'
        'if not exist "runtime\\python.exe" (\r\n'
        '    echo [ERROR] No se encuentra runtime\\python.exe.\r\n'
        '    echo Asegurate de descomprimir todo el ZIP antes de iniciar.\r\n'
        '    pause\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'echo Iniciando AI Race Engineer en modo consola...\r\n'
        'set "PYTHONNOUSERSITE=1"\r\n'
        'set "PYTHONPATH=%~dp0app"\r\n'
        'set "ENGINEER_CONFIG=%~dp0config.json"\r\n'
        'set "TCL_LIBRARY=%~dp0runtime\\tcl\\tcl8.6"\r\n'
        'set "TK_LIBRARY=%~dp0runtime\\tcl\\tk8.6"\r\n'
        '"%~dp0runtime\\python.exe" -s -m engineer --gui\r\n'
        'if %errorlevel% neq 0 (\r\n'
        '    echo.\r\n'
        '    echo [AVISO] La aplicacion se cerro con codigo %errorlevel%.\r\n'
        '    pause\r\n'
        ')\r\n'
    )
    (folder_standalone / "Debug_Start_AI_Race_Engineer.bat").write_text(debug_bat, encoding="utf-8")
    (folder_standalone / "README_STANDALONE.txt").write_text(README_STANDALONE_TEXT, encoding="utf-8")


def build(rebuild_runtime: bool = False, include_swofty: bool = False) -> None:
    runtime_src = build_portable_runtime(rebuild=rebuild_runtime)

    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    pkg_addon_script = ROOT_DIR / "package_addon.py"
    if include_swofty and pkg_addon_script.exists():
        print("=== 2. Empaquetando addon de Swofty (.swoftyaddon) + Standalone ===")
        py_runner = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        if not py_runner.exists():
            py_runner = Path(sys.executable)
        subprocess.run([str(py_runner), str(pkg_addon_script)], check=True)
        addon_file = ROOT_DIR.parent / "ai_engineer.swoftyaddon"
        if not addon_file.exists():
            addon_file = ROOT_DIR / "ai_engineer.swoftyaddon"

        folder_standalone = RELEASE_DIR / "1_Standalone_Version (Sin Swofty)"
        folder_swofty = RELEASE_DIR / "2_Swofty_Addon_Version"
        _write_standalone_folder(folder_standalone, runtime_src)

        folder_swofty.mkdir(parents=True, exist_ok=True)
        cfg_file = ROOT_DIR / "config.json"
        if cfg_file.exists():
            shutil.copy2(cfg_file, folder_swofty / "config.json")
        if addon_file.exists():
            shutil.copy2(addon_file, folder_swofty / "ai_engineer.swoftyaddon")
        (folder_swofty / "README_SWOFTY.txt").write_text(README_SWOFTY_TEXT, encoding="utf-8")
        (RELEASE_DIR / "README_FIRST.txt").write_text(README_ROOT_TEXT, encoding="utf-8")
    else:
        print("=== 2. Estructurando release Standalone (sin Swofty Addon) ===")
        _write_standalone_folder(RELEASE_DIR, runtime_src)

    print("=== 3. Creando archivo comprimido ZIP para Overtake.gg ===")
    zip_path = ROOT_DIR / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(RELEASE_DIR):
            for file in files:
                p = Path(root) / file
                arcname = p.relative_to(RELEASE_DIR)
                zf.write(p, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\n[OK] Release para Overtake.gg creada con exito:")
    print(f" -> ZIP local: {zip_path} ({size_mb:.2f} MB)")

    if DESKTOP_DIR.exists():
        dest_zip = DESKTOP_DIR / ZIP_NAME
        shutil.copy2(zip_path, dest_zip)
        print(f" -> Copiado a Escritorio: {dest_zip}")

        dest_folder = DESKTOP_DIR / "F1_25_AI_Race_Engineer_v1.0.3_Overtake"
        if dest_folder.exists():
            shutil.rmtree(dest_folder)
        shutil.copytree(RELEASE_DIR, dest_folder)
        print(f" -> Carpeta en Escritorio sincronizada: {dest_folder}")


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    with_swofty = "--with-swofty" in sys.argv
    build(rebuild_runtime=rebuild, include_swofty=with_swofty)
