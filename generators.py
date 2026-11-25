import random
import secrets
import time


TIME_SEED = "PRNG — Time Seed"
CUSTOM_SEED = "PRNG — Custom Seed"
SYSTEM_RANDOM = "System Random"
MODES = (TIME_SEED, CUSTOM_SEED, SYSTEM_RANDOM)


class SystemRandom:
    def choice(self, items):
        return secrets.choice(items)

    def randint(self, low, high):
        return low + secrets.randbelow(high - low + 1)


class RandomSource:
    def __init__(self, backend):
        self.backend = backend

    def choice(self, items):
        return self.backend.choice(items)

    def randint(self, low, high):
        return self.backend.randint(low, high)

    def weighted_choice(self, items, weights):
        ticket = self.randint(1, sum(weights))
        for item, weight in zip(items, weights):
            ticket -= weight
            if ticket <= 0:
                return item
        raise ValueError("Некорректные веса выбора.")


def make_source(mode, seed=None):
    if mode == TIME_SEED:
        actual_seed = time.time_ns() if seed is None else seed
        return RandomSource(random.Random(actual_seed)), actual_seed
    if mode == CUSTOM_SEED:
        if not isinstance(seed, str) or not seed.strip():
            raise ValueError("Введите seed, содержащий хотя бы один непробельный символ.")
        return RandomSource(random.Random(seed)), seed
    if mode == SYSTEM_RANDOM:
        return RandomSource(SystemRandom()), None
    raise ValueError("Неизвестный режим случайности.")
