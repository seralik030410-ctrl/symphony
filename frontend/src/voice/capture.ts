export interface CaptureOptions { mode: "compressed" | "pcm16"; sampleRate?: number; threshold?: number; silenceMs?: number }

export class VoiceCapture {
  private stream: MediaStream | null = null; private recorder: MediaRecorder | null = null;
  private pending: Promise<void>[] = []; private context: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null; private frame = 0;
  private heardSpeech = false; private quietSince = 0; mimeType = "audio/webm";

  static capabilities() { return { input_codecs: ["pcm16"], sample_rates: [24000, 16000] }; }

  async start(deviceId: string | null, onChunk: (chunk: ArrayBuffer) => void, onSilence?: () => void,
              options: CaptureOptions = { mode: "compressed" }): Promise<void> {
    if (this.recorder?.state === "recording" || this.processor) return;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId }, echoCancellation: true, noiseSuppression: true } : { echoCancellation: true, noiseSuppression: true } });
    this.heardSpeech = false; this.quietSince = 0;
    if (options.mode === "pcm16") this.startPcm(onChunk, onSilence, options); else this.startCompressed(onChunk, onSilence, options);
  }

  private startCompressed(onChunk: (chunk: ArrayBuffer) => void, onSilence: (() => void) | undefined, options: CaptureOptions) {
    const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find(value => MediaRecorder.isTypeSupported(value));
    this.recorder = preferred ? new MediaRecorder(this.stream!, { mimeType: preferred }) : new MediaRecorder(this.stream!);
    this.mimeType = this.recorder.mimeType || preferred || "audio/webm"; this.pending = [];
    this.recorder.ondataavailable = event => { if (event.data.size) this.pending.push(event.data.arrayBuffer().then(onChunk)); };
    this.recorder.start(250); if (onSilence) this.startAnalyser(onSilence, options.threshold ?? 0.025, options.silenceMs ?? 900);
  }

  private startPcm(onChunk: (chunk: ArrayBuffer) => void, onSilence: (() => void) | undefined, options: CaptureOptions) {
    const targetRate = options.sampleRate ?? 24000; this.mimeType = "audio/pcm"; this.context = new AudioContext();
    const source = this.context.createMediaStreamSource(this.stream!); this.processor = this.context.createScriptProcessor(4096, 1, 1);
    const silent = this.context.createGain(); silent.gain.value = 0; source.connect(this.processor); this.processor.connect(silent); silent.connect(this.context.destination);
    this.processor.onaudioprocess = event => {
      const sourceSamples = event.inputBuffer.getChannelData(0); const ratio = this.context!.sampleRate / targetRate;
      const length = Math.max(1, Math.floor(sourceSamples.length / ratio)); const bytes = new ArrayBuffer(length * 2); const pcm = new DataView(bytes); let energy = 0;
      for (let index = 0; index < length; index++) { const sample = Math.max(-1, Math.min(1, sourceSamples[Math.min(sourceSamples.length - 1, Math.floor(index * ratio))])); energy += sample * sample; pcm.setInt16(index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true); }
      onChunk(bytes); if (onSilence) this.checkSilence(Math.sqrt(energy / length), onSilence, options.threshold ?? 0.025, options.silenceMs ?? 900);
    };
  }

  private checkSilence(rms: number, onSilence: () => void, threshold: number, silenceMs: number) {
    if (rms >= threshold) { this.heardSpeech = true; this.quietSince = 0; }
    else if (this.heardSpeech) { this.quietSince ||= performance.now(); if (performance.now() - this.quietSince >= silenceMs) onSilence(); }
  }

  private startAnalyser(onSilence: () => void, threshold: number, silenceMs: number) {
    try { this.context = new AudioContext(); const source = this.context.createMediaStreamSource(this.stream!); const analyser = this.context.createAnalyser(); analyser.fftSize = 1024; source.connect(analyser); const samples = new Float32Array(analyser.fftSize);
      const inspect = () => { if (!this.recorder || this.recorder.state !== "recording") return; analyser.getFloatTimeDomainData(samples); const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length); this.checkSilence(rms, onSilence, threshold, silenceMs); this.frame = requestAnimationFrame(inspect); }; this.frame = requestAnimationFrame(inspect);
    } catch { /* Manual stop remains available. */ }
  }

  stop(): Promise<void> { return new Promise(resolve => { const recorder = this.recorder; if (!recorder || recorder.state === "inactive") { this.release(); resolve(); return; } recorder.addEventListener("stop", () => { void Promise.all(this.pending).finally(() => { this.release(); resolve(); }); }, { once: true }); recorder.stop(); }); }
  release(): void { if (this.processor) { this.processor.disconnect(); this.processor.onaudioprocess = null; this.processor = null; } this.stream?.getTracks().forEach(track => track.stop()); cancelAnimationFrame(this.frame); this.frame = 0; void this.context?.close(); this.context = null; this.stream = null; this.recorder = null; this.pending = []; }
}
