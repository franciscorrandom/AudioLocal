"""Offline tests: no downloads, installed packages, or FFmpeg are required."""

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import Cancelled, DownloadEngine, DownloadError, DownloadRequest, validate_url


VIDEO_ID = "BaW_jenozKc"
SECOND_ID = "abcdefghijk"
THIRD_ID = "12345678901"
CANONICAL = "https://www.youtube.com/watch?v=" + VIDEO_ID


@contextmanager
def offline_dependencies():
    """Only bypass dependency discovery; filesystem and subprocesses stay real."""
    with patch("engine.discover_ffmpeg", return_value="unused-ffmpeg"), patch(
        "engine.importlib.util.find_spec", return_value=object()
    ):
        yield


class URLTests(unittest.TestCase):
    def test_supported_video_formats_become_one_canonical_url(self):
        urls = [
            "https://www.youtube.com/watch?v=" + VIDEO_ID,
            "http://youtube.com/watch?v=" + VIDEO_ID + "&t=15",
            "https://m.youtube.com/watch?v=" + VIDEO_ID,
            "https://music.youtube.com/watch?v=" + VIDEO_ID,
            "https://youtu.be/" + VIDEO_ID + "?si=tracking",
            "https://www.youtu.be/" + VIDEO_ID,
            "https://www.youtube.com/shorts/" + VIDEO_ID,
            "https://www.youtube.com/embed/" + VIDEO_ID + "/",
            "https://www.youtube.com/live/" + VIDEO_ID,
            "  https://WWW.YOUTUBE.COM/watch?v=" + VIDEO_ID + "  ",
        ]
        for value in urls:
            with self.subTest(url=value):
                self.assertEqual(validate_url(value), CANONICAL)

    def test_playlist_parameter_keeps_only_the_individual_video(self):
        url = CANONICAL + "&list=PL_some_playlist&index=3&t=10"
        self.assertEqual(validate_url(url), CANONICAL)

    def test_unsupported_or_deceptive_links_are_rejected(self):
        urls = [
            "",
            "youtube.com/watch?v=" + VIDEO_ID,
            "ftp://www.youtube.com/watch?v=" + VIDEO_ID,
            "https://youtube.com.evil.test/watch?v=" + VIDEO_ID,
            "https://notyoutube.com/watch?v=" + VIDEO_ID,
            "https://youtube-com.test/watch?v=" + VIDEO_ID,
            "https://youtu.be.evil.test/" + VIDEO_ID,
            "https://www.youtube.com:8443/watch?v=" + VIDEO_ID,
            "https://user@www.youtube.com/watch?v=" + VIDEO_ID,
            "https://user:secret@www.youtube.com/watch?v=" + VIDEO_ID,
            "https://www.youtube.com@evil.test/watch?v=" + VIDEO_ID,
            "https://www.youtube.com/playlist?list=PL_only_playlist",
            "https://www.youtube.com/watch?list=PL_only_playlist",
            "https://youtu.be/",
            "https://youtu.be/" + VIDEO_ID + "/other",
            "https://www.youtube.com/watch?v=short",
            "https://www.youtube.com/watch?v=" + VIDEO_ID + "extra",
            "https://www.youtube.com/shorts/short",
            "https://www.youtube.com/channel/" + VIDEO_ID,
        ]
        for value in urls:
            with self.subTest(url=value):
                with self.assertRaises(DownloadError):
                    validate_url(value)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.engine = DownloadEngine(self.events.append)

    @staticmethod
    def fake_download(url, work, index, total):
        video_id = url.rsplit("=", 1)[-1]
        source = work / ("Audio [" + video_id + "].webm")
        source.write_bytes(b"downloaded-source")
        return {"filepath": source, "title": "Audio " + video_id}

    @staticmethod
    def fake_convert(info, destination, ffmpeg, request):
        destination.write_bytes(b"converted-mp3")

    def done(self):
        results = [event for event in self.events if event["type"] == "done"]
        self.assertEqual(len(results), 1)
        self.assertIs(self.events[-1], results[0])
        return results[0]

    def test_canonical_duplicates_are_downloaded_once(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            request = DownloadRequest(
                [CANONICAL, "https://youtu.be/" + VIDEO_ID,
                 CANONICAL + "&list=PL_tracking", "https://www.youtube.com/embed/" + VIDEO_ID],
                output,
            )
            with offline_dependencies(), patch.object(
                self.engine, "_download", side_effect=self.fake_download
            ) as download, patch.object(self.engine, "_convert", side_effect=self.fake_convert):
                self.engine.run(request)
            self.assertEqual(download.call_count, 1)
            self.assertEqual(download.call_args.args[0], CANONICAL)
            self.assertEqual(len(list(output.glob("*.mp3"))), 1)
            self.assertEqual(self.done(), {
                "type": "done", "completed": 1, "total": 1,
                "failed": 0, "cancelled": False,
            })

    def test_one_failed_link_does_not_stop_the_following_links(self):
        def download(url, work, index, total):
            if url.endswith(SECOND_ID):
                raise DownloadError("El vídeo no está disponible.")
            return self.fake_download(url, work, index, total)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            request = DownloadRequest(
                [CANONICAL, "https://youtu.be/" + SECOND_ID, "https://youtu.be/" + THIRD_ID],
                output,
            )
            with offline_dependencies(), patch.object(
                self.engine, "_download", side_effect=download
            ) as download_mock, patch.object(self.engine, "_convert", side_effect=self.fake_convert):
                self.engine.run(request)
            self.assertEqual(download_mock.call_count, 3)
            self.assertEqual(len(list(output.glob("*.mp3"))), 2)
            self.assertFalse(list(output.glob(".audiolocal-*")))
            errors = [event for event in self.events if event["type"] == "error"]
            self.assertEqual(len(errors), 1)
            self.assertIn("Enlace 2", errors[0]["message"])
            self.assertEqual(len([e for e in self.events if e["type"] == "file"]), 2)
            self.assertEqual([e for e in self.events if e["type"] == "progress"][-1]["percent"], 100)
            self.assertEqual(self.done(), {
                "type": "done", "completed": 2, "total": 3,
                "failed": 1, "cancelled": False,
            })

    def test_cancel_before_start_does_not_create_output_or_start_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-created"
            self.engine.cancel()
            with patch.object(self.engine, "_download") as download, patch(
                "engine.discover_ffmpeg"
            ) as ffmpeg:
                self.engine.run(DownloadRequest([CANONICAL], output))
            download.assert_not_called()
            ffmpeg.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(self.done(), {
                "type": "done", "completed": 0, "total": 1,
                "failed": 0, "cancelled": True,
            })

    def test_cancelled_download_cleans_partial_files_and_keeps_finished_mp3s(self):
        def download(url, work, index, total):
            (work / "unfinished.webm.part").write_bytes(b"unfinished")
            self.engine.cancel()
            return self.fake_download(url, work, index, total)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            previous = output / "existing.mp3"
            previous.write_bytes(b"keep-this-recording")
            with offline_dependencies(), patch.object(
                self.engine, "_download", side_effect=download
            ), patch.object(self.engine, "_convert") as convert:
                self.engine.run(DownloadRequest([CANONICAL], output))
            convert.assert_not_called()
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(previous.read_bytes(), b"keep-this-recording")
            self.assertTrue(self.done()["cancelled"])
            self.assertEqual(self.done()["completed"], 0)


class SaveTests(unittest.TestCase):
    def test_existing_mp3_is_preserved_and_new_files_get_unique_names(self):
        engine = DownloadEngine(lambda event: None)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "output"
            output.mkdir()
            previous = output / "song.mp3"
            previous.write_bytes(b"previous-recording")
            encoded = base / "encoded.mp3"
            encoded.write_bytes(b"new-recording")
            first = engine._save(encoded, base / "song.webm", output)
            second = engine._save(encoded, base / "song.webm", output)
            self.assertEqual(first.name, "song (2).mp3")
            self.assertEqual(second.name, "song (3).mp3")
            self.assertEqual(previous.read_bytes(), b"previous-recording")
            self.assertEqual(first.read_bytes(), b"new-recording")
            self.assertEqual(second.read_bytes(), b"new-recording")

    def test_cancellation_during_save_removes_only_the_partial_new_mp3(self):
        engine = DownloadEngine(lambda event: None)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "output"
            output.mkdir()
            previous = output / "song.mp3"
            previous.write_bytes(b"previous-recording")
            encoded = base / "encoded.mp3"
            encoded.write_bytes(b"x" * (3 * 1024 * 1024))
            partial = output / "song (2).mp3"
            check_cancelled = engine._check_cancelled

            def cancel_when_writing_has_started():
                if partial.exists() and partial.stat().st_size:
                    engine.cancel()
                check_cancelled()

            with patch.object(engine, "_check_cancelled", side_effect=cancel_when_writing_has_started):
                with self.assertRaises(Cancelled):
                    engine._save(encoded, base / "song.webm", output)
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(previous.read_bytes(), b"previous-recording")
            self.assertTrue(encoded.exists())


class SubprocessTests(unittest.TestCase):
    def test_process_failure_keeps_the_actionable_error(self):
        engine = DownloadEngine(lambda event: None)
        with self.assertRaisesRegex(DownloadError, "ERROR: useful failure"):
            engine._execute([
                sys.executable, "-u", "-c",
                "import sys; print('context'); print('ERROR: useful failure'); sys.exit(7)",
            ])
        self.assertIsNone(engine._process)

    def assert_subprocess_can_be_cancelled(self, ignore_sigterm=False):
        engine = DownloadEngine(lambda event: None)
        ready = threading.Event()
        errors = []
        script = "import time; print('ready', flush=True); time.sleep(10)"
        if ignore_sigterm:
            script = "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); " + script

        def run_child():
            try:
                engine._execute(
                    [sys.executable, "-u", "-c", script],
                    on_line=lambda line: ready.set() if line == "ready" else None,
                )
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=run_child, daemon=True)
        worker.start()
        process = None
        try:
            self.assertTrue(ready.wait(timeout=3), "The local test subprocess did not start.")
            process = engine._process
            cancelled_at = time.monotonic()
            engine.cancel()
            worker.join(timeout=3.5)
            elapsed = time.monotonic() - cancelled_at
            self.assertFalse(worker.is_alive(), "Cancellation left the subprocess reader blocked.")
            self.assertLess(elapsed, 4)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], Cancelled)
            self.assertIsNone(engine._process)
            self.assertIsNotNone(process)
            self.assertIsNotNone(process.poll())
        finally:
            engine.cancel()
            process = process or engine._process
            if process is not None and process.poll() is None:
                process.kill()
            worker.join(timeout=1)

    def test_cancel_stops_a_sleeping_subprocess(self):
        self.assert_subprocess_can_be_cancelled()

    @unittest.skipUnless(os.name == "posix", "SIGTERM handling is a POSIX test.")
    def test_cancel_stops_a_subprocess_that_ignores_sigterm(self):
        self.assert_subprocess_can_be_cancelled(ignore_sigterm=True)

    @unittest.skipUnless(os.name == "posix", "SIGTERM handling is a POSIX test.")
    def test_cancel_while_child_is_starting_cannot_leave_a_blocked_reader(self):
        engine = DownloadEngine(lambda event: None)
        started = threading.Event()
        created = []
        errors = []
        real_popen = subprocess.Popen
        script = (
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(10)"
        )

        def start_and_cancel(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            created.append(process)
            self.assertEqual(process.stdout.readline().strip(), "ready")
            # Reproduce cancellation after spawn, before _execute registers its child.
            engine.cancel()
            started.set()
            return process

        def run_child():
            try:
                engine._execute([sys.executable, "-u", "-c", script])
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=run_child, daemon=True)
        with patch("engine.subprocess.Popen", side_effect=start_and_cancel):
            worker.start()
            try:
                self.assertTrue(started.wait(timeout=3))
                cancelled_at = time.monotonic()
                worker.join(timeout=3.5)
                self.assertFalse(worker.is_alive(), "The startup cancellation race blocked stdout.")
                self.assertLess(time.monotonic() - cancelled_at, 4)
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], Cancelled)
                self.assertIsNone(engine._process)
            finally:
                engine.cancel()
                for process in created:
                    if process.poll() is None:
                        process.kill()
                worker.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
