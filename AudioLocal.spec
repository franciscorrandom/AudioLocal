from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
analysis = Analysis(
    [str(root / "src" / "bundle_entry.py")],
    pathex=[str(root / "src")],
    binaries=[(str(root / "tools" / name), "tools") for name in ("ffmpeg", "node")],
    # Preserve the official universal onefile executable and its appended archive.
    datas=collect_data_files("customtkinter") + [(str(root / "licenses"), "licenses"), (str(root / "tools" / "yt-dlp_macos"), "tools")],
    hiddenimports=[],
    excludes=["yt_dlp", "yt_dlp_ejs", "imageio_ffmpeg"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="AudioLocal", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, target_arch="arm64", codesign_identity=None, entitlements_file=None, argv_emulation=False)
collection = COLLECT(executable, analysis.binaries, analysis.datas, strip=False, upx=False, name="AudioLocal")
application = BUNDLE(collection, name="AudioLocal.app", bundle_identifier="cl.guiaestudio.audiolocal", version="1.0.0", info_plist={"CFBundleShortVersionString": "1.0.0", "LSMinimumSystemVersion": "13.5", "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication"})
