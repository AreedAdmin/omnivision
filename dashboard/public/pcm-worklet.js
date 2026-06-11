// AudioWorklet: forwards raw Float32 mic frames to the main thread.
// Downsampling to 16 kHz + Int16 conversion happens in lib/audio.ts.
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length > 0) {
      // copy — the underlying buffer is reused by the audio thread
      this.port.postMessage(channel.slice(0));
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
