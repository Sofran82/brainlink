from typing import Callable

from BrainLinkParser import BrainLinkParser

from .data import EEGData


class BrainLinkDataParser:
    """
    Wrapper around the official Macrotellect BrainLinkParser.

    The Macrotellect parser handles the BrainLink byte protocol.
    This class converts the callbacks into our own EEGData object.
    """

    def __init__(
        self,
        data_callback: Callable[[EEGData], None] | None = None,
    ):
        self.data_callback = data_callback

        self.latest = EEGData.now()

        self.parser = BrainLinkParser(
            self._on_eeg,
            self._on_extended,
            self._on_gyro,
            self._on_rr,
            self._on_raw,
        )

    def parse(self, data: bytes):
        """
        Feed bytes received from the BrainLink COM port
        into the official parser.
        """

        if not data:
            return

        self.parser.parse(data)

    # ---------------------------------------------------------
    # BrainLink callbacks
    # ---------------------------------------------------------

    def _on_raw(self, raw: int):
        self.latest.timestamp = EEGData.now().timestamp
        self.latest.raw = raw

        self._emit()

    def _on_eeg(self, data):
        self.latest.timestamp = EEGData.now().timestamp

        self.latest.signal = getattr(data, "signal", None)
        self.latest.attention = getattr(data, "attention", None)
        self.latest.meditation = getattr(data, "meditation", None)

        self.latest.delta = getattr(data, "delta", None)
        self.latest.theta = getattr(data, "theta", None)

        self.latest.low_alpha = getattr(data, "lowAlpha", None)
        self.latest.high_alpha = getattr(data, "highAlpha", None)

        self.latest.low_beta = getattr(data, "lowBeta", None)
        self.latest.high_beta = getattr(data, "highBeta", None)

        self.latest.low_gamma = getattr(data, "lowGamma", None)
        self.latest.high_gamma = getattr(data, "highGamma", None)

        self._emit()

    def _on_extended(self, data):
        self.latest.battery = getattr(data, "battery", None)
        self.latest.temperature = getattr(data, "temperature", None)
        self.latest.heart = getattr(data, "heart", None)

    def _on_gyro(self, x, y, z):
        pass

    def _on_rr(self, rr1, rr2, rr3):
        pass

    # ---------------------------------------------------------

    def _emit(self):
        if self.data_callback is not None:
            self.data_callback(self.latest)