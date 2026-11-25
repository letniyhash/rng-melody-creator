MODEL_VERSION = "1.0"
PITCH_NAMES = (
    "До", "До♯", "Ре", "Ми♭", "Ми", "Фа",
    "Фа♯", "Соль", "Ля♭", "Ля", "Си♭", "Си",
)
SCALES = {
    "мажор": (0, 2, 4, 5, 7, 9, 11),
    "натуральный минор": (0, 2, 3, 5, 7, 8, 10),
}
DEGREES = ("I", "II", "III", "IV", "V", "VI", "VII")
STABLE_DEGREES = (0, 2, 4)
TRANSITIONS = (
    (5, 25, 20, 12, 25, 9, 4),
    (32, 5, 26, 12, 16, 5, 4),
    (19, 21, 5, 24, 20, 9, 2),
    (19, 10, 26, 5, 30, 8, 2),
    (33, 9, 14, 17, 5, 19, 3),
    (17, 8, 11, 13, 32, 5, 14),
    (48, 11, 7, 4, 7, 18, 5),
)
INTERVAL_NAMES = (
    "прима", "малая секунда", "большая секунда", "малая терция",
    "большая терция", "чистая кварта", "тритон", "чистая квинта",
    "малая секста", "большая секста", "малая септима",
    "большая септима", "октава",
)


def note_name(midi):
    return f"{PITCH_NAMES[midi % 12]}{midi // 12 - 1}"


def note_frequency(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def transition_table():
    lines = ["Из / в   " + " ".join(f"{degree:>4}" for degree in DEGREES) + "   Сумма"]
    for degree, row in zip(DEGREES, TRANSITIONS):
        values = " ".join(f"{weight:>4}" for weight in row)
        lines.append(f"{degree:<8} {values}   {sum(row):>5}")
    return "\n".join(lines)
