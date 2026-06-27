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
        bundle_identifier='com.biaoge.excelassistant',
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
