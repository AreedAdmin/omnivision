"""Channel B — outbound supplier call (Twilio Media Streams ↔ call persona).

The call persona is deliberately near-toolless (plan/04): PO context is baked
into the system prompt before dialing; its only tool is end_call. Every write
happens AFTER the call, in agent.extraction.finalize_call — so a dropped call
never leaves a half-written PO.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocket
from loguru import logger
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.assemblyai.models import AssemblyAIConnectionParams
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

import db
from agent.extraction import finalize_call
from agent.personas import INBOUND_CALL_SCHEMAS, build_inbound_prompt
from config import settings
from processors import TranscriptRelay

SAMPLE_RATE = 8000  # Twilio Media Streams is 8 kHz μ-law; serializer transcodes


async def run_telephony_session(websocket: WebSocket, stream_sid: str,
                                call_sid: str, ctx: dict) -> None:
    """ctx comes from calls.CALL_CONTEXTS — created before dialing."""
    call_id = ctx["call_id"]
    po_id = ctx["po_id"]
    logger.info("starting supplier call session call_id={} po={}", call_id, ctx["po_number"])

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=TwilioFrameSerializer(
                stream_sid=stream_sid,
                call_sid=call_sid,
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
            ),
        ),
    )

    stt = AssemblyAISTTService(
        api_key=settings.assemblyai_api_key,
        vad_force_turn_endpoint=False,
        connection_params=AssemblyAIConnectionParams(
            end_of_turn_confidence_threshold=0.7,
            # phone pacing: shorter silence so the line never feels dead
            min_turn_silence=400,
            max_turn_silence=1800,
        ),
    )

    llm = AnthropicLLMService(api_key=settings.anthropic_api_key,
                              model=settings.live_model)
    tts = CartesiaTTSService(api_key=settings.cartesia_api_key,
                             voice_id=settings.cartesia_voice_id)

    context = OpenAILLMContext(
        messages=[{"role": "system", "content": build_inbound_prompt(ctx)}],
        tools=ToolsSchema(standard_tools=INBOUND_CALL_SCHEMAS),
    )
    context_aggregator = llm.create_context_aggregator(context)

    # ── transcript capture: in-memory for extraction + persisted for the dashboard
    transcript_turns: list[dict] = []
    turn_counter = {"n": 0}

    async def record_turn(speaker: str, text: str, final: bool):
        if not final:
            return
        spk = "supplier" if speaker == "user" else "agent"
        turn_counter["n"] += 1
        turn = {"speaker": spk, "text": text, "turn_no": turn_counter["n"]}
        transcript_turns.append(turn)
        await asyncio.to_thread(db.insert_transcript_turn, call_id,
                                turn["turn_no"], spk, text)

    pipeline = Pipeline([
        transport.input(),
        stt,
        TranscriptRelay("user", record_turn, include_interim=False),
        context_aggregator.user(),
        llm,
        tts,
        TranscriptRelay("agent", record_turn),
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

    # end_call tool: let the goodbye audio flush, then end the pipeline
    # (TwilioFrameSerializer hangs the call up on EndFrame).
    async def end_call(params: FunctionCallParams):
        await params.result_callback({"status": "ending the call now"})

        async def _hangup():
            await asyncio.sleep(4)  # let the goodbye TTS finish playing out
            await task.queue_frame(EndFrame())

        asyncio.create_task(_hangup())

    llm.register_function("end_call", end_call)

    # kick off the greeting the moment Twilio's audio stream is connected
    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        context.add_message({
            "role": "user",
            "content": "(The supplier has just answered the phone. Begin the call "
                       "now with your greeting.)",
        })
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    finally:
        logger.info("supplier call {} pipeline ended ({} turns)",
                    call_id, len(transcript_turns))
        # all writes happen here, post-call (extraction → confidence-gated PO update)
        await finalize_call(call_id, po_id, transcript_turns)
