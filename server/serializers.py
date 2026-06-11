"""Custom frame serializer for the in-app (browser) channel.

Wire protocol (deliberately dependency-free on the browser side):
  client → server : binary WebSocket frames = raw PCM16 mono @ 16 kHz
  server → client : binary frames = raw PCM16 mono @ 16 kHz (agent TTS audio)
                    (JSON text frames — transcripts/events — are sent directly
                     by TranscriptRelay processors, not through this serializer)
"""

from __future__ import annotations

from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.serializers.base_serializer import FrameSerializer


class RawPCMSerializer(FrameSerializer):
    def __init__(self, sample_rate: int = 16000, **kwargs):
        super().__init__(**kwargs)
        self._sample_rate = sample_rate

    async def setup(self, frame: StartFrame):
        pass

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if self.should_ignore_frame(frame):
            return None
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        return None  # everything else is not sent via the transport

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, (bytes, bytearray)) and len(data) > 0:
            return InputAudioRawFrame(audio=bytes(data),
                                      sample_rate=self._sample_rate,
                                      num_channels=1)
        return None  # ignore text frames from the client
