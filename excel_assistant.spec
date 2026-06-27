# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT, BUNDLE

block_cipher = None
base_dir = os.path.abspath('.')

datas = []
if os.path.isdir(os.path.join(base_dir, 'templates')):
    datas.append(('templates', 'templates'))
if os.path.exists(os.path.join(base_dir, '.env')):
    datas.append(('.env', '.'))

hiddenimports = ['openpyxl', 'pandas', 'openai']

python_exe = os.path.abspath(sys.executable)

# Some PyInstaller bundle types place binaries into Frameworks by default.
# To force the Python executable into Contents/MacOS/_internal, add it
# to `datas` with the target folder `MacOS/_internal` so it is copied
# into the exact path the bootloader expects.
if os.path.exists(python_exe):
    datas.append((python_exe, 'MacOS/_internal'))

analysis = Analysis(
    ['main.py'],
    pathex=[base_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name='ExcelAssistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        analysis.binaries,
        analysis.zipfiles,
        analysis.datas,
        strip=False,
        upx=False,
        name='ExcelAssistant.app',
    )
    coll = app
else:
    coll = COLLECT(
        exe,
        analysis.binaries,
        analysis.zipfiles,
        analysis.datas,
        strip=False,
        upx=False,
        name='ExcelAssistant',
    )

# Post-collect: ensure bootloader expected path Contents/MacOS/_internal/Python
# exists by copying the packaged Frameworks/Python into that path. This helps
# when the bootloader looks for ./_internal/Python at runtime.
if sys.platform == 'darwin':
    try:
        import shutil
        dist_app = os.path.join(base_dir, 'dist', 'ExcelAssistant.app')
        macos_internal = os.path.join(dist_app, 'Contents', 'MacOS', '_internal')
        src_frameworks_python = os.path.join(dist_app, 'Contents', 'Frameworks', 'Python')
        # If Python exists under Frameworks, copy it to MacOS/_internal/Python
        if os.path.exists(src_frameworks_python):
            os.makedirs(macos_internal, exist_ok=True)
            dst = os.path.join(macos_internal, 'Python')
            if os.path.isdir(src_frameworks_python):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src_frameworks_python, dst)
            else:
                shutil.copy2(src_frameworks_python, dst)
    except Exception as e:
        print('Warning: failed to populate MacOS/_internal:', e)
