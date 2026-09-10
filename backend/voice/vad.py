from __future__ import annotations

import math
from array import array
from dataclasses import dataclass


@dataclass(slots=True)
class VADResult:
    speaking: bool
    speech_started: bool = False
    speech_ended: bool = False
    level: float = 0.0


class EnergyVAD:
    """Small PCM16 VAD used as a deterministic fallback, not a speech recognizer."""

    def __init__(self, *, threshold: float = 0.025, silence_ms: int = 900, sample_rate: int = 16_000) -> None:
        self.threshold = threshold
        self.silence_samples = int(sample_rate * silence_ms / 1000)
        self._speaking = False
        self._quiet_samples = 0

    def feed(self, pcm16: bytes) -> VADResult:
        samples = array("h")
        samples.frombytes(pcm16[:len(pcm16) - len(pcm16) % 2])
        if not samples:
            return VADResult(self._speaking)
        level = math.sqrt(sum((sample / 32768) ** 2 for sample in samples) / len(samples))
        started = ended = False
        if level >= self.threshold:
            self._quiet_samples = 0
            if not self._speaking:
                self._speaking, started = True, True
        elif self._speaking:
            self._quiet_samples += len(samples)
            if self._quiet_samples >= self.silence_samples:
                self._speaking, self._quiet_samples, ended = False, 0, True
        return VADResult(self._speaking, started, ended, level)

