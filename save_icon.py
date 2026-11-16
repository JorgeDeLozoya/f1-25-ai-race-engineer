import os
from PIL import Image

src = r"C:\Users\Jorge\.gemini\antigravity\brain\17759d81-ba4b-4147-a3d6-3106ea9e1770\ai_race_engineer_minimalist_icon_1794864127653.jpg"
im = Image.open(src)
im = im.resize((512, 512), Image.Resampling.LANCZOS)

out_desk_png = r"D:\Escritorio\mod_icon.png"
out_desk_jpg = r"D:\Escritorio\mod_icon.jpg"
out_local = r"c:\Users\Jorge\.gemini\antigravity\scratch\f1_mods\ai_race_engineer\icon.png"

im.save(out_desk_png, "PNG")
im.save(out_desk_jpg, "JPEG", quality=95)
im.save(out_local, "PNG")

print("Files saved:")
print(f"  {out_desk_png} (size: {os.path.getsize(out_desk_png)} bytes)")
print(f"  {out_desk_jpg} (size: {os.path.getsize(out_desk_jpg)} bytes)")
print(f"  {out_local} (size: {os.path.getsize(out_local)} bytes)")
