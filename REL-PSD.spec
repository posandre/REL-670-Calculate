# -*- mode: python ; coding: utf-8 -*-


def exclude_qt_entry(entry):
    name = entry[0].replace('/', '\\')
    excluded_prefixes = (
        'PySide6\\plugins\\platforminputcontexts\\qtvirtualkeyboardplugin',
        'PySide6\\plugins\\platforms\\qdirect2d',
        'PySide6\\plugins\\platforms\\qminimal',
        'PySide6\\plugins\\platforms\\qoffscreen',
        'PySide6\\plugins\\imageformats\\qpdf',
        'PySide6\\plugins\\imageformats\\qicns',
        'PySide6\\plugins\\imageformats\\qtga',
        'PySide6\\plugins\\imageformats\\qgif',
        'PySide6\\plugins\\imageformats\\qwbmp',
        'PySide6\\plugins\\imageformats\\qwebp',
        'PySide6\\plugins\\imageformats\\qtiff',
        'PySide6\\opengl32sw',
        'PySide6\\Qt6Pdf',
        'PySide6\\Qt6VirtualKeyboard',
        'PySide6\\Qt6Quick',
        'PySide6\\Qt6Qml',
        'PIL\\_avif',
        'PIL\\_webp',
        'PIL\\_imagingtk',
    )
    return name.startswith(excluded_prefixes)


a = Analysis(
    ['src\\app\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('resources', 'resources'),
        ('src/app/localization/translations', 'app/localization/translations'),
        ('src/app/ui/styles/app.qss', 'app/ui/styles'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'black',
        'mypy',
        'pytest',
        'ruff',
        'tkinter',
        'numpy.testing',
        'PIL.AvifImagePlugin',
        'PIL.FpxImagePlugin',
        'PIL.ImageTk',
        'PIL.MicImagePlugin',
        'PIL.WebPImagePlugin',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_webagg',
        'PySide6.QtPdf',
        'PySide6.QtQuick',
        'PySide6.QtQml',
        'PySide6.QtVirtualKeyboard',
    ],
    noarchive=False,
    optimize=1,
)
a.binaries = [entry for entry in a.binaries if not exclude_qt_entry(entry)]
a.datas = [entry for entry in a.datas if not exclude_qt_entry(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='REL-PSD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources\\app_icon.ico'],
)
