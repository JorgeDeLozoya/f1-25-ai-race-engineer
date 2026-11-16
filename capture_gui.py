import time
import threading
from pathlib import Path
from PIL import ImageGrab
from engineer.config import EngineerConfig
from engineer.app import RaceEngineerApp
from engineer.gui import PitWallWindow

cfg = EngineerConfig()
cfg.language = "en"
cfg.driver_name = "Driver"
cfg.engineer_name = "Engineer"

app = RaceEngineerApp(cfg)
gui = PitWallWindow(app)

def auto_cap():
    time.sleep(1.5)
    gui.root.update()
    x = gui.root.winfo_rootx()
    y = gui.root.winfo_rooty()
    w = gui.root.winfo_width()
    h = gui.root.winfo_height()
    if w > 200 and h > 200:
        im = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        out_path = Path(r"D:\Escritorio\screenshot_4_app_dashboard_en.png")
        im.save(out_path)
        print(f"[OK] Dashboard capturado: {out_path}")
    gui.root.after(100, gui.root.destroy)

threading.Thread(target=auto_cap, daemon=True).start()
gui.root.mainloop()
