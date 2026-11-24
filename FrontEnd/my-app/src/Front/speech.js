export async function checkSpeechAvailability() {
  const base = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(base + "/speech/status", { signal: controller.signal });
    if (!response.ok)
      throw new Error("Сервис голосового ввода недоступен. Напишите сообщение текстом.");
    const status = await response.json();
    if (!status.enabled)
      throw new Error("Голосовой ввод на этом сервере отключён. Напишите сообщение текстом.");
  } catch (error) {
    const failure = new Error(
      error.name === "AbortError"
        ? "Сервис голосового ввода не отвечает. Напишите сообщение текстом."
        : error.message,
    );
    failure.name = "SpeechUnavailableError";
    throw failure;
  } finally {
    clearTimeout(timeout);
  }
}

// Decode browser recordings and send a portable PCM WAV to local Whisper.
export async function transcribeVoice(blob) {
  const Context = window.AudioContext || window.webkitAudioContext;
  const context = new Context();
  let decoded;
  try {
    decoded = await context.decodeAudioData(await blob.arrayBuffer());
  } finally {
    await context.close();
  }
  if (decoded.duration > 120) throw new Error("Запишите сообщение короче двух минут.");
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const pcm = (await offline.startRendering()).getChannelData(0);
  const bytes = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(bytes);
  const label = (offset, text) =>
    [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  label(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  label(8, "WAVE");
  label(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  label(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  pcm.forEach((value, i) => {
    const sample = Math.max(-1, Math.min(1, value));
    view.setInt16(44 + i * 2, sample * (sample < 0 ? 32768 : 32767), true);
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);
  try {
    const base = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
    const response = await fetch(base + "/speech/transcribe", {
      method: "POST",
      headers: { "Content-Type": "audio/wav" },
      body: bytes,
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        typeof result.detail === "string" ? result.detail : "Не удалось распознать запись.",
      );
    if (typeof result.text !== "string" || !result.text.trim())
      throw new Error("Речь не распознана.");
    return result.text.trim();
  } finally {
    clearTimeout(timeout);
  }
}
