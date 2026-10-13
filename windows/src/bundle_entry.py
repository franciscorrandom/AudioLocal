"""Desktop entry point and explicit offline verification of the Windows bundle."""
from __future__ import annotations

import os
import sys

# PyInstaller windowed builds have no console streams. Libraries may still log.
for stream in ("stdout", "stderr"):
    if getattr(sys, stream) is None:
        setattr(sys, stream, open(os.devnull, "w", encoding="utf-8"))

import ctypes
from ctypes import wintypes
import json
import math
from pathlib import Path
import struct
import shutil
import re
import tempfile
import threading
import time
import traceback
import wave
from unittest.mock import patch

from engine import Cancelled, DownloadEngine, DownloadRequest, bundled_tool, discover_ffmpeg


def windows_pid_alive(pid: int) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        result = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(result))) and result.value == 259
    finally:
        kernel.CloseHandle(handle)


def execute_output(arguments):
    output = []
    DownloadEngine(lambda event: None)._execute(arguments, output.append)
    return "\n".join(output)


def verify_package(destination: Path, fixture_directory: Path):
    assert os.name == "nt", "This verification must run on Windows"
    assert getattr(sys, "frozen", False), "Verify the actual packaged executable"
    report = {"version": "1.0.0-beta.1", "platform": "windows-x64", "frozen": True}
    paths = {name: bundled_tool(name) for name in ("ffmpeg", "node", "yt-dlp")}
    bundle_root = Path(sys._MEIPASS).resolve()
    assert all(Path(value).resolve().is_relative_to(bundle_root) for value in paths.values())
    report["tools_resolved_inside_bundle"] = True
    report["tool_versions"] = {
        name: execute_output([path, "-version" if name == "ffmpeg" else "--version"]).splitlines()[0]
        for name, path in paths.items()
    }
    assert report["tool_versions"]["node"] == "v24.14.1"
    assert report["tool_versions"]["yt-dlp"] == "2026.08.19"
    assert "--enable-gpl" not in execute_output([paths["ffmpeg"], "-buildconf"])
    assert "--enable-nonfree" not in execute_output([paths["ffmpeg"], "-buildconf"])
    conversions = []
    with tempfile.TemporaryDirectory(prefix="audiolocal-verify-") as directory:
        work = Path(directory)
        original = work / "Canción de prueba.wav"
        with wave.open(str(original), "wb") as audio:
            audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 48000))) for i in range(60000)))
        fixtures = {"wav": original, "opus": work / "Canción.webm", "aac": work / "Canción.m4a"}
        shutil.copyfile(fixture_directory / "signal-opus.webm", fixtures["opus"])
        shutil.copyfile(fixture_directory / "signal-aac.m4a", fixtures["aac"])
        for format_name, fixture in fixtures.items():
            for bitrate in (128, 192, 320):
                encoded = work / f"{format_name}-{bitrate}.mp3"
                decoded = work / "decoded.wav"
                engine = DownloadEngine(lambda event: None)
                engine._convert({"filepath": fixture, "title": "Canción de prueba", "artist": "AudioLocal"}, encoded, paths["ffmpeg"], DownloadRequest([], work, bitrate=bitrate))
                description = execute_output([paths["ffmpeg"], "-hide_banner", "-loglevel", "info", "-y", "-i", str(encoded), "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(decoded)])
                actual_bitrate = re.search(r"Audio: mp3[^\n]*?, (\d+) kb/s", description)
                assert actual_bitrate and int(actual_bitrate.group(1)) == bitrate, description
                with wave.open(str(decoded), "rb") as waveform:
                    seconds = waveform.getnframes() / waveform.getframerate()
                    samples = waveform.readframes(waveform.getnframes())
                assert abs(seconds - 1.25) < 0.15, (format_name, bitrate, seconds)
                assert any(samples), "The converted MP3 is silent"
                assert b"TIT2" in encoded.read_bytes()
                assert "Canción de prueba".encode("utf-16") in encoded.read_bytes(), "Unicode title was not preserved"
                conversions.append({"input": format_name, "bitrate": bitrate, "duration_seconds": round(seconds, 4), "bytes": encoded.stat().st_size})
        encoded = work / "without-metadata.mp3"
        DownloadEngine(lambda event: None)._convert({"filepath": original, "title": "Hidden"}, encoded, paths["ffmpeg"], DownloadRequest([], work, metadata=False))
        assert b"TIT2" not in encoded.read_bytes()
    report["conversions"] = conversions

    cancellations = []
    for mode in ("normal", "forced", "orphan", "startup"):
        forced = mode == "forced"
        engine = DownloadEngine(lambda event: None)
        ready = threading.Event()
        child_pids = {}
        spawned = []
        errors = []
        # A child inherits the stdout pipe. Killing only its parent would block the reader.
        script = "const{spawn}=require('child_process');const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:['ignore','inherit','inherit'],windowsHide:true});console.log(JSON.stringify({parent:process.pid,child:child.pid}));setInterval(()=>{},1000);"
        if mode == "orphan":
            script += "setTimeout(()=>process.exit(0),80);"
        def line_received(line):
            child_pids.update(json.loads(line))
            ready.set()
        def run_child():
            try:
                engine._execute([paths["node"], "-e", script], line_received)
            except Exception as error:
                errors.append(error)
        if forced:
            engine._terminate = lambda process: None  # Exercise the timer escalation against real Windows processes.
        from windows_support import WindowsJob
        resume = WindowsJob.resume
        def resume_then_cancel(job, process):
            resume(job, process)
            # Reproduce cancellation after the job owns parent/child but before
            # _execute registers its process. The real pipe and processes remain.
            line = process.stdout.readline().strip()
            spawned.append(process)
            line_received(line)
            engine.cancel()
        worker = threading.Thread(target=run_child, daemon=True)
        started = time.monotonic()
        with patch.object(WindowsJob, "resume", resume_then_cancel) if mode == "startup" else patch.object(WindowsJob, "resume", resume):
            worker.start()
            assert ready.wait(10), "Node parent/child did not start"
            process = spawned[0] if mode == "startup" else engine._process
            if mode == "orphan":
                deadline = time.monotonic() + 5
                while windows_pid_alive(child_pids["parent"]) and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert not windows_pid_alive(child_pids["parent"]), "The orphan test parent did not exit"
                assert windows_pid_alive(child_pids["child"]), "The orphan test did not leave a live child"
            elif mode != "startup":
                assert windows_pid_alive(child_pids["parent"]) and windows_pid_alive(child_pids["child"])
            if mode != "startup":
                started = time.monotonic()
                engine.cancel()
            worker.join(6)
        assert not worker.is_alive(), "Cancellation blocked the subprocess reader"
        assert len(errors) == 1 and isinstance(errors[0], Cancelled), errors
        assert process.poll() is not None and engine._process is None
        assert not windows_pid_alive(child_pids["parent"]), "Parent survived cancellation"
        assert not windows_pid_alive(child_pids["child"]), "Child survived cancellation"
        seconds = time.monotonic() - started
        if forced:
            assert seconds >= 1.8, "The force-stop timer was not exercised"
        cancellations.append({"mode": mode, "forced_timer": forced, "process_tree_terminated": True, "seconds": round(seconds, 3)})
    report["cancellations"] = cancellations

    from app import AudioLocalApp, DEFAULT_OUTPUT_DIRECTORY
    from windows_support import downloads_directory
    import customtkinter as ctk
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    application = AudioLocalApp()
    application.update()
    assert Path(application.output_directory.get()) == downloads_directory() / "AudioLocal"
    application._start_download()
    assert not application._running
    application._set_running(True)
    assert application.download_button.cget("state") == "disabled"
    application._set_running(False)
    report["ui"] = {"window": application.title(), "width": application.winfo_width(), "height": application.winfo_height(), "native_downloads_folder": True, "blank_input_rejected": True, "controls_disabled_during_work": True}
    destination.with_name("gui-ready.json").write_text(json.dumps({"pid": os.getpid(), "title": application.title()}), encoding="utf-8")
    application.after(5000, application.destroy)
    application.mainloop()
    report["passed"] = True
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--verify-package" and sys.argv[3] == "--fixtures":
        destination = Path(sys.argv[2]).resolve()
        try:
            verify_package(destination, Path(sys.argv[4]).resolve())
        except BaseException:
            destination.write_text(json.dumps({"passed": False, "error": traceback.format_exc()}, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
    else:
        from app import main
        main()
