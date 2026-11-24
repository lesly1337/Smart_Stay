import { useRef, useState } from "react";

const formatTime = (value) =>
  `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`;

export default function VoiceMessage({ message }) {
  const audio = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [error, setError] = useState("");
  const samples = message.samples || [];
  const bars = Array.from({ length: 32 }, (_, index) => {
    const start = Math.floor((index * samples.length) / 32);
    const end = Math.max(start + 1, Math.floor(((index + 1) * samples.length) / 32));
    return Math.max(0.07, ...samples.slice(start, end));
  });
  async function toggle() {
    if (!audio.current.paused) {
      audio.current.pause();
      return;
    }
    setError("");
    try {
      await audio.current.play();
    } catch {
      setError("Не удалось воспроизвести запись");
    }
  }
  return (
    <div className="voice-message">
      <audio
        ref={audio}
        preload="auto"
        src={message.audio}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setPosition(0);
        }}
        onTimeUpdate={() => setPosition(audio.current.currentTime)}
      />
      <button
        type="button"
        className="voice-message-play"
        onClick={toggle}
        aria-label={
          playing ? "Приостановить голосовое сообщение" : "Воспроизвести голосовое сообщение"
        }
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          {playing ? <path d="M7 5h4v14H7zm6 0h4v14h-4z" /> : <path d="M8 4v16l12-8z" />}
        </svg>
      </button>
      <div className="voice-message-content">
        <div className="voice-message-wave" aria-hidden="true">
          {bars.map((height, index) => (
            <span
              key={index}
              data-played={position / message.duration > index / bars.length}
              style={{ height: `${4 + height * 22}px` }}
            />
          ))}
        </div>
        <span className="voice-message-time">
          {formatTime(position > 0 ? position : message.duration)}
        </span>
      </div>
      {message.transcript && <span className="voice-transcript">{message.transcript}</span>}
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
