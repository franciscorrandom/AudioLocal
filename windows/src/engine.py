"""Local download and conversion engine. No browser sessions are accessed."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

from windows_support import WindowsJob


INFO_TEMPLATE = "%(.{filepath,title,artist,uploader,track,album})j"
_SPAWN_LOCK = threading.Lock()


@contextmanager
def clean_dll_search():
    """External bundled tools must load their own DLLs, not our Python DLLs."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.restype = ctypes.c_int
    with _SPAWN_LOCK:
        if not kernel.SetDllDirectoryW(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            kernel.SetDllDirectoryW(str(sys._MEIPASS))


class DownloadError(Exception):
    """An error that can be shown directly in the interface."""


class Cancelled(DownloadError):
    pass


@dataclass
class DownloadRequest:
    urls: list[str]
    output_dir: Path
    bitrate: int = 192
    metadata: bool = True


def validate_url(value: str) -> str:
    """Accept individual YouTube videos, never arbitrary hosts or playlists."""
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
        raise DownloadError("Pega un enlace completo de YouTube, con https://.")
    if parsed.netloc.lower() not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
        "youtu.be", "www.youtu.be",
    }:
        raise DownloadError("Solo se aceptan enlaces de videos de YouTube.")
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/")
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    else:
        match = re.fullmatch(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})/?", parsed.path)
        video_id = match.group(1) if match else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise DownloadError("Ese enlace no identifica un video. Pega su enlace individual.")
    # A canonical URL removes tracking parameters and accidental playlist downloads.
    return "https://www.youtube.com/watch?v=" + video_id


def bundled_tool(name: str) -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    filename = "yt-dlp.exe" if name == "yt-dlp" else name + ".exe" if os.name == "nt" else name
    candidate = root / "tools" / filename
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    raise DownloadError(f"La aplicación está incompleta: falta {name}. Vuelve a descargar AudioLocal.")


def discover_ffmpeg() -> str:
    packaged = bundled_tool("ffmpeg")
    if packaged:
        return packaged
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    try:
        import imageio_ffmpeg
        binary = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(binary).is_file():
            return binary
    except (ImportError, RuntimeError, OSError):
        pass
    raise DownloadError("Falta FFmpeg. Instala las dependencias de requirements.txt y vuelve a abrir AudioLocal.")


class DownloadEngine:
    def __init__(self, on_event: Callable[[dict], None]):
        self.on_event = on_event
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._running = False

    def _emit(self, kind: str, **fields):
        self.on_event({"type": kind, **fields})

    def cancel(self):
        """Stop only the child process started by this instance."""
        self._cancel.set()
        with self._lock:
            process = self._process
            if process is not None and (getattr(process, "_audiolocal_job", None) or process.poll() is None):
                self._terminate(process)
                # A child may ignore SIGTERM while our reader is waiting for output.
                # Escalate independently so cancellation does not depend on that reader.
                killer = threading.Timer(2.0, self._force_stop, args=(process,))
                killer.daemon = True
                killer.start()

    @staticmethod
    def _force_stop(process):
        job = getattr(process, "_audiolocal_job", None)
        if job:
            job.terminate()
            return
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                job = getattr(process, "_audiolocal_job", None)
                job.terminate() if job else process.kill()
        except (ProcessLookupError, OSError):
            pass

    @staticmethod
    def _terminate(process):
        job = getattr(process, "_audiolocal_job", None)
        if job:
            job.terminate()
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (ProcessLookupError, OSError):
            pass

    def _check_cancelled(self):
        if self._cancel.is_set():
            raise Cancelled("Descarga cancelada. Los MP3 ya terminados se conservan.")

    def _execute(self, args: list[str], on_line=None):
        self._check_cancelled()
        # Assign the job before the child runs, so even early onefile/runtime children belong to it.
        options = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NO_WINDOW | 0x00000004}  # CREATE_SUSPENDED
        child_environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        with clean_dll_search():
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                env=child_environment, **options,
            )
        job = None
        if os.name == "nt":
            try:
                job = WindowsJob()
                job.assign(process)
                process._audiolocal_job = job
                job.resume(process)
            except OSError as exc:
                process.kill()
                process.wait(timeout=3)
                if process.stdout:
                    process.stdout.close()
                if job:
                    job.close()
                raise DownloadError("Windows no permitió iniciar el proceso de descarga. Vuelve a abrir AudioLocal.") from exc
        with self._lock:
            self._process = process
            if self._cancel.is_set():
                self._terminate(process)
                killer = threading.Timer(2.0, self._force_stop, args=(process,))
                killer.daemon = True
                killer.start()
        recent = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                if line:
                    recent.append(line)
                    recent = recent[-12:]
                    if on_line:
                        on_line(line)
                self._check_cancelled()
            code = process.wait()
            self._check_cancelled()
            if code != 0:
                reason = next((x for x in reversed(recent) if "ERROR:" in x), "")
                if not reason:
                    reason = " ".join(recent[-3:]) or f"El proceso terminó con código {code}."
                raise DownloadError(reason[:1200])
        finally:
            if process.poll() is None:
                self._terminate(process)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        self._force_stop(process)
                    process.wait(timeout=3)
            if process.stdout:
                process.stdout.close()
            if job:
                job.close()
            with self._lock:
                if self._process is process:
                    self._process = None

    def _download(self, url: str, work: Path, index: int, total: int) -> dict:
        result = {}
        marker = "__AUDIOLOCAL_INFO__"
        progress_marker = "__AUDIOLOCAL_PROGRESS__"

        def on_line(line):
            if line.startswith(marker):
                try:
                    result.update(json.loads(line[len(marker):]))
                except ValueError as exc:
                    raise DownloadError("No se pudo leer la información del audio descargado.") from exc
            elif line.startswith(progress_marker):
                numbers = re.search(r"([\d.]+)%", line[len(progress_marker):])
                if numbers:
                    local = min(float(numbers.group(1)), 100) / 100
                    self._emit("progress", percent=100 * (index + 0.85 * local) / total)
            elif line.startswith("WARNING:"):
                self._emit("status", message=line[:600])

        command = [bundled_tool("yt-dlp")] if getattr(sys, "frozen", False) else [sys.executable, "-m", "yt_dlp"]
        args = command + [
            "--ignore-config", "--no-plugin-dirs", "--no-cache-dir",
            "--no-playlist", "--no-colors", "--newline", "--progress",
            "--windows-filenames", "--no-js-runtimes",
            "--no-simulate", "--socket-timeout", "15", "--retries", "2",
            "--fragment-retries", "2", "--extractor-retries", "2",
            "--format", "bestaudio/best", "--max-filesize", "1G",
            "--paths", str(work), "--output", "%(title).150B [%(id)s].%(ext)s",
            "--progress-template", "download:" + progress_marker + "%(progress._percent_str)s",
            "--print", "after_move:" + marker + INFO_TEMPLATE,
        ]
        node = bundled_tool("node") or shutil.which("node")
        if node:
            args.extend(["--js-runtimes", "node:" + node])
        args.extend(["--", url])
        self._execute(args, on_line)
        if not result.get("filepath"):
            raise DownloadError("YouTube no devolvió un archivo de audio descargable.")
        source = Path(result["filepath"]).resolve()
        if not source.is_file() or not source.is_relative_to(work.resolve()):
            raise DownloadError("El archivo descargado no se encuentra en la carpeta temporal.")
        result["filepath"] = source
        return result

    def _convert(self, info: dict, destination: Path, ffmpeg: str, request: DownloadRequest):
        args = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(info["filepath"]), "-map", "0:a:0", "-vn",
            "-map_metadata", "-1", "-c:a", "libmp3lame", "-b:a", f"{request.bitrate}k",
            "-ar", "44100", "-id3v2_version", "3",
        ]
        if request.metadata:
            for tag, choices in {
                "title": [info.get("track"), info.get("title")],
                "artist": [info.get("artist"), info.get("uploader")],
                "album": [info.get("album")],
            }.items():
                value = next((str(x) for x in choices if x and x != "NA"), "")
                if value:
                    args.extend(["-metadata", tag + "=" + value])
        args.append(str(destination))
        self._execute(args)
        if not destination.is_file() or not destination.stat().st_size:
            raise DownloadError("FFmpeg no pudo generar el MP3.")

    def _save(self, encoded: Path, original: Path, output: Path) -> Path:
        stem = original.stem
        for number in range(1, 10001):
            candidate = output / (stem + (f" ({number})" if number > 1 else "") + ".mp3")
            try:
                target = candidate.open("xb")
            except FileExistsError:
                continue
            try:
                with target, encoded.open("rb") as source:
                    while data := source.read(1024 * 1024):
                        self._check_cancelled()
                        target.write(data)
            except BaseException:
                candidate.unlink(missing_ok=True)
                raise
            return candidate
        raise DownloadError("Hay demasiados archivos con el mismo nombre en esa carpeta.")

    def run(self, request: DownloadRequest):
        with self._lock:
            if self._running:
                raise DownloadError("Ya hay una descarga en curso.")
            self._running = True
        completed = failed = 0
        total = len(request.urls)
        cancelled = False
        try:
            self._check_cancelled()
            if not request.urls:
                raise DownloadError("Agrega al menos un enlace de YouTube.")
            if request.bitrate not in {128, 192, 320}:
                raise DownloadError("La calidad debe ser 128, 192 o 320 kbps.")
            urls = list(dict.fromkeys(validate_url(value) for value in request.urls))
            total = len(urls)
            output = Path(request.output_dir).expanduser().resolve()
            output.mkdir(parents=True, exist_ok=True)
            ffmpeg = discover_ffmpeg()
            if not getattr(sys, "frozen", False) and importlib.util.find_spec("yt_dlp") is None:
                raise DownloadError("Falta yt-dlp. Instala las dependencias de requirements.txt y vuelve a abrir AudioLocal.")
            for index, url in enumerate(urls):
                self._check_cancelled()
                self._emit("status", message=f"Descargando audio {index + 1} de {total}…")
                try:
                    with tempfile.TemporaryDirectory(prefix=".audiolocal-", dir=output) as temp:
                        work = Path(temp)
                        info = self._download(url, work, index, total)
                        self._check_cancelled()
                        self._emit("status", message=f"Convirtiendo a MP3: {info.get('title', 'audio')}…")
                        encoded = work / "converted.mp3"
                        self._convert(info, encoded, ffmpeg, request)
                        self._check_cancelled()
                        saved = self._save(encoded, info["filepath"], output)
                    completed += 1
                    self._emit("file", path=str(saved), message=saved.name)
                except Cancelled:
                    raise
                except (DownloadError, OSError) as exc:
                    failed += 1
                    self._emit("error", message=f"Enlace {index + 1}: {exc}")
                self._emit("progress", percent=100 * (index + 1) / total)
        except Cancelled as exc:
            cancelled = True
            self._emit("status", message=str(exc))
        except (DownloadError, OSError) as exc:
            failed = max(failed, total - completed)
            self._emit("error", message=str(exc))
        except Exception as exc:
            failed = max(failed, total - completed)
            self._emit("error", message=f"No se pudo completar la descarga: {exc}")
        finally:
            with self._lock:
                self._running = False
            self._emit("done", completed=completed, total=total, failed=failed, cancelled=cancelled)
