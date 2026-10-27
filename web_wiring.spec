# -*- mode: python ; coding: utf-8 -*-

# Prevent Windows Defender / Antivirus file lock from failing the build on PE checksum update
try:
    import PyInstaller.utils.win32.winutils as winutils
    orig_update = winutils.update_exe_pe_checksum
    def safe_update_exe_pe_checksum(exe_path):
        try:
            return orig_update(exe_path)
        except Exception as e:
            print(f"[NOTE] Skipped PE checksum update ({e}); not required for user-mode applications.")
    winutils.update_exe_pe_checksum = safe_update_exe_pe_checksum
except Exception:
    pass

a = Analysis(
    ['web_wiring.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'paho.mqtt.client',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'cv2',
        'numpy',
        'flask',
        'jinja2',
        'werkzeug',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchvision',
        'torchaudio',
        'ultralytics',
        'matplotlib',
        'scipy',
        'IPython',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide6',
        'pandas',
        'mock_pms_server',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='web_wiring',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
