import math
import wave
from array import array
from functools import lru_cache
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile

try:
    import winsound
except ImportError:
    winsound = None

from music_theory import note_frequency


SAMPLE_RATES = {8: 32000, 16: 44100}
TABLE_SIZE = 2048


@lru_cache(maxsize=5)
def wave_table(name):
    if name == "Квадратная":
        harmonics = [(n, 1 / n) for n in (1, 3, 5, 7)]
    elif name == "Импульсная 25%":
        harmonics = [(n, math.sin(math.pi * n / 4) / n) for n in (1, 2, 3, 5, 6, 7)]
    elif name == "Треугольная":
        harmonics = [(n, (-1) ** index / n ** 2) for index, n in enumerate((1, 3, 5, 7))]
    elif name == "Мягкая треугольная":
        harmonics = [(1, 1), (3, -0.10), (5, 0.025)]
    else:
        harmonics = [(1, 1), (2, 0.18), (3, 0.08)]

    values = [
        sum(amplitude * math.sin(math.tau * harmonic * index / TABLE_SIZE)
            for harmonic, amplitude in harmonics)
        for index in range(TABLE_SIZE)
    ]
    peak = max(abs(value) for value in values)
    return [value / peak for value in values]


def stereo_samples(melody, lead, total_eighths, rate):
    peak, offset = (57, 128) if melody.bits == 8 else (14745, 0)
    samples = array("B" if melody.bits == 8 else "h")
    left_delay = round(rate * 0.023)
    right_delay = round(rate * 0.037)
    fade_frames = round(rate * 0.045)
    root = 36 + melody.key
    bass_steps = [math.tau * note_frequency(note) / rate for note in (root, root + 7)]

    for beat, eighth in enumerate(range(0, total_eighths, 2)):
        start = round(len(lead) * eighth / total_eighths)
        end = round(len(lead) * min(eighth + 2, total_eighths) / total_eighths)
        length = end - start
        step = bass_steps[beat % 4 == 2 and eighth + 2 < total_eighths]
        for index in range(start, end):
            age = index - start
            bass_envelope = min(1, age / (rate * 0.015), (length - 1 - age) / (rate * 0.065))
            bass = 0.18 * math.sin(age * step) * bass_envelope
            dry = 0.66 * lead[index] + bass
            left_echo = lead[index - left_delay] if index >= left_delay else 0
            right_echo = lead[index - right_delay] if index >= right_delay else 0
            fade = min(1, (len(lead) - 1 - index) / fade_frames)
            samples.append(offset + round(peak * fade * (dry + 0.14 * left_echo)))
            samples.append(offset + round(peak * fade * (dry + 0.14 * right_echo)))
    return samples


def write_wav(melody, path):
    rate = SAMPLE_RATES[melody.bits]
    total_frames = round(melody.seconds * rate)
    total_eighths = sum(note.eighths for note in melody.notes)
    table = wave_table(melody.waveform)
    lead = array("f")

    used_eighths = 0
    start = 0
    for note_index, note in enumerate(melody.notes):
        used_eighths += note.eighths
        end = round(total_frames * used_eighths / total_eighths)
        frames = end - start
        audible = frames if note_index == len(melody.notes) - 1 else round(frames * 0.94)
        attack = min(round(rate * 0.007), audible // 3)
        release = min(round(rate * 0.032), audible // 3)
        phase_step = TABLE_SIZE * note_frequency(note.midi) / rate

        for sample_index in range(audible):
            envelope = min(1, sample_index / attack, (audible - 1 - sample_index) / release)
            envelope *= 1 - 0.25 * sample_index / audible
            value = table[int(sample_index * phase_step) % TABLE_SIZE]
            lead.append(value * envelope)

        lead.extend([0] * (frames - audible))
        start = end

    with wave.open(str(path), "wb") as output:
        output.setparams((2, melody.bits // 8, rate, 0, "NONE", "not compressed"))
        output.writeframes(stereo_samples(melody, lead, total_eighths, rate))


def wav_duration(path):
    with wave.open(str(path), "rb") as track:
        return track.getnframes() / track.getframerate()


def save_copy(source, destination):
    source, destination = Path(source), Path(destination).resolve()
    if destination == source.resolve():
        return destination
    with NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as file:
        pending_path = Path(file.name)
    try:
        copyfile(source, pending_path)
        pending_path.replace(destination)
    finally:
        pending_path.unlink(missing_ok=True)
    return destination


def play_wav(path):
    if winsound is None:
        raise RuntimeError("Для воспроизведения нужен Python для Windows с модулем winsound.")
    if not Path(path).is_file():
        raise FileNotFoundError("Файл мелодии не найден. Сгенерируйте её ещё раз.")
    winsound.PlaySound(
        str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    )


def stop_audio():
    if winsound is not None:
        winsound.PlaySound(None, 0)
