"""Channel A — in-app voice session (browser mic ↔ ops/manager personas).

Pipeline: WS audio in → AssemblyAI streaming STT → Claude (persona tools)
          → Cartesia TTS → WS audio out
Transcripts/agent text are mirrored to the client as JSON for live captions.
"""

from __future__ import annotations

import uuid

from fastapi import WebSocket
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.assemblyai.models import AssemblyAIConnectionParams
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from agent.personas import build_persona
from config import settings
from processors import TranscriptRelay
from serializers import RawPCMSerializer

SAMPLE_RATE = 16000


async def run_inapp_session(websocket: WebSocket, persona_name: str) -> None:
    session_ref = f"inapp:{persona_name}:{uuid.uuid4().hex[:8]}"
    persona = build_persona(persona_name, session_ref)
    logger.info("starting in-app session {} ({})", session_ref, persona_name)

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=RawPCMSerializer(sample_rate=SAMPLE_RATE),
        ),
    )

    stt = AssemblyAISTTService(
        api_key=settings.assemblyai_api_key,
        vad_force_turn_endpoint=False,  # use AssemblyAI's end-of-turn model
        connection_params=AssemblyAIConnectionParams(
            end_of_turn_confidence_threshold=0.7,
            # floor/manager: people pause mid-utterance while reading labels
            min_turn_silence=560,
            max_turn_silence=2400,
        ),
    )

    llm = AnthropicLLMService(api_key=settings.anthropic_api_key,
                              model=settings.live_model)
    for name, handler in persona.handlers.items():
        llm.register_function(name, handler)

    tts = CartesiaTTSService(api_key=settings.cartesia_api_key,
                             voice_id=settings.cartesia_voice_id)

    context = OpenAILLMContext(
        messages=[{"role": "system", "content": persona.system}],
        tools=persona.tools,
    )
    context_aggregator = llm.create_context_aggregator(context)

    async def send_event(speaker: str, text: str, final: bool):
        try:
            await websocket.send_json({"type": "transcript", "speaker": speaker,
                                       "text": text, "final": final})
        except Exception:
            pass

    pipeline = Pipeline([
        transport.input(),
        stt,
        TranscriptRelay("user", send_event),
        context_aggregator.user(),
        llm,
        tts,
        TranscriptRelay("agent", send_event),
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        ),
    )

    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    finally:
        logger.info("in-app session {} ended", session_ref)
