# PyInstaller onedir console bundle. Only collected dependencies/code are included;
# user settings, runtime, source TC folders and build/test logs are never data inputs.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
hidden = collect_submodules('uvicorn') + collect_submodules('serial')
a = Analysis(
    [str(root / 'scripts' / 'windows_runner_entry.py')],
    pathex=[str(root)], binaries=[], datas=[], hiddenimports=hidden,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'tkinter', 'IPython'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='BSP-Windows-Runner',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='BSP-Windows-Runner')
