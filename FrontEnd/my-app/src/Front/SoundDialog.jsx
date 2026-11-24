import { useLayoutEffect, useRef, useState } from "react";
import { useDismissSheet } from "./useDismissSheet.js";
import SoundTimer from "./SoundTimer.jsx";
import DeviceStatus from "./DeviceStatus.jsx";
import { soundIcons } from "./soundAssets.js";
import soundOn from "./images/sound-on.png";
import soundOff from "./images/sound-off.png";

export default function SoundDialog({
  timer,
  sound,
  tracks,
  catalog,
  onChoose,
  onChange,
  onRetryCatalog,
  feedback,
  onRetry,
  onClose,
}) {
  const ref = useRef(null);
  const sheet = useDismissSheet(onClose);
  const [setting, setSetting] = useState(null);
  const playing = sound.volume > 0;
  const selected = tracks.find((track) => track.track_id === sound.track_id);
  useLayoutEffect(() => {
    const dialog = ref.current;
    const previous = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="sound-dialog"
      aria-labelledby="sound-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="sound-stage"
        onClick={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <div
          className="sound-orb-area"
          onClick={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
        >
          <button
            type="button"
            className="sound-orb"
            data-on={playing}
            aria-label="Закрыть выбор звука"
            onClick={onClose}
          >
            <img className="sound-orb-off" src={soundOff} alt="" />
            <img className="sound-orb-on" src={soundOn} alt="" />
          </button>
        </div>
        <section ref={sheet.panelRef} className="sound-panel">
          <button
            type="button"
            className="sound-sheet-handle sound-panel-handle"
            aria-label="Закрыть выбор звука"
            {...sheet.handlers}
          >
            <span />
          </button>
          <header className="sound-panel-header">
            <h2 id="sound-dialog-title">Звук</h2>
            <button
              type="button"
              className="sound-close"
              aria-label="Закрыть выбор звука"
              onClick={onClose}
            >
              ×
            </button>
          </header>
          <DeviceStatus
            feedback={catalog}
            saving="Загружаем список треков…"
            onRetry={onRetryCatalog}
          />
          <div className="sound-options" role="group" aria-label="Выбор звука">
            {tracks.map((track) => (
              <button
                type="button"
                className="sound-option"
                key={track.track_id}
                aria-pressed={playing && sound.track_id === track.track_id}
                onClick={() => onChoose(track.track_id)}
              >
                {soundIcons[track.track_id] && <img src={soundIcons[track.track_id]} alt="" />}
                <span>{track.title}</span>
              </button>
            ))}
          </div>
          <div className="sound-toolbar" role="group" aria-label="Настройки звука">
            <button type="button" aria-label="Таймер звука" onClick={() => setSetting("timer")}>
              <svg
                viewBox="0 0 32 32"
                width="32"
                height="32"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              >
                <path d="M14 2h4m-2 4v2" />
                <circle cx="16" cy="19" r="11" fill="currentColor" stroke="none" />
                <path d="m16 19 5-5" stroke="#4b3c30" />
              </svg>
            </button>
            <button type="button" aria-label="Громкость звука" onClick={() => setSetting("volume")}>
              <SoundToolIcon />
            </button>
          </div>
          <DeviceStatus feedback={feedback} saving="Сохраняем звук…" onRetry={onRetry} />
        </section>
      </div>
      {setting && (
        <SoundSettingSheet
          timer={timer}
          kind={setting}
          sound={sound}
          title={selected?.title ?? "Выбранный звук"}
          onChange={onChange}
          feedback={feedback}
          onRetry={onRetry}
          onClose={() => setSetting(null)}
        />
      )}
    </dialog>
  );
}

function SoundToolIcon() {
  return (
    <svg
      viewBox="0 0 32 32"
      width="32"
      height="32"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
    >
      <path d="M3 10h26M3 23h26M21 5v10M11 18v10" />
    </svg>
  );
}

function SoundSettingSheet({ timer, kind, sound, title, onChange, feedback, onRetry, onClose }) {
  const ref = useRef(null);
  const sheet = useDismissSheet(onClose);
  useLayoutEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="sound-settings-dialog"
      aria-labelledby="sound-setting-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section ref={sheet.panelRef} className="sound-settings-sheet" data-kind={kind}>
        <button
          type="button"
          className="sound-sheet-handle"
          aria-label="Закрыть настройки звука"
          {...sheet.handlers}
        >
          <span />
        </button>
        <h2 id="sound-setting-title">{kind === "timer" ? "Таймер" : "Громкость"}</h2>
        {kind === "timer" ? (
          <SoundTimer timer={timer} />
        ) : (
          <>
            <div className="sound-volume-control" style={{ "--volume": sound.volume + "%" }}>
              <span aria-hidden="true">{title}</span>
              <input
                autoFocus
                type="range"
                min="0"
                max="100"
                step="1"
                value={sound.volume}
                aria-label="Громкость звука"
                aria-valuetext={sound.volume + "%"}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  onChange((current) => ({ ...current, volume: value }));
                }}
              />
            </div>
          </>
        )}
        <DeviceStatus feedback={feedback} saving="Сохраняем…" onRetry={onRetry} />
      </section>
    </dialog>
  );
}
