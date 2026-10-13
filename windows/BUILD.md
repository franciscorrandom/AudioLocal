# AudioLocal Windows 1.0.0-beta.1

Build target: Windows 10/11 x64. The desktop app and each tool are independent
processes. The portable directory includes its own Python/Tk runtime, the
unaltered official yt-dlp 2026.08.19 executable, Node 24.14.1 and a minimal
FFmpeg 7.1 built with LAME 3.100. No browser cookies or credentials are read.

## Repeat the build

Use Windows x64 with Python 3.12.10/Tk 8.6, MSYS2 UCRT64 GCC/nasm/make and
Inno Setup 6 installed on the build machine. These are build dependencies,
never user prerequisites. GitHub Actions provisions the builder automatically.

1. `python -m pip install --require-hashes -r requirements-build.lock`
2. `./scripts/download-tools.ps1` from PowerShell.
3. `bash scripts/build-ffmpeg.sh` in MSYS2 UCRT64.
4. `python -m unittest discover -s src/tests -v`
5. `python -m PyInstaller --noconfirm --clean Windows.spec`
6. `./scripts/verify-bundle.ps1` from PowerShell.
7. `./scripts/package-release.ps1`

The workflow lives at `.github/workflows/windows.yml` in the repository root;
the files described here live under `windows/`. Push to the Windows build
branch starts CI; workflow_dispatch is also available once the workflow is on
the default branch. CI does not publish releases or modify the website.

## Verification

The packaged GUI is exercised with PATH restricted to Windows system folders.
Tests use an original generated tone, never private user audio. WAV, Opus WebM
and AAC M4A inputs convert to MP3 at 128/192/320 kbps with Unicode ID3 metadata.
Cancellation checks real Node parent/child processes, including forced timer
escalation. Windows Job Objects own descendants and kill on close; children
start suspended until assigned to their job. No console windows are created.
FFmpeg PE imports are checked to reject MSYS2 or compiler runtime dependencies.

## Corresponding sources and licenses

`Windows-Fuentes.zip` includes this application's source, build scripts,
FFmpeg/LAME/Mutagen/yt-dlp source archives, the FFmpeg configuration and LAME static
archive. Rebuilding uses only documented switches and the source tarballs.
FFmpeg and LAME are LGPL builds; no GPL or nonfree FFmpeg components enabled.
The separate official yt-dlp executable has its own third-party licenses,
including Mutagen GPL. Replacing an included executable preserves the app's
tool interface; tools are distributed independently and are not signed/locked.

Other dependency source:
- Python: https://www.python.org/downloads/release/python-31210/
- Tcl/Tk 8.6: https://www.tcl-lang.org/software/tcltk/8.6.html
- Node: https://nodejs.org/dist/v24.14.1/
- yt-dlp: https://github.com/yt-dlp/yt-dlp/tree/2026.08.19
- CustomTkinter: https://github.com/TomSchimansky/CustomTkinter/tree/v5.2.2
- PyInstaller: https://github.com/pyinstaller/pyinstaller/tree/v6.22.0

The beta is unsigned. SmartScreen behavior depends on Windows reputation and
local policies; the app does not disable or bypass those system protections.
