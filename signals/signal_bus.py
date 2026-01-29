from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Iterable

from signals.signal import Signal


@dataclass(frozen=True)
class SignalEnvelope:
    signal: Signal
    trace_id: str


class SignalBus:
    def publish(self, envelope: SignalEnvelope) -> None:
        raise NotImplementedError

    def drain(self) -> Iterable[SignalEnvelope]:
        raise NotImplementedError


class MultiprocessingSignalBus(SignalBus):
    def __init__(self) -> None:
        self._queue: mp.Queue[SignalEnvelope] = mp.Queue()

    def publish(self, envelope: SignalEnvelope) -> None:
        self._queue.put(envelope)

    def drain(self) -> Iterable[SignalEnvelope]:
        while not self._queue.empty():
            yield self._queue.get()

    @property
    def queue(self) -> mp.Queue[SignalEnvelope]:
        return self._queue
