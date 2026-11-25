from dataclasses import dataclass

from generators import make_source
from music_theory import SCALES, STABLE_DEGREES, TRANSITIONS


WAVEFORMS = {
    8: ("Квадратная", "Импульсная 25%", "Треугольная"),
    16: ("Синус с обертонами", "Мягкая треугольная"),
}
RHYTHM_UNITS = (1, 2, 3, 4)
MAX_LEAP = 7


@dataclass(frozen=True)
class Note:
    midi: int
    eighths: int


@dataclass(frozen=True)
class Melody:
    mode: str
    seed: int | str | None
    seconds: float
    bits: int
    key: int
    scale: str
    bpm: int
    waveform: str
    notes: tuple[Note, ...]
    motif_length: int
    motif_repeat_start: int | None


def make_rhythm(source, total_eighths, motif_length, repeat_motif):
    reserve = (motif_length + 1 if repeat_motif else 0) + 2
    opening = []
    for index in range(motif_length):
        available = total_eighths - sum(opening)
        minimum_left = reserve + motif_length - index - 1
        choices = [unit for unit in (1, 2, 3) if unit <= available - minimum_left]
        opening.append(source.weighted_choice(choices, (5, 6, 2)[:len(choices)]))

    rhythm = opening[:]
    variation_start = None
    if repeat_motif:
        rhythm.append(1)
        variation_start = len(rhythm)
        for index in range(motif_length):
            available = total_eighths - sum(rhythm)
            minimum_left = 2 + motif_length - index - 1
            choices = [unit for unit in (1, 2, 3) if unit <= available - minimum_left]
            rhythm.append(source.weighted_choice(choices, (5, 6, 2)[:len(choices)]))

    remaining = total_eighths - sum(rhythm)
    while remaining > 4:
        choices = [unit for unit in RHYTHM_UNITS if unit <= remaining - 2]
        weights = (6, 7, 2, 1) if sum(rhythm) % 2 else (4, 7, 3, 2)
        unit = source.weighted_choice(choices, weights[:len(choices)])
        rhythm.append(unit)
        remaining -= unit
    penultimate = source.randint(1, min(2, remaining - 1))
    rhythm.extend((penultimate, remaining - penultimate))
    return rhythm, variation_start


def allowed_pitches(pitches, previous, repeated):
    return [
        pitch for pitch in pitches
        if abs(pitch - previous) <= MAX_LEAP
        and not (pitch == previous and repeated)
    ]


def choose_next(source, candidates, degrees, previous, ending, final):
    row = TRANSITIONS[degrees[previous]]
    weights = []
    for pitch in candidates:
        degree = degrees[pitch]
        weight = row[degree] * (2 if 0 < abs(pitch - previous) <= 2 else 1)
        if ending:
            if degree == 0:
                weight *= 10 if final else 3
            elif degree in STABLE_DEGREES:
                weight *= 4 if final else 2
        weights.append(weight)
    return source.weighted_choice(candidates, weights)


def generate_melody(mode, seconds, bits, seed=None):
    if not 5 <= seconds <= 10:
        raise ValueError("Длительность должна быть от 5 до 10 секунд.")
    if bits not in WAVEFORMS:
        raise ValueError("Выберите режим звучания 8-bit или 16-bit.")

    source, actual_seed = make_source(mode, seed)
    key = source.randint(0, 11)
    scale = source.choice(tuple(SCALES))
    bpm = source.randint(90, 170)
    waveform = source.choice(WAVEFORMS[bits])

    lowest = source.randint(55, 63)
    highest = lowest + source.randint(14, 21)
    steps = SCALES[scale]
    degrees = {
        midi: steps.index((midi - key) % 12)
        for midi in range(lowest, highest + 1)
        if (midi - key) % 12 in steps
    }
    pitches = tuple(degrees)
    motif_length = source.randint(3, 5)
    total_eighths = round(seconds * bpm / 30)
    repeat_motif = total_eighths >= 2 * motif_length + 3 and source.randint(1, 100) <= 65
    rhythm, variation_start = make_rhythm(source, total_eighths, motif_length, repeat_motif)

    first_weights = [3 if degrees[pitch] in STABLE_DEGREES else 1 for pitch in pitches]
    notes = [Note(source.weighted_choice(pitches, first_weights), rhythm[0])]
    for index in range(1, len(rhythm)):
        previous = notes[-1].midi
        repeated = len(notes) >= 2 and notes[-2].midi == previous
        candidates = allowed_pitches(pitches, previous, repeated)
        if variation_start is not None and index == variation_start - 1:
            anchor = notes[0].midi
            bridge = [pitch for pitch in candidates
                      if abs(pitch - anchor) <= MAX_LEAP and not pitch == previous == anchor]
            if bridge:
                candidates = bridge
        if index == variation_start and notes[0].midi not in candidates:
            variation_start = None
        motif_index = index - variation_start if variation_start is not None else -1
        if 0 <= motif_index < motif_length - 1 and notes[motif_index].midi in candidates:
            pitch = notes[motif_index].midi
        else:
            if motif_index == motif_length - 1:
                original_ending = notes[motif_index].midi
                candidates = [pitch for pitch in candidates if pitch != original_ending]
            pitch = choose_next(
                source, candidates, degrees, previous,
                index >= len(rhythm) - 2, index == len(rhythm) - 1,
            )
        notes.append(Note(pitch, rhythm[index]))

    return Melody(mode, actual_seed, seconds, bits, key, scale, bpm, waveform,
                  tuple(notes), motif_length, variation_start)
