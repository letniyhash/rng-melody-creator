import os
import sys
import time
import unittest
import wave
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from audio import SAMPLE_RATES, save_copy, wav_duration, write_wav
from generators import CUSTOM_SEED, MODES, SYSTEM_RANDOM, TIME_SEED
from melody import MAX_LEAP, generate_melody
from music_theory import SCALES, TRANSITIONS, transition_table
from statistics_report import build_report


UNICODE_SEED = "  БРАТУХА 42! — 音楽 🎵  "


class EngineTests(unittest.TestCase):
    def test_all_sources(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                track = generate_melody(mode, 6, 16, UNICODE_SEED if mode == CUSTOM_SEED else None)
                self.assertGreater(len(track.notes), 3)
                self.assertIn(track.scale, SCALES)
                if mode == SYSTEM_RANDOM:
                    self.assertIsNone(track.seed)
                    self.assertIn("невоспроизводим", build_report(track, 6))

    def test_custom_seed_and_report_reproducibility(self):
        first = generate_melody(CUSTOM_SEED, 6.5, 8, UNICODE_SEED)
        second = generate_melody(CUSTOM_SEED, 6.5, 8, UNICODE_SEED)
        self.assertEqual(first.seed, UNICODE_SEED)
        self.assertEqual(first, second)
        self.assertEqual(build_report(first, 6.5), build_report(second, 6.5))
        self.assertNotEqual(first.notes, generate_melody(CUSTOM_SEED, 6.5, 8, UNICODE_SEED.strip()).notes)
        self.assertNotEqual(first.notes, generate_melody(CUSTOM_SEED, 6.5, 8, "другой").notes)

    def test_empty_seed(self):
        for seed in ("", " \t ", None):
            with self.assertRaisesRegex(ValueError, "Введите seed"):
                generate_melody(CUSTOM_SEED, 5, 8, seed)

    def test_time_seed_replay(self):
        first = generate_melody(TIME_SEED, 5, 8)
        self.assertIsInstance(first.seed, int)
        self.assertIn(str(first.seed), build_report(first, 5))
        self.assertEqual(first, generate_melody(TIME_SEED, 5, 8, first.seed))

    def test_system_mode_uses_secrets(self):
        with (
            patch("generators.random.Random", side_effect=AssertionError("PRNG использован")),
            patch("generators.secrets.choice", side_effect=lambda items: items[0]) as choice,
            patch("generators.secrets.randbelow", return_value=0) as below,
        ):
            track = generate_melody(SYSTEM_RANDOM, 5, 8)
        self.assertIsNone(track.seed)
        self.assertGreater(choice.call_count, 0)
        self.assertGreater(below.call_count, 0)

    def test_melody_invariants_and_motif(self):
        tonalities = set()
        varied = 0
        for index in range(600):
            duration = 5 + (index % 11) / 2
            track = generate_melody(CUSTOM_SEED, duration, 8, str(index))
            tonalities.add((track.key, track.scale))
            self.assertTrue(90 <= track.bpm <= 170)
            self.assertTrue(3 <= track.motif_length <= 5)
            pitches = [note.midi for note in track.notes]
            lengths = [note.eighths for note in track.notes]
            self.assertTrue(all(55 <= pitch <= 84 for pitch in pitches))
            self.assertTrue(all((pitch - track.key) % 12 in SCALES[track.scale] for pitch in pitches))
            self.assertTrue(all(abs(a - b) <= MAX_LEAP for a, b in zip(pitches, pitches[1:])))
            self.assertTrue(all(not a == b == c for a, b, c in zip(pitches, pitches[1:], pitches[2:])))
            self.assertTrue(all(1 <= length <= 4 for length in lengths))
            self.assertEqual(sum(lengths), round(duration * track.bpm / 30))
            if track.motif_repeat_start is not None:
                varied += 1
                start = track.motif_repeat_start
                self.assertEqual(pitches[start], pitches[0])
                self.assertNotEqual(pitches[start + track.motif_length - 1], pitches[track.motif_length - 1])
        self.assertEqual(len(tonalities), 24)
        self.assertTrue(0 < varied < 600)

    def test_matrix_weights(self):
        for row in TRANSITIONS:
            self.assertEqual(len(row), 7)
            self.assertTrue(all(weight >= 0 for weight in row))
            self.assertEqual(sum(row), 100)

    def test_pcm_and_cyrillic_save(self):
        with TemporaryDirectory() as folder:
            for bits, seconds in ((8, 5), (16, 10)):
                with self.subTest(bits=bits):
                    track = generate_melody(CUSTOM_SEED, seconds, bits, UNICODE_SEED)
                    path = Path(folder) / f"Мелодия 🎵 {bits}.wav"
                    copy = path.with_stem(path.stem + " сохранённая")
                    write_wav(track, path)
                    rate = SAMPLE_RATES[bits]
                    with wave.open(str(path), "rb") as sound:
                        self.assertEqual(sound.getparams()[:5], (2, bits // 8, rate, seconds * rate, "NONE"))
                        samples = array("B" if bits == 8 else "h", sound.readframes(seconds * rate))
                    midpoint = 128 if bits == 8 else 0
                    limit = 57 if bits == 8 else 14745
                    self.assertEqual(list(samples[:2]), [midpoint, midpoint])
                    self.assertEqual(list(samples[-2:]), [midpoint, midpoint])
                    self.assertTrue(any(left != right for left, right in zip(samples[::2], samples[1::2])))
                    peak = max(abs(sample - midpoint) for sample in samples)
                    self.assertGreater(peak, limit / 2)
                    self.assertLessEqual(peak, limit)
                    self.assertEqual(wav_duration(path), seconds)
                    self.assertEqual(save_copy(path, copy), copy.resolve())
                    self.assertEqual(copy.read_bytes(), path.read_bytes())

    def test_report_uses_generated_numbers(self):
        track = generate_melody(CUSTOM_SEED, 7, 16, UNICODE_SEED)
        report = build_report(track, 7)
        self.assertIn(f"Темп: {track.bpm} BPM", report)
        self.assertIn(f"Тембр: {track.waveform}", report)
        self.assertIn(f"Количество нот: {len(track.notes)} · Нот вне гаммы: 0", report)
        self.assertIn("Фактическая длительность WAV: 7.000 с", report)
        self.assertIn(transition_table(), report)


@unittest.skipUnless(sys.platform == "win32", "Проверка интерфейса Windows")
class WindowsTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from main import App

        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.root = tk.Tk()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.base)}):
            self.app = App(self.root)
        self.addCleanup(self.app.close)
        self.root.update()

    def wait_for_generation(self):
        deadline = time.monotonic() + 8
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertFalse(self.app.busy, "Время ожидания генерации истекло.")

    def test_ui_generate_play_stop_replay_save_and_regenerate(self):
        app = self.app
        app.mode.set(CUSTOM_SEED)
        app.update_mode_hint()
        with (
            patch("main.simpledialog.askstring", return_value=UNICODE_SEED) as seed_dialog,
            patch("main.messagebox.showerror") as error,
        ):
            app.generate_button.invoke()
            self.wait_for_generation()
            seed_dialog.assert_called_once()
            error.assert_not_called()

        self.assertTrue(app.wav_path.exists())
        self.assertIn(UNICODE_SEED, app.report)
        self.assertIsNotNone(app.playback_timer)
        self.assertTrue(app.stop_button.instate(("!disabled",)))
        report_window = app.report_window.window
        self.assertTrue(report_window.winfo_exists())
        self.assertIn(str(app.wav_path), app.report_window.text.get("1.0", "end"))
        time.sleep(0.12)
        app.stop_button.invoke()
        self.assertIsNone(app.playback_timer)
        app.play_button.invoke()
        self.assertIsNotNone(app.playback_timer)
        time.sleep(0.12)
        app.stop_button.invoke()

        target = self.base / "Вариант 🎵.wav"
        with patch("main.filedialog.asksaveasfilename", return_value=str(target)) as save_dialog:
            app.save_button.invoke()
        self.assertTrue(save_dialog.call_args.kwargs["confirmoverwrite"])
        self.assertEqual(target.read_bytes(), app.wav_path.read_bytes())
        self.assertIn(str(target), app.report_window.text.get("1.0", "end"))

        app.mode.set(SYSTEM_RANDOM)
        app.bits.set(16)
        with patch("main.messagebox.showerror") as error:
            app.generate_button.invoke()
            self.wait_for_generation()
            error.assert_not_called()
        self.assertIs(app.report_window.window, report_window)
        self.assertIn(SYSTEM_RANDOM, app.report)
        self.assertIn("16-bit", app.report)
        self.assertIsNone(app.saved_path)
        report_window.destroy()
        self.root.update()
        self.assertTrue(self.root.winfo_exists())
        app.report_button.invoke()
        self.assertTrue(app.report_window.window.winfo_exists())
        self.assertIsNot(app.report_window.window, report_window)

    def test_audio_error_keeps_wav_and_save_available(self):
        app = self.app
        with (
            patch("main.play_wav", side_effect=RuntimeError("Нет аудиоустройства")),
            patch("main.messagebox.showerror") as error,
        ):
            app.generate_button.invoke()
            self.wait_for_generation()
            error.assert_called_once()
        self.assertIsNone(app.playback_timer)
        self.assertIn("Звук не запустился", app.status.get())
        self.assertTrue(app.save_button.instate(("!disabled",)))
        self.assertTrue(app.wav_path.exists())

    def test_seed_dialog_accepts_unicode_and_spaces(self):
        from tkinter import Entry, Toplevel

        app = self.app
        app.mode.set(CUSTOM_SEED)

        def enter_seed():
            for dialog in self.root.winfo_children():
                if isinstance(dialog, Toplevel):
                    for frame in dialog.winfo_children():
                        for field in frame.winfo_children():
                            if isinstance(field, Entry):
                                field.insert(0, UNICODE_SEED)
                                dialog.ok()
                                return
            self.root.after(20, enter_seed)

        self.root.after(20, enter_seed)
        with (
            patch("main.play_wav"),
            patch("main.messagebox.showwarning") as warning,
            patch("main.messagebox.showerror") as error,
        ):
            app.generate_button.invoke()
            self.wait_for_generation()
            warning.assert_not_called()
            error.assert_not_called()
        self.assertEqual(app.last_seed, UNICODE_SEED)
        self.assertIn(UNICODE_SEED, app.report)


if __name__ == "__main__":
    unittest.main()
