from dataclasses import dataclass
from time import time


@dataclass
class EEGData:
    timestamp: float

    raw: int | None = None

    signal: int | None = None
    attention: int | None = None
    meditation: int | None = None

    delta: int | None = None
    theta: int | None = None

    low_alpha: int | None = None
    high_alpha: int | None = None

    low_beta: int | None = None
    high_beta: int | None = None

    low_gamma: int | None = None
    high_gamma: int | None = None

    battery: int | None = None
    temperature: int | None = None
    heart: int | None = None

    @classmethod
    def now(cls):
        return cls(timestamp=time())