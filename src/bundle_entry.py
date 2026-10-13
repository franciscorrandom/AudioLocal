"""Application entry point and an explicit, offline package verification mode."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

from engine import Cancelled, DownloadEngine, DownloadRequest, bundled_tool, discover_ffmpeg


def verify_package(destination: Path) -> None:
    report = {"version": "1.0.0", "frozen": bool(getattr(sys, "frozen", False)), "path": os.environ.get("PATH", "")}
    tools = {name: bundled_tool(name) for name in ("ffmpeg", "node", "yt-dlp_macos")}
    report["tools"] = tools
    versions = {}
    for name, path in tools.items():
        result = subprocess.run([path, "-version" if name == "ffmpeg" else "--version"], capture_output=True, text=True, check=True)
        versions[name] = result.stdout.splitlines()[0]
    report["tool_versions"] = versions
    with tempfile.TemporaryDirectory(prefix="audiolocal-verify-") as temporary:
        work = Path(temporary)
        original = work / "test.wav"
        with wave.open(str(original), "wb") as audio:
            audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 48000))) for i in range(60000)))
        conversions = []
        for bitrate in (128, 192, 320):
            encoded = work / f"test-{bitrate}.mp3"
            DownloadEngine(lambda event: None)._convert({"filepath": original, "title": "AudioLocal test", "artist": "AudioLocal"}, encoded, discover_ffmpeg(), DownloadRequest([], work, bitrate=bitrate))
            decoded = subprocess.run([discover_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(encoded), "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], capture_output=True, check=True)
            import io
            with wave.open(io.BytesIO(decoded.stdout), "rb") as waveform:
                # Pipe WAV uses an unknown-size RIFF header, so count returned samples.
                samples = waveform.readframes(100000)
                seconds = len(samples) / (2 * waveform.getframerate())
                assert abs(seconds - 1.25) < 0.08, seconds
            assert b"TIT2" in encoded.read_bytes()
            conversions.append({"bitrate": bitrate, "duration_seconds": round(seconds, 4), "bytes": encoded.stat().st_size})
        report["conversions"] = conversions
    cancellations = []
    for ignore_term in (False, True):
        engine = DownloadEngine(lambda event: None)
        ready = threading.Event()
        errors = []
        script = "console.log('ready'); setInterval(()=>{},1000);"
        if ignore_term:
            script = "process.on('SIGTERM',()=>{});" + script
        def child():
            try:
                engine._execute([tools["node"], "-e", script], lambda line: ready.set() if line == "ready" else None)
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=child)
        worker.start()
        assert ready.wait(5), "Node child did not start"
        process = engine._process
        began = time.monotonic()
        engine.cancel()
        worker.join(5)
        assert not worker.is_alive(), "Cancellation blocked"
        assert len(errors) == 1 and isinstance(errors[0], Cancelled)
        assert process.poll() is not None and engine._process is None
        cancellations.append({"ignores_sigterm": ignore_term, "seconds": round(time.monotonic() - began, 3)})
    report["cancellations"] = cancellations
    from app import AudioLocalApp, DEFAULT_OUTPUT_DIRECTORY
    import customtkinter as ctk
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    application = AudioLocalApp()
    application.update()
    assert Path(application.output_directory.get()) == Path.home() / "Downloads" / "AudioLocal"
    application._start_download()
    assert not application._running
    application._set_running(True)
    assert application.download_button.cget("state") == "disabled"
    application._set_running(False)
    report["ui"] = {"window": application.title(), "width": application.winfo_width(), "height": application.winfo_height(), "default_output": str(DEFAULT_OUTPUT_DIRECTORY), "blank_input_rejected": True, "controls_disabled_during_work": True}
    application.after(800, application.destroy)
    application.mainloop()
    report["passed"] = True
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-package":
        verify_package(Path(sys.argv[2]).resolve())
    else:
        from app import main
        main()
