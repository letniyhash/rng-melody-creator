import os
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory
from threading import Thread
from tkinter import filedialog, messagebox, simpledialog, ttk

from audio import play_wav, save_copy, stop_audio, wav_duration, write_wav
from generators import CUSTOM_SEED, MODES, SYSTEM_RANDOM, TIME_SEED
from melody import generate_melody
from statistics_report import ReportWindow, build_report


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("RNG Melody Creator")
        self.root.minsize(540, 390)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.mode = tk.StringVar(value=TIME_SEED)
        self.duration = tk.StringVar(value="7,0")
        self.bits = tk.IntVar(value=8)
        self.status = tk.StringVar(value="Готово к генерации.")
        self.mode_hint = tk.StringVar()
        self.last_seed = ""
        self.results = Queue()
        self.busy = False
        self.closing = False
        self.playback_timer = None
        self.animation_timer = None
        self.cassette_frame = 0
        self.report = None
        self.saved_path = None
        self.actual_seconds = 0

        user_folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RNG Melody Creator"
        user_folder.mkdir(parents=True, exist_ok=True)
        self.temp_folder = TemporaryDirectory(prefix="session-", dir=user_folder)
        self.wav_path = Path(self.temp_folder.name) / "melody.wav"
        self.report_window = ReportWindow(root)

        self.build_interface()
        self.update_mode_hint()
        self.update_buttons()
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())

    def build_interface(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.configure(background="#120c22")
        style.configure(".", background="#120c22", foreground="#fff4eb", font=("Consolas", 11))
        style.configure("TButton", background="#2d2047", bordercolor="#9364bb",
                        lightcolor="#9364bb", darkcolor="#38244e", padding=(10, 9))
        style.map("TButton", background=[("pressed", "#553271"), ("active", "#44285f")],
                  foreground=[("disabled", "#a497b5")])
        style.configure("Accent.TButton", background="#ffdb5b", foreground="#22152a",
                        bordercolor="#ffe897", lightcolor="#ffe897", darkcolor="#a46724",
                        padding=(14, 12), font=("Consolas", 13, "bold"))
        style.map("Accent.TButton",
                  background=[("disabled", "#443451"), ("pressed", "#edaa43"), ("active", "#fff191")],
                  foreground=[("disabled", "#cec1d8")])
        style.configure("TCombobox", fieldbackground="#241a39", arrowcolor="#63f5d6",
                        bordercolor="#9364bb", padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", "#241a39")],
                  foreground=[("readonly", "#fff4eb")], selectbackground=[("readonly", "#241a39")],
                  selectforeground=[("readonly", "#fff4eb")])
        style.configure("TRadiobutton", indicatorbackground="#241a39", indicatorforeground="#63f5d6")
        style.map("TRadiobutton", background=[("active", "#2d2047")],
                  indicatorbackground=[("selected", "#63f5d6")])
        style.configure("Muted.TLabel", foreground="#c9b5df", font=("Consolas", 10))
        style.configure("Vertical.TScrollbar", background="#38244e", troughcolor="#120c22",
                        arrowcolor="#ffdb5b")
        self.root.option_add("*TCombobox*Listbox.background", "#241a39")
        self.root.option_add("*TCombobox*Listbox.foreground", "#fff4eb")

        panel = ttk.Frame(self.root, padding=(24, 22, 24, 22))
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(1, weight=1)
        marquee = tk.Canvas(panel, width=555, height=126, background="#1c122d",
                            borderwidth=0, highlightthickness=0)
        marquee.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 22))
        marquee.bind("<Configure>", self.draw_marquee)
        self.animation_timer = self.root.after(120, self.animate_cassette, marquee)

        ttk.Label(panel, text="Источник случайности").grid(row=1, column=0, sticky="w", padx=(0, 16))
        self.mode_box = ttk.Combobox(panel, values=MODES, textvariable=self.mode, state="readonly")
        self.mode_box.grid(row=1, column=1, sticky="ew")
        self.mode_box.bind("<<ComboboxSelected>>", self.update_mode_hint)
        ttk.Label(panel, textvariable=self.mode_hint, style="Muted.TLabel", wraplength=440).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(5, 16)
        )

        ttk.Label(panel, text="Длительность, с").grid(row=3, column=0, sticky="w", padx=(0, 16))
        self.duration_box = ttk.Combobox(
            panel, values=[f"{step / 2:.1f}".replace(".", ",") for step in range(10, 21)],
            textvariable=self.duration, state="readonly", width=7,
        )
        self.duration_box.grid(row=3, column=1, sticky="w")

        ttk.Label(panel, text="Звучание").grid(row=4, column=0, sticky="w", pady=(12, 0))
        formats = ttk.Frame(panel)
        formats.grid(row=4, column=1, sticky="w", pady=(12, 0))
        self.format_buttons = []
        for bits in (8, 16):
            button = ttk.Radiobutton(formats, text=f"{bits}-bit", value=bits, variable=self.bits)
            button.pack(side="left", padx=(0, 16))
            self.format_buttons.append(button)

        self.generate_button = ttk.Button(
            panel, text="Сгенерировать мелодию", style="Accent.TButton", command=self.generate
        )
        self.generate_button.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(21, 13))

        actions = ttk.Frame(panel)
        actions.grid(row=6, column=0, columnspan=2, sticky="ew")
        self.play_button = ttk.Button(actions, text="Воспроизвести", command=self.play)
        self.stop_button = ttk.Button(actions, text="Остановить", command=self.stop)
        self.save_button = ttk.Button(actions, text="Сохранить WAV", command=self.save)
        self.report_button = ttk.Button(actions, text="Статистика", command=self.show_report)
        for column, button in enumerate(
            (self.play_button, self.stop_button, self.save_button, self.report_button)
        ):
            actions.columnconfigure(column, weight=1)
            button.grid(row=0, column=column, sticky="ew", padx=(0, 6 if column < 3 else 0))

        ttk.Label(panel, textvariable=self.status, style="Muted.TLabel", wraplength=470).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )

    def draw_marquee(self, event):
        canvas = event.widget
        width, height = event.width, event.height
        canvas.delete("all")
        for y in range(6, height - 4, 5):
            canvas.create_line(6, y, width - 6, y, fill="#251636")
        canvas.create_rectangle(2, 2, width - 3, height - 3, outline="#b477eb", width=2)
        canvas.create_rectangle(8, 8, width - 9, height - 9, outline="#613c82")
        for y, title, size, color in (
            (32, "RNG MELODY", 23, "#63f5d6"), (68, "CREATOR", 29, "#ffdb5b")
        ):
            canvas.create_text(width / 2 + 2, y + 3, text=title, fill="#6f378e",
                               font=("Consolas", size, "bold"))
            canvas.create_text(width / 2, y, text=title, fill=color, font=("Consolas", size, "bold"))

        heights = (2, 4, 7, 4, 2, 3, 5, 3, 2, 4, 6, 4, 2)
        for index, bars in enumerate(heights):
            x = width / 2 + (index - len(heights) // 2) * 10
            for level in range(bars):
                y = 113 - level * 3
                canvas.create_rectangle(x - 2, y - 1, x + 2, y,
                                        fill="#63f5d6" if index % 2 else "#b477eb", outline="")
        self.draw_cassette(canvas, width)

    def draw_cassette(self, canvas, width):
        canvas.delete("cassette")
        x = width - 105
        canvas.create_rectangle(x, 16, x + 87, 78, fill="#120c22",
                                outline="#9364bb", tags="cassette")
        canvas.create_rectangle(x + 9, 27, x + 78, 67, fill="#63f5d6",
                                outline="#fff4eb", width=2, tags="cassette")
        canvas.create_rectangle(x + 15, 34, x + 72, 53, fill="#241a39",
                                outline="#38244e", tags="cassette")
        canvas.create_rectangle(x + 23, 59, x + 64, 66, fill="#b477eb",
                                outline="", tags="cassette")
        offsets = ((0, -6), (4, -4), (6, 0), (4, 4), (0, 6), (-4, 4), (-6, 0), (-4, -4))
        for center in (x + 29, x + 58):
            canvas.create_rectangle(center - 7, 36, center + 7, 51, fill="#120c22",
                                    outline="#9364bb", tags="cassette")
            for spoke in (0, 3, 5):
                dx, dy = offsets[(self.cassette_frame + spoke) % len(offsets)]
                canvas.create_line(center, 44, center + dx, 44 + dy, fill="#ffdb5b",
                                   width=2, tags="cassette")

    def animate_cassette(self, canvas):
        if self.root.winfo_viewable():
            self.cassette_frame = (self.cassette_frame + 1) % 8
            self.draw_cassette(canvas, canvas.winfo_width())
        self.animation_timer = self.root.after(120, self.animate_cassette, canvas)

    def update_mode_hint(self, _event=None):
        hints = {
            TIME_SEED: "Seed берётся из системного времени и показывается в отчёте.",
            CUSTOM_SEED: "Перед генерацией откроется окно ввода seed.",
            SYSTEM_RANDOM: "Криптографический источник операционной системы.",
        }
        self.mode_hint.set(hints[self.mode.get()])

    def update_buttons(self):
        ready = self.report is not None and not self.busy
        for button in (self.play_button, self.save_button, self.report_button):
            button.configure(state="normal" if ready else "disabled")
        self.stop_button.configure(state="normal" if self.playback_timer is not None else "disabled")
        self.generate_button.configure(state="disabled" if self.busy else "normal")
        for box in (self.mode_box, self.duration_box):
            box.configure(state="disabled" if self.busy else "readonly")
        for button in self.format_buttons:
            button.configure(state="disabled" if self.busy else "normal")

    def generate(self):
        if self.busy:
            return
        mode = self.mode.get()
        seed = None
        if mode == CUSTOM_SEED:
            seed = simpledialog.askstring(
                "Пользовательский seed", "Введите текст для seed.",
                initialvalue=self.last_seed, parent=self.root,
            )
            if seed is None:
                return
            if not seed.strip():
                messagebox.showwarning(
                    "Пустой seed", "Введите хотя бы один непробельный символ.", parent=self.root
                )
                return
            self.last_seed = seed

        if self.playback_timer is not None and not self.stop():
            return
        seconds = float(self.duration.get().replace(",", "."))
        self.busy = True
        self.status.set("Сочиняем мелодию и записываем WAV…")
        self.update_buttons()
        Thread(target=self.generate_in_background, args=(mode, seconds, self.bits.get(), seed)).start()
        self.root.after(40, self.check_result)

    def generate_in_background(self, mode, seconds, bits, seed):
        try:
            melody = generate_melody(mode, seconds, bits, seed)
            pending_path = self.wav_path.with_name("pending.wav")
            write_wav(melody, pending_path)
            actual_seconds = wav_duration(pending_path)
            report = build_report(melody, actual_seconds)
            pending_path.replace(self.wav_path)
            self.results.put((report, actual_seconds, None))
        except Exception as error:
            self.results.put((None, 0, error))

    def check_result(self):
        try:
            report, actual_seconds, error = self.results.get_nowait()
        except Empty:
            self.root.after(40, self.check_result)
            return

        self.busy = False
        if self.closing:
            self.close()
            return
        if error is not None:
            self.show_error("Ошибка генерации", error)
        else:
            self.report = report
            self.actual_seconds = actual_seconds
            self.saved_path = None
            self.show_report()
            self.play()
        self.update_buttons()

    def play(self):
        try:
            play_wav(self.wav_path)
        except (OSError, RuntimeError) as error:
            self.show_error("Звук не запустился. Проверьте устройство воспроизведения", error)
            return

        if self.playback_timer is not None:
            self.root.after_cancel(self.playback_timer)
        self.playback_timer = self.root.after(round(self.actual_seconds * 1000), self.playback_finished)
        self.status.set("Воспроизводится мелодия…")
        self.update_buttons()

    def playback_finished(self):
        self.playback_timer = None
        self.status.set("Воспроизведение завершено.")
        self.update_buttons()

    def stop(self):
        try:
            stop_audio()
        except RuntimeError as error:
            self.show_error("Звук не удалось остановить", error)
            return False
        if self.playback_timer is not None:
            self.root.after_cancel(self.playback_timer)
            self.playback_timer = None
        self.status.set("Воспроизведение остановлено.")
        self.update_buttons()
        return True

    def save(self):
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Сохранить мелодию",
            defaultextension=".wav", initialfile="RNG-мелодия.wav",
            filetypes=(("Звук WAV", "*.wav"),), confirmoverwrite=True,
        )
        if not destination:
            return
        try:
            self.saved_path = save_copy(self.wav_path, destination)
        except OSError as error:
            self.show_error("Не удалось сохранить WAV", error)
            return
        self.status.set(f"Сохранено: {self.saved_path.name}")
        self.report_window.display(self.report, self.wav_path, self.saved_path, show=False)

    def show_report(self):
        self.report_window.display(self.report, self.wav_path, self.saved_path)

    def show_error(self, title, error):
        self.status.set(title + ".")
        messagebox.showerror("RNG Melody Creator", f"{title}.\n\n{error}", parent=self.root)

    def close(self):
        if self.animation_timer is not None:
            self.root.after_cancel(self.animation_timer)
            self.animation_timer = None
        if self.busy:
            self.closing = True
            self.root.withdraw()
            return
        if self.report is not None:
            try:
                stop_audio()
            except RuntimeError:
                pass
        self.root.destroy()
        self.temp_folder.cleanup()


def main():
    root = tk.Tk()
    try:
        App(root)
    except OSError as error:
        messagebox.showerror(
            "RNG Melody Creator", f"Не удалось подготовить папку для WAV.\n\n{error}", parent=root
        )
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
