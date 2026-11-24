import { useEffect, useRef, useState } from "react";
import { checkSpeechAvailability } from "./speech.js";

export function useVoiceRecorder(onRecorded) {
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [levels, setLevels] = useState(() => Array(40).fill(0));
  const [seconds, setSeconds] = useState(0);
  const session = useRef(null);
  const generation = useRef(0);
  const callback = useRef(onRecorded);
  useEffect(() => {
    callback.current = onRecorded;
  }, [onRecorded]);

  function release(current) {
    clearInterval(current?.interval);
    current?.stream?.getTracks().forEach((track) => track.stop());
    current?.context?.close().catch(() => {});
  }
  function discard() {
    generation.current++;
    const current = session.current;
    session.current = null;
    if (current?.recorder) {
      current.recorder.onstop = null;
      current.recorder.ondataavailable = null;
      current.recorder.onerror = null;
      if (current.recorder.state !== "inactive") current.recorder.stop();
    }
    release(current);
  }
  useEffect(() => () => discard(), []);

  async function start() {
    if (session.current) return;
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError(
        "Запись недоступна. Откройте приложение через HTTPS или localhost в браузере с поддержкой микрофона.",
      );
      return;
    }
    const version = ++generation.current;
    const current = { chunks: [], samples: [] };
    session.current = current;
    setStatus("requesting");
    try {
      await checkSpeechAvailability();
      if (generation.current !== version) return;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: { ideal: 1 },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (generation.current !== version) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      current.stream = stream;
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      current.recorder = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) current.chunks.push(event.data);
      };
      recorder.onstop = () => {
        release(current);
        if (generation.current !== version) return;
        session.current = null;
        setStatus("idle");
        const blob = new Blob(current.chunks, {
          type: recorder.mimeType || current.chunks[0]?.type,
        });
        if (blob.size)
          callback.current(
            blob,
            Math.max(1, Math.round((Date.now() - current.started) / 1000)),
            current.samples,
          );
        else setError("Не удалось записать звук. Попробуйте ещё раз.");
      };
      recorder.onerror = () => {
        discard();
        setStatus("idle");
        setError("Запись прервалась. Попробуйте ещё раз.");
      };
      // Start capturing before awaiting the waveform analyser so first words aren't lost.
      current.started = Date.now();
      recorder.start(250);
      setSeconds(0);
      setLevels(Array(40).fill(0));
      setStatus("recording");
      try {
        const Context = window.AudioContext || window.webkitAudioContext;
        current.context = new Context();
        await current.context.resume();
        if (generation.current !== version) {
          release(current);
          return;
        }
        current.analyser = current.context.createAnalyser();
        current.analyser.fftSize = 256;
        current.context.createMediaStreamSource(stream).connect(current.analyser);
        current.data = new Uint8Array(current.analyser.frequencyBinCount);
      } catch {
        /* Recording remains available without the visual analyser. */
      }
      if (generation.current !== version) {
        release(current);
        return;
      }
      if (recorder.state !== "recording") return;
      current.interval = setInterval(() => {
        setSeconds(Math.floor((Date.now() - current.started) / 1000));
        if (current.analyser) {
          current.analyser.getByteTimeDomainData(current.data);
          const rms = Math.sqrt(
            current.data.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) /
              current.data.length,
          );
          const level = Math.min(1, rms * 8);
          current.samples.push(level);
          setLevels((previous) => [...previous.slice(1), level]);
        }
      }, 80);
    } catch (failure) {
      if (generation.current !== version) return;
      discard();
      setStatus("idle");
      setError(
        failure.name === "SpeechUnavailableError"
          ? failure.message
          : failure.name === "NotAllowedError"
            ? "Разрешите доступ к микрофону в настройках браузера и попробуйте снова."
            : failure.name === "NotFoundError"
              ? "Микрофон не найден."
              : "Не удалось включить микрофон. Проверьте, не занят ли он другим приложением.",
      );
    }
  }
  return {
    status,
    error,
    levels,
    seconds,
    start,
    stop() {
      const current = session.current;
      if (current?.recorder?.state === "recording") {
        setStatus("stopping");
        current.recorder.stop();
        clearInterval(current.interval);
        current.stream.getTracks().forEach((track) => track.stop());
      }
    },
    cancel() {
      discard();
      setStatus("idle");
    },
  };
}
