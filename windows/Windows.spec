from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
analysis = Analysis(
    [str(root / "src" / "bundle_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    # Official tools retain their original bytes, including yt-dlp's onefile archive.
    datas=collect_data_files("customtkinter") + [(str(root / "licenses"), "licenses")]
        + [(str(root / "tools" / filename), "tools") for filename in ("ffmpeg.exe", "node.exe", "yt-dlp.exe")],
    hiddenimports=[],
    excludes=["yt_dlp", "yt_dlp_ejs", "imageio_ffmpeg", "mutagen", "PIL"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="AudioLocal", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    version=str(root / "windows-version.txt"), uac_admin=False,
    disable_windowed_traceback=False)
collection = COLLECT(executable, analysis.binaries, analysis.datas, strip=False, upx=False, name="AudioLocal")
