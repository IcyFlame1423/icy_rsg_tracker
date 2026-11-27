"""Writes build\\version_info.txt for PyInstaller (see build.bat): the version and names Windows
shows in the .exe's Properties > Details, from icy_rsg_tracker.__version__."""
from pathlib import Path

from icy_rsg_tracker import __version__

parts = [int(p) for p in __version__.split(".")] + [0] * 4
version = tuple(parts[:4])
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={version}, prodvers={version}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'IcyFlame1423'),
      StringStruct('FileDescription', 'Icy RSG Tracker - Minecraft RSG speedrun tracker'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'icy_rsg_tracker'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 IcyFlame1423. MIT License.'),
      StringStruct('OriginalFilename', 'icy_rsg_tracker.exe'),
      StringStruct('ProductName', 'Icy RSG Tracker'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = Path(__file__).parent / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(text, encoding="utf-8")
print(f"Wrote {out} ({__version__})")
