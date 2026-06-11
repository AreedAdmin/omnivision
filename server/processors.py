"""Pipeline side-channel processors.

TranscriptRelay taps the frame stream and reports text to an async callback
without altering the pipeline:
  role="user"  → TranscriptionFrame / InterimTranscriptionFrame (STT output)
  role="agent" → TTSTextFrame (sentence-level text the agent is speaking)

Used for: dashboard live captions (channel A) and call transcript persistence
(channel B).
"""

from __future__ import annotations

from typing import Awaitable, Callable

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# callback(speaker: str, text: str, final: bool)
TextCallback = Callable[[str, str, bool], Awaitable[None]]


class TranscriptRelay(FrameProcessor):
    def __init__(self, role: str, on_text: TextCallback, include_interim: bool = True):
        super().__init__()
        self._role = role
        self._on_text = on_text
        self._include_interim = include_interim

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        try:
            if self._role == "user":
                if isinstance(frame, TranscriptionFrame) and frame.text.strip():
                    await self._on_text(self._role, frame.text, True)
                elif (self._include_interim
                      and isinstance(frame, InterimTranscriptionFrame)
                      and frame.text.strip()):
                    await self._on_text(self._role, frame.text, False)
            elif self._role == "agent":
                if isinstance(frame, TTSTextFrame) and frame.text.strip():
                    await self._on_text(self._role, frame.text, True)
        except Exception:
            pass  # side-channel must never break the audio pipeline
        await self.push_frame(frame, direction)
