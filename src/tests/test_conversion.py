"""Real FFmpeg conversion checks; generated tone, no network needed."""
import math
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mutagen.mp3 import MP3
from yt_dlp import YoutubeDL

from engine import DownloadEngine, DownloadRequest, INFO_TEMPLATE, discover_ffmpeg


class ConversionTests(unittest.TestCase):
    def test_metadata_template_with_absent_optional_fields(self):
        info = {"filepath": "/tmp/Canción.m4a", "title": 'Prueba "audio"', "uploader": "Test"}
        expected = dict(info)
        with YoutubeDL({"quiet": True}) as ydl:
            rendered = ydl.evaluate_outtmpl(INFO_TEMPLATE, info)
        self.assertEqual(json.loads(rendered), expected)

    def test_real_conversion_bitrates_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                frames = b"".join(
                    struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 48000)))
                    for i in range(60000)
                )
                audio.writeframes(frames)
            info = {
                "filepath": source, "title": "Canción de prueba", "artist": "AudioLocal",
                "album": "Pruebas", "track": "NA",
            }
            for bitrate in (128, 192, 320):
                with self.subTest(bitrate=bitrate):
                    encoded = root / f"{bitrate}.mp3"
                    engine = DownloadEngine(lambda event: None)
                    engine._convert(info, encoded, discover_ffmpeg(),
                                    DownloadRequest([], root, bitrate=bitrate))
                    mp3 = MP3(encoded)
                    self.assertAlmostEqual(mp3.info.length, 1.25, delta=0.1)
                    self.assertEqual(mp3.info.sample_rate, 44100)
                    self.assertAlmostEqual(mp3.info.bitrate, bitrate * 1000, delta=1000)
                    self.assertEqual(str(mp3.tags["TIT2"]), "Canción de prueba")
                    self.assertEqual(str(mp3.tags["TPE1"]), "AudioLocal")
                    self.assertEqual(str(mp3.tags["TALB"]), "Pruebas")

            encoded = root / "no-metadata.mp3"
            engine = DownloadEngine(lambda event: None)
            engine._convert(info, encoded, discover_ffmpeg(),
                            DownloadRequest([], root, metadata=False))
            mp3 = MP3(encoded)
            self.assertNotIn("TIT2", mp3.tags or {})
            self.assertNotIn("TPE1", mp3.tags or {})


if __name__ == "__main__":
    unittest.main()
