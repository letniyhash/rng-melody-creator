import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import ttk

from generators import CUSTOM_SEED, TIME_SEED
from music_theory import INTERVAL_NAMES, MODEL_VERSION, PITCH_NAMES, SCALES, note_name, transition_table


def build_report(melody, actual_seconds):
    pitches = [note.midi for note in melody.notes]
    count = len(pitches)
    frequency = Counter(pitches)
    intervals = Counter(abs(b - a) for a, b in zip(pitches, pitches[1:]))
    outside = sum((pitch - melody.key) % 12 not in SCALES[melody.scale] for pitch in pitches)

    if melody.mode == TIME_SEED:
        source = f"Псевдослучайный, seed от часов компьютера\nSeed (целое число): {melody.seed}"
    elif melody.mode == CUSTOM_SEED:
        source = f"Псевдослучайный, пользовательский seed\nSeed (строка в кавычках): {melody.seed!r}"
    else:
        source = "Системный криптографический источник. Результат невоспроизводим по seed."

    lines = [
        f"Генератор: {melody.mode}", source,
        f"Тональность: {PITCH_NAMES[melody.key]}, {melody.scale}",
        f"Темп: {melody.bpm} BPM · Режим: {melody.bits}-bit",
        f"Тембр: {melody.waveform}",
        f"Цель: {melody.seconds:.3f} с · Фактическая длительность WAV: {actual_seconds:.3f} с",
        f"Количество нот: {count} · Нот вне гаммы: {outside}",
        "",
        "ПОСЛЕДОВАТЕЛЬНОСТЬ · нота (длительность в восьмых)",
        "  ".join(f"{note_name(note.midi)} ({note.eighths})" for note in melody.notes),
        "",
        "РАСПРЕДЕЛЕНИЕ ПО НОТАМ · количество и процент",
    ]
    for pitch, occurrences in sorted(frequency.items()):
        fraction = occurrences / count
        bar = "█" * max(1, round(fraction * 30))
        lines.append(f"{note_name(pitch):<6} {occurrences:>2}  {fraction:>6.1%}  {bar}")

    lines.extend(("", "ИНТЕРВАЛЫ · расстояние в полутонах без учёта направления"))
    for size, occurrences in sorted(intervals.items()):
        lines.append(f"{size:>2}  {INTERVAL_NAMES[size]:<17} {occurrences}")
    lines.extend((
        "", "ПОВТОРЫ НОТ",
        f"Соседних повторов одной высоты: {intervals[0]}",
        f"Уникальных высот: {len(frequency)}. Повторных появлений: {count - len(frequency)}.",
        "", "МОТИВ",
        "Начальный мотив: " + "  ".join(note_name(pitch) for pitch in pitches[:melody.motif_length]),
    ))
    start = melody.motif_repeat_start
    if start is None:
        lines.append("Вариаций: 0.")
    else:
        end = start + melody.motif_length
        shared = sum(a == b for a, b in zip(pitches, pitches[start:end]))
        lines.append(f"Вариаций: 1 (начиная с ноты №{start + 1}). "
                     f"Совпали {shared} из {melody.motif_length} высот.")
        lines.append("Вариация: " + "  ".join(note_name(pitch) for pitch in pitches[start:end]))

    lines.extend((
        "", f"МАТРИЦА БАЗОВЫХ ВЕСОВ ПЕРЕХОДОВ · модель {MODEL_VERSION}",
        transition_table(),
        "Из строки выбираются веса доступных высот. Пошаговое движение",
        "и устойчивые ступени в конце получают больший вес. Вариация",
        "мотива может повторить высоту напрямую в пределах ограничений.",
    ))
    return "\n".join(lines)


class ReportWindow:
    def __init__(self, root):
        self.root = root
        self.window = None
        self.text = None

    def display(self, report, wav_path, saved_path=None, show=True):
        if self.window is None or not self.window.winfo_exists():
            if not show:
                return
            self.window = tk.Toplevel(self.root)
            self.window.title("Статистика мелодии")
            self.window.geometry("720x625")
            self.window.minsize(430, 300)
            frame = ttk.Frame(self.window, padding=14)
            frame.pack(fill="both", expand=True)
            scrollbar = ttk.Scrollbar(frame)
            scrollbar.pack(side="right", fill="y")
            self.text = tk.Text(
                frame, wrap="word", font=("Consolas", 11),
                background="#1c122d", foreground="#c8ffef", borderwidth=0,
                highlightthickness=2, highlightbackground="#9364bb",
                highlightcolor="#63f5d6", selectbackground="#553271",
                selectforeground="#fff4eb",
                padx=16, pady=14, yscrollcommand=scrollbar.set,
            )
            self.text.pack(fill="both", expand=True)
            scrollbar.configure(command=self.text.yview)

        files = f"Текущий WAV: {Path(wav_path).name}\nПуть: {wav_path}"
        if saved_path is not None:
            files += f"\nСохранённая копия: {Path(saved_path).name}\nПуть: {saved_path}"

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", files + "\n\n" + report)
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
        if show:
            self.window.deiconify()
            self.window.lift()
