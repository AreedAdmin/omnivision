"""Channel B (LOCAL MODE) — simulated supplier call over a browser mic.

Plan change: no Twilio number available, so the supplier call runs locally —
the "supplier" (a teammate) answers in the browser; their mic is the supplier
side of the call. Identical to the telephony pipeline in every other respect:
same inbound call persona, same transcript persistence, same post-call
extraction → confidence-gated PO update. Twilio telephony remains the
deployment story (pipelines/telephony.py is kept for it).
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
from serializers import RawPCMSerializer

SAMPLE_RATE = 16000  # browser channel — same as in-app


async def run_local_call_session(websocket: WebSocket, ctx: dict) -> None:
    """ctx comes from calls.CALL_CONTEXTS — created by /calls/initiate."""
    call_id = ctx["call_id"]
    po_id = ctx["po_id"]
    logger.info("starting LOCAL supplier call call_id={} po={}", call_id, ctx["po_number"])

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
        vad_force_turn_endpoint=False,
        connection_params=AssemblyAIConnectionParams(
            end_of_turn_confidence_threshold=0.7,
            # call pacing: shorter silence so the conversation never feels dead
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

    # transcript: in-memory for extraction + persisted rows for the dashboard
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
    async def end_call(params: FunctionCallParams):
        await params.result_callback({"status": "ending the call now"})

        async def _hangup():
            await asyncio.sleep(4)  # let the goodbye TTS finish playing out
            await task.queue_frame(EndFrame())

        asyncio.create_task(_hangup())

    llm.register_function("end_call", end_call)

    # greet the moment the "supplier" answers (WS audio connects)
    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        context.add_message({
            "role": "user",
            "content": "(The supplier has just answered the call. Begin now "
                       "with your greeting.)",
        })
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    finally:
        logger.info("local supplier call {} ended ({} turns)",
                    call_id, len(transcript_turns))
        # all writes happen here, post-call (extraction → confidence-gated PO update)
        await finalize_call(call_id, po_id, transcript_turns)
