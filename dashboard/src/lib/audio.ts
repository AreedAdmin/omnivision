// Audio plumbing for the in-app voice channel.
// Mic: AudioWorklet (Float32 @ context rate) → downsample → Int16 PCM @ 16 kHz → WS
// Playback: Int16 PCM @ 16 kHz ← WS, scheduled gaplessly via AudioContext.

export const TARGET_RATE = 16000;

export function downsampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === TARGET_RATE) return input;
  const ratio = inputRate / TARGET_RATE;
  const outLength = Math.floor(input.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = pos - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac; // linear interpolation
  }
  return out;
}

export function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/** Gapless PCM16 player — schedules incoming chunks back-to-back. */
export class PCMPlayer {
  private ctx: AudioContext;
  private nextTime = 0;
  private sources = new Set<AudioBufferSourceNode>();

  constructor(ctx: AudioContext) {
    this.ctx = ctx;
  }

  play(buf: ArrayBuffer) {
    const i16 = new Int16Array(buf);
    if (i16.length === 0) return;
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;

    const audioBuffer = this.ctx.createBuffer(1, f32.length, TARGET_RATE);
    audioBuffer.getChannelData(0).set(f32);

    const src = this.ctx.createBufferSource();
    src.buffer = audioBuffer;
    src.connect(this.ctx.destination);
    const startAt = Math.max(this.ctx.currentTime + 0.02, this.nextTime);
    src.start(startAt);
    this.nextTime = startAt + audioBuffer.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }

  /** Barge-in: drop everything queued. */
  flush() {
    this.sources.forEach((s) => {
      try { s.stop(); } catch { /* already stopped */ }
    });
    this.sources.clear();
    this.nextTime = 0;
  }

  /** True while scheduled audio is still playing (used for half-duplex). */
  isPlaying(): boolean {
    return this.ctx.currentTime < this.nextTime - 0.05;
  }
}

export interface MicSession {
  setSending(on: boolean): void;
  close(): void;
  ctx: AudioContext;
}

/** Start the mic graph; onChunk receives Int16 PCM @16k while sending is on. */
export async function startMic(onChunk: (chunk: Int16Array) => void): Promise<MicSession> {
  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("/pcm-worklet.js");
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
  });

  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm-processor");
  // keep the graph alive without audible monitoring
  const mute = ctx.createGain();
  mute.gain.value = 0;
  source.connect(node);
  node.connect(mute);
  mute.connect(ctx.destination);

  let sending = false;
  node.port.onmessage = (e: MessageEvent<Float32Array>) => {
    if (!sending) return;
    const ds = downsampleTo16k(e.data, ctx.sampleRate);
    onChunk(floatToInt16(ds));
  };

  return {
    setSending: (on: boolean) => { sending = on; },
    close: () => {
      try { node.disconnect(); source.disconnect(); } catch { /* noop */ }
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
    ctx,
  };
}
