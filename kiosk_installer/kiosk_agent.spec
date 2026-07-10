# PyInstaller spec for the kiosk agent, run as:
#   pyinstaller kiosk_installer/kiosk_agent.spec --distpath kiosk_installer/dist --workpath kiosk_installer/build
#
# Produces two executables from the same kiosk_agent.py entry point:
#   - kiosk_agent.exe         (console)  -- interactive use: `enroll --employee-id N`,
#                                            or `listen` in the foreground for debugging.
#   - kiosk_agent_service.exe (windowed) -- used only by the Scheduled Task to run
#                                            `listen` silently in the background.
#     (Both variants always log to kiosk_agent.log next to the exe — see kiosk_agent.py.)
#
# pythonnet ships its own PyInstaller hook (registered as a `pyinstaller40` entry
# point, auto-discovered — see .venv/Lib/site-packages/pythonnet/_pyinstaller/) that
# bundles the .NET interop DLLs correctly. pyzkfp has no such hook, so its native
# libzkfpcsharp.dll (present at two paths inside the package -- pyzkfp/ itself and
# pyzkfp/dll/, both referenced by pyzkfp/zkfp2.py's own path lookup) is added
# explicitly below as `datas` (not `binaries`) so PyInstaller preserves the exact
# nested folder layout the package expects at runtime instead of flattening it.

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
PYZKFP_DIR = os.path.join(REPO_ROOT, '.venv', 'Lib', 'site-packages', 'pyzkfp')

pyzkfp_datas = collect_data_files('pyzkfp') + [
    (os.path.join(PYZKFP_DIR, 'libzkfpcsharp.dll'), 'pyzkfp'),
    (os.path.join(PYZKFP_DIR, 'dll', 'libzkfpcsharp.dll'), 'pyzkfp/dll'),
]

hiddenimports = (
    collect_submodules('pyzkfp')
    + collect_submodules('biometric')
    + ['clr', 'clr_loader', 'pythonnet']
)

a = Analysis(
    [os.path.join(REPO_ROOT, 'kiosk_agent.py')],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=pyzkfp_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['django', 'PyQt5', 'PySide2', 'matplotlib', 'numpy', 'tkinter'],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe_console = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='kiosk_agent',
    console=True,
    clean=True,
)

exe_windowed = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='kiosk_agent_service',
    console=False,
    clean=True,
)
