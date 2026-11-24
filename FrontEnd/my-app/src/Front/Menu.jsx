import { updateRoomSetting } from "./roomSettings.js";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  positionLightCard,
  closeAnimatedCard,
  useBrightnessWheel,
  controlIcons,
  alarmModes,
  setAlarmTimePart,
  useChatSheetDrag,
} from "./Menu.js";
import "./Menu.css";
import { useSoundTimer } from "./useSoundTimer.js";
import { useVoiceRecorder } from "./useVoiceRecorder.js";
import { transcribeVoice } from "./speech.js";
import { openInteractiveSession, sendGuestCommand } from "./api.js";
import VoiceMessage from "./VoiceMessage.jsx";
import { useGuestPlan } from "./useGuestPlan.js";
import PlanExplanation from "./PlanExplanation.jsx";
import GuestSelect from "./GuestSelect.jsx";
import SoundDialog from "./SoundDialog.jsx";
import AlarmTimePicker from "./AlarmTimePicker.jsx";
import DeviceStatus from "./DeviceStatus.jsx";
import { useRoomSettings } from "./useRoomSettings.js";
import { useSimulatorSettings } from "./useSimulatorSettings.js";
import voiceMic from "./images/microphone-voice-input.svg";
import soundOnImage from "./images/sound-on.png";
import soundTimerWave from "./images/sound-timer-wave.png";
import soundOffImage from "./images/sound-off.png";

export default function RoomMenu() {
  const [expandedDevice, setExpandedDevice] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Привет! Помогу настроить номер.\nНапример скажи «сделай теплее» или «выключи свет».",
    },
  ]);
  const voiceUrls = useRef([]);
  const [speechPending, setSpeechPending] = useState(0);
  const speechCommand = useRef(null);
  const voice = useVoiceRecorder(async (blob, duration, samples) => {
    const audio = URL.createObjectURL(blob);
    voiceUrls.current.push(audio);
    setMessages((current) => [...current, { role: "user", audio, duration, samples }]);
    setSpeechPending((count) => count + 1);
    try {
      const text = await transcribeVoice(blob);
      setMessages((current) =>
        current.map((message) =>
          message.audio === audio ? { ...message, transcript: text } : message,
        ),
      );
      await speechCommand.current?.(text);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text:
            error.name === "AbortError"
              ? "Распознавание заняло слишком много времени. Попробуйте ещё раз."
              : error.message || "Не удалось распознать голос.",
        },
      ]);
    } finally {
      setSpeechPending((count) => count - 1);
    }
  });
  useEffect(() => {
    const urls = voiceUrls.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.length = 0;
    };
  }, []);
  function openVoiceChat() {
    setChatOpen(true);
    voice.start();
  }
  function clearConversation() {
    voice.cancel();
    setMessages([]);
    setCommand("");
    voiceUrls.current.forEach((url) => URL.revokeObjectURL(url));
    voiceUrls.current.length = 0;
  }
  function closeChat() {
    voice.cancel();
    setChatOpen(false);
  }
  const [command, setCommand] = useState("");
  const [activeTab, setActiveTab] = useState("room");
  const [lightExpanded, setLightExpanded] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [commandPending, setCommandPending] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const sending = useRef(false);
  const guestPlan = useGuestPlan();
  const simulator = useSimulatorSettings(commandPending || guestPlan.busy);
  const soundTimer = useSoundTimer(
    (update) => simulator.change("sound", update, true),
    simulator.confirmed?.sound,
    simulator.writes.sound,
  );
  const { settings, setSettings, status: apiStatus, retry: retryApi } = useRoomSettings(simulator);

  const devices = simulator.draft;
  const actual = simulator.confirmed;
  const selectedTrack = simulator.tracks.find(
    (track) => track.track_id === devices?.sound.track_id,
  );
  const plan = guestPlan.plan;
  const schedule = plan?.periods ?? [];
  const writesPending = Object.values(simulator.writes).some((write) => write.status === "saving");
  const actionBusy =
    guestPlan.busy ||
    commandPending ||
    speechPending > 0 ||
    voice.status !== "idle" ||
    writesPending;
  const temperature = devices ? Math.round(devices.climate.temperature) : undefined;
  const curtainsOpen = devices?.curtains.position > 0;
  const soundOn = devices?.sound.volume > 0;
  const alarm = devices?.alarm;
  const dnd = devices?.dnd.enabled;

  useEffect(() => {
    const unavailable = (event) => setSessionError(event.detail);
    window.addEventListener("room-session-unavailable", unavailable);
    return () => window.removeEventListener("room-session-unavailable", unavailable);
  }, []);
  async function renewSession() {
    try {
      await openInteractiveSession(true);
      window.location.reload();
    } catch (error) {
      setSessionError(error.message);
    }
  }
  async function processCommand(text) {
    if (guestPlan.busy || sending.current || writesPending || !devices) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: "Дождитесь загрузки и сохранения текущих настроек, затем повторите просьбу.",
        },
      ]);
      return;
    }
    sending.current = true;
    setCommandPending(true);
    try {
      const answer = await sendGuestCommand(text, crypto.randomUUID());
      setMessages((current) => [
        ...current,
        ...answer.replies.map((reply) => ({ role: "assistant", text: reply.text })),
      ]);
      await simulator.refresh();
      if (answer.confirmed_settings?.sound?.timer_minutes !== undefined)
        soundTimer.confirm(answer.confirmed_settings.sound.timer_minutes);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", text: error.message }]);
      await simulator.refresh().catch(() => {});
    } finally {
      sending.current = false;
      setCommandPending(false);
    }
  }

  useEffect(() => {
    speechCommand.current = processCommand;
  });

  function sendChatMessage() {
    const text = command.trim();
    if (!text) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setCommand("");
    void processCommand(text);
  }

  function updateSetting(name, value) {
    setSettings((current) => updateRoomSetting(current, name, value));
  }

  function stepTemperature(delta) {
    simulator.change("climate", (current) => ({
      temperature: Math.max(16, Math.min(26, Math.round(current.temperature) + delta)),
    }));
  }

  return (
    <div
      className="room-app"
      data-theme="dark"
      data-tab={activeTab}
      data-light-expanded={lightExpanded || Boolean(expandedDevice)}
    >
      <main className="room-main">
        <header className="screen-header">
          <h1 className="page-title">{activeTab === "room" ? "Мой номер" : "Управление"}</h1>
        </header>
        {sessionError && (
          <div className="api-status" role="alert">
            <p>{sessionError}</p>
            <button type="button" onClick={renewSession}>
              Создать новый сеанс
            </button>
          </div>
        )}
        {guestPlan.error && (
          <p className="plan-error" role="alert">
            {guestPlan.error}
          </p>
        )}
        {activeTab === "controls" && (
          <>
            {!["ready", "saved"].includes(apiStatus) && (
              <div
                className="api-status"
                role="status"
                data-error={apiStatus === "error" || apiStatus === "load-error"}
              >
                {apiStatus === "loading"
                  ? "Загружаем настройки…"
                  : apiStatus === "saving"
                    ? "Сохраняем свет…"
                    : apiStatus === "error"
                      ? "Не удалось сохранить свет."
                      : apiStatus === "load-error"
                        ? "Бэкенд недоступен. Проверьте сервер на порту 8000."
                        : apiStatus === "saved"
                          ? "Свет сохранён"
                          : "Настройки загружены"}
                {(apiStatus === "error" || apiStatus === "load-error") && (
                  <button type="button" onClick={retryApi}>
                    Повторить
                  </button>
                )}
              </div>
            )}
            <DeviceStatus
              feedback={simulator.load}
              saving="Загружаем состояние номера из симулятора…"
              onRetry={simulator.retryLoad}
            />
          </>
        )}

        {activeTab === "room" ? (
          <>
            <section className="room-card" aria-label="Ваш номер">
              <p className="hotel-name">Ваш отдых</p>
              <h2 className="room-number">{plan?.stay.label ?? "Ваш номер"}</h2>
              <p className="stay-dates">
                {plan ? formatStayDates(plan.stay) : "Загружаем данные гостя…"}
              </p>
              {guestPlan.guests.length > 1 && (
                <GuestSelect
                  guests={guestPlan.guests}
                  value={plan?.stay.record_id ?? ""}
                  disabled={actionBusy || !plan}
                  formatDates={formatStayDates}
                  onChange={(id) => {
                    clearConversation();
                    guestPlan.select(id);
                  }}
                />
              )}
            </section>

            <section className="schedule" aria-labelledby="schedule-title">
              <h2 id="schedule-title" className="section-title">
                Ваш план отдыха
              </h2>
              <p className="section-subtitle">
                {plan?.personalization === "history"
                  ? "По вашей анкете и истории"
                  : "По анкете гостя"}
              </p>

              <DeviceStatus
                feedback={guestPlan.load}
                saving="Готовим план по анкете…"
                onRetry={guestPlan.retry}
              />
              {plan && (
                <>
                  <p className="schedule-updated">
                    Подготовлен в {formatClock(plan.updated_at, plan.stay.hotel_timezone)}
                  </p>
                  <p className="plan-state" role="status">
                    {plan.status === "applied"
                      ? "План загружен в симулятор"
                      : "План подготовлен. Примените его к номеру."}
                  </p>
                  <p className="plan-simulator-clock">
                    Время симулятора: {formatClock(plan.session.at, plan.stay.hotel_timezone)}
                  </p>
                </>
              )}
              <ol className="schedule-list">
                {schedule.map((item) => (
                  <li
                    key={item.id}
                    data-period={item.id}
                    className={`schedule-card schedule-card--${item.tone}`}
                  >
                    <div
                      className={`schedule-time ${
                        item.times.length > 1 ? "schedule-time--range" : ""
                      }`}
                      aria-label={item.timeLabel}
                    >
                      {item.times.map((time) => (
                        <span key={time}>{time}</span>
                      ))}
                    </div>

                    <div className="schedule-description">
                      <h3>{item.title}</h3>
                      {item.details.map((detail) => (
                        <p key={detail}>{detail}</p>
                      ))}
                    </div>
                  </li>
                ))}
              </ol>

              {plan && (
                <div className="plan-actions">
                  <button
                    type="button"
                    className="plan-apply"
                    disabled={actionBusy}
                    onClick={guestPlan.apply}
                  >
                    {guestPlan.busy
                      ? "Подождите…"
                      : plan.status === "applied"
                        ? "Применить план снова"
                        : "Применить план"}
                  </button>
                  <button
                    type="button"
                    className="plan-personalize"
                    disabled={actionBusy || plan.personalization === "history"}
                    onClick={guestPlan.personalize}
                  >
                    {plan.personalization === "history"
                      ? "История гостя учтена"
                      : "Учесть привычки из истории"}
                  </button>
                  {plan.personalization === "profile" && (
                    <p>
                      История учитывается по запросу. До этого используются анкета и отмеченные в
                      пояснении допущения.
                    </p>
                  )}
                </div>
              )}
              <button
                type="button"
                disabled={!plan}
                className="explanation-toggle"
                aria-expanded={expanded}
                aria-controls={expanded ? "settings-explanation" : undefined}
                aria-haspopup="dialog"
                onClick={() => setExpanded((value) => !value)}
              >
                <span>Почему такие настройки?</span>
                <svg
                  className={expanded ? "chevron chevron--open" : "chevron"}
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="m9 5 7 7-7 7"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </section>
          </>
        ) : (
          <fieldset
            className="device-controls"
            aria-label="Управление номером"
            disabled={guestPlan.busy || commandPending}
            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
          >
            <section className="climate-card climate-card--inline" aria-label="Климат">
              <h2 className="preview-title">Климат</h2>
              <span className="climate-caption">
                {actual
                  ? `Установлено ${Math.round(actual.climate.temperature)} °C`
                  : "По умолчанию"}
              </span>
              <div className="temperature-controls">
                <button
                  type="button"
                  className="climate-disc"
                  aria-label="Уменьшить температуру"
                  disabled={temperature === undefined || temperature <= 16}
                  onClick={() => stepTemperature(-1)}
                >
                  −
                </button>
                <output className="temperature-value" aria-live="polite">
                  {temperature ?? 20}
                  <sup>°</sup>
                </output>
                <button
                  type="button"
                  className="climate-disc"
                  aria-label="Увеличить температуру"
                  disabled={temperature === undefined || temperature >= 26}
                  onClick={() => stepTemperature(1)}
                >
                  +
                </button>
              </div>
              <input
                className="temperature-slider"
                aria-label="Температура"
                aria-valuetext={
                  temperature === undefined ? "20 °C, начальное значение" : temperature + " °C"
                }
                type="range"
                min="16"
                max="26"
                step="1"
                disabled={temperature === undefined}
                value={temperature ?? 20}
                onChange={(event) =>
                  simulator.change("climate", () => ({ temperature: Number(event.target.value) }))
                }
              />
              <DeviceStatus
                feedback={simulator.writes.climate}
                saving="Сохраняем температуру…"
                onRetry={() => simulator.retryDevice("climate")}
              />
            </section>
            <div className="device-grid">
              <button
                type="button"
                className="device-card light-card-preview"
                disabled={!devices}
                data-active={settings.lightOn}
                aria-haspopup="dialog"
                aria-expanded={lightExpanded}
                onClick={() => setLightExpanded(true)}
              >
                <span className="device-heading">
                  <span>Свет</span>
                  <PreviewSwitch checked={settings.lightOn} />
                </span>
                <span className="device-value">{settings.lightOn ? settings.brightness : 0}%</span>
                <span className="device-caption">
                  {settings.lightTone === "cool" ? "Холодный" : "Теплый"}
                </span>
              </button>
              <button
                type="button"
                className="device-card device-preview curtains-card"
                data-active={curtainsOpen}
                role="switch"
                aria-label="Шторы"
                aria-checked={curtainsOpen}
                disabled={!devices}
                onClick={() =>
                  simulator.change("curtains", (curtains) => ({
                    position: curtains.position > 0 ? 0 : 100,
                  }))
                }
              >
                <span className="device-heading">
                  <span>Шторы</span>
                  <PreviewSwitch checked={curtainsOpen} />
                </span>
                <span className="device-value curtains-value">
                  {curtainsOpen ? "Открыты" : "Закрыты"}
                </span>
              </button>
              <button
                type="button"
                className="device-card device-preview sound-card"
                data-device="sound"
                data-active={soundOn}
                aria-haspopup="dialog"
                disabled={!devices}
                onClick={() => setExpandedDevice("sound")}
              >
                <span className="preview-title">Звук</span>
                <span
                  className="sound-preview-orb"
                  data-on={soundOn || soundTimer.running}
                  data-timer={soundTimer.running}
                >
                  <img className="sound-preview-off" src={soundOffImage} alt="" />
                  <img className="sound-preview-on" src={soundOnImage} alt="" />
                  {soundTimer.running && (
                    <span className="sound-timer-waves" aria-hidden="true">
                      <svg className="sound-wave-filter" width="0" height="0">
                        <defs>
                          <filter
                            id="sound-timer-ripple"
                            x="-15%"
                            y="-15%"
                            width="130%"
                            height="130%"
                            colorInterpolationFilters="sRGB"
                          >
                            <feTurbulence
                              type="fractalNoise"
                              baseFrequency="0.035"
                              numOctaves="2"
                              seed="8"
                              result="noise"
                            />
                            <feDisplacementMap
                              in="SourceGraphic"
                              in2="noise"
                              scale="7"
                              xChannelSelector="R"
                              yChannelSelector="G"
                            />
                          </filter>
                        </defs>
                      </svg>
                      <img
                        className="sound-timer-wave sound-timer-wave--back"
                        src={soundTimerWave}
                        alt=""
                      />
                      <img
                        className="sound-timer-wave sound-timer-wave--front"
                        src={soundTimerWave}
                        alt=""
                      />
                    </span>
                  )}
                  {soundTimer.running && (
                    <span
                      className="sound-preview-timer"
                      role="timer"
                      aria-label="Оставшееся время таймера звука"
                      data-long={soundTimer.remaining >= 6000}
                    >
                      {String(Math.floor(soundTimer.remaining / 60)).padStart(2, "0")}:
                      {String(soundTimer.remaining % 60).padStart(2, "0")}
                    </span>
                  )}
                </span>
                <span className="sound-caption">
                  {soundOn ? (selectedTrack?.title ?? "Включён") : "Выключен"}
                </span>
              </button>
              <button
                type="button"
                className="device-card device-preview"
                data-device="alarm"
                data-active={alarm?.enabled ?? false}
                aria-haspopup="dialog"
                disabled={!alarm}
                onClick={() => setExpandedDevice("alarm")}
              >
                <span className="preview-title">Будильник</span>
                <span className="alarm-row">
                  <span className="device-value">{alarm?.time ?? "00:00"}</span>
                  <PreviewSwitch checked={alarm?.enabled ?? false} />
                </span>
                <span className="device-caption">
                  {alarm
                    ? alarmModes.find((mode) => mode.value === alarm.mode)?.caption
                    : "Выключен"}
                </span>
              </button>
            </div>
            <DeviceStatus
              feedback={simulator.writes.curtains}
              saving="Сохраняем положение штор…"
              onRetry={() => simulator.retryDevice("curtains")}
            />
            {expandedDevice !== "sound" && (
              <DeviceStatus
                feedback={simulator.writes.sound}
                saving="Сохраняем звук…"
                onRetry={() => simulator.retryDevice("sound")}
              />
            )}
            {expandedDevice !== "alarm" && (
              <DeviceStatus
                feedback={simulator.writes.alarm}
                saving="Сохраняем будильник…"
                onRetry={() => simulator.retryDevice("alarm")}
              />
            )}
            <button
              type="button"
              className="quiet-card device-preview"
              data-active={dnd ?? false}
              role="switch"
              aria-checked={dnd ?? false}
              disabled={!devices}
              onClick={() => simulator.change("dnd", (mode) => ({ enabled: !mode.enabled }))}
            >
              <span>Не беспокоить</span>
              <PreviewSwitch checked={dnd ?? false} />
            </button>
            <DeviceStatus
              feedback={simulator.writes.dnd}
              saving="Сохраняем режим «Не беспокоить»…"
              onRetry={() => simulator.retryDevice("dnd")}
            />
            <form
              className="room-command"
              onSubmit={(event) => {
                event.preventDefault();
                setChatOpen(true);
                sendChatMessage();
              }}
            >
              <span className="voice-wave voice-wave--animated" aria-hidden="true">
                {Array.from({ length: 7 }, (_, index) => (
                  <span className="voice-wave-bar" key={index} />
                ))}
              </span>
              <label className="visually-hidden" htmlFor="room-command-input">
                Что изменить?
              </label>
              <div className="command-input-wrap">
                <input
                  id="room-command-input"
                  value={command}
                  onChange={(event) => {
                    setCommand(event.target.value);
                    if (event.target.value) setChatOpen(true);
                  }}
                  placeholder="Хотите что то изменить?"
                  required
                />
                <button type="submit" aria-label="Применить текстовую команду">
                  <ControlIcon name="arrow" />
                </button>
                <button
                  type="button"
                  className="voice-input-button"
                  aria-label="Голосовой ввод"
                  onClick={openVoiceChat}
                >
                  <img src={voiceMic} alt="" />
                </button>
              </div>
            </form>
          </fieldset>
        )}
      </main>

      <nav className="bottom-nav" aria-label="Основная навигация">
        <button
          type="button"
          className={`nav-button ${activeTab === "room" ? "nav-button--active" : ""}`}
          aria-current={activeTab === "room" ? "page" : undefined}
          onClick={() => setActiveTab("room")}
        >
          <ControlIcon name="home" />
          Мой номер
        </button>
        <button
          type="button"
          className={`nav-button ${activeTab === "controls" ? "nav-button--active" : ""}`}
          aria-current={activeTab === "controls" ? "page" : undefined}
          onClick={() => setActiveTab("controls")}
        >
          <ControlIcon name="controls" />
          Управление
        </button>
      </nav>
      {expanded && (
        <PlanExplanation
          error={guestPlan.error}
          plan={plan}
          tracks={simulator.tracks}
          busy={actionBusy}
          onApply={guestPlan.apply}
          onClose={() => setExpanded(false)}
        />
      )}
      {chatOpen && (
        <AssistantChat
          voice={voice}
          pending={commandPending || speechPending > 0 || writesPending || apiStatus === "saving"}
          messages={messages}
          draft={command}
          setDraft={setCommand}
          onSend={sendChatMessage}
          onClose={closeChat}
        />
      )}
      {expandedDevice === "sound" && devices && (
        <SoundDialog
          timer={soundTimer}
          sound={devices.sound}
          tracks={simulator.tracks}
          catalog={simulator.catalog}
          onChoose={simulator.chooseSound}
          onChange={(update) => simulator.change("sound", update)}
          onRetryCatalog={simulator.retryCatalog}
          feedback={simulator.writes.sound}
          onRetry={() => simulator.retryDevice("sound")}
          onClose={() => setExpandedDevice(null)}
        />
      )}
      {expandedDevice === "alarm" && alarm && (
        <AlarmDialog
          alarm={alarm}
          onChange={(update) => simulator.change("alarm", update)}
          feedback={simulator.writes.alarm}
          onRetry={() => simulator.retryDevice("alarm")}
          onClose={() => setExpandedDevice(null)}
        />
      )}
      {lightExpanded && (
        <LightDialog
          settings={settings}
          updateSetting={updateSetting}
          onClose={() => setLightExpanded(false)}
        />
      )}
    </div>
  );
}

function DeviceSwitch({ label, checked, onChange }) {
  return (
    <button
      type="button"
      className="device-switch"
      role="switch"
      aria-label={label}
      aria-checked={checked}
      onClick={() => onChange(!checked)}
    >
      <span aria-hidden="true" />
    </button>
  );
}

function LightDialog({ settings, updateSetting, onClose }) {
  const dialogRef = useRef(null);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    dialog.showModal();
    const reposition = () =>
      positionLightCard(dialog, document.querySelector(".light-card-preview"));
    reposition();
    window.addEventListener("resize", reposition);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("resize", reposition);
      dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const wheel = useBrightnessWheel(settings.brightness, (value) =>
    updateSetting("brightness", value),
  );

  return (
    <dialog
      ref={dialogRef}
      className="light-dialog"
      aria-labelledby="light-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        closeAnimatedCard(dialogRef.current, onClose);
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) closeAnimatedCard(dialogRef.current, onClose);
      }}
    >
      <section className="light-expanded-card" data-active={settings.lightOn}>
        <div className="device-heading">
          <h2 id="light-dialog-title">Свет</h2>
          <DeviceSwitch
            label="Свет"
            checked={settings.lightOn}
            onChange={(value) => updateSetting("lightOn", value)}
          />
        </div>
        <div
          className="brightness-wheel"
          data-off={!settings.lightOn}
          role="slider"
          tabIndex={0}
          aria-label="Яркость света"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={settings.brightness}
          aria-valuetext={settings.brightness + "%"}
          {...wheel}
        >
          {Array.from({ length: 11 }, (_, index) => index * 10).map((value) => (
            <span
              key={value}
              className="brightness-wheel-value"
              data-selected={value === settings.brightness}
              aria-hidden="true"
            >
              {value}
            </span>
          ))}
        </div>
        <div className="brightness-wheel-dots" aria-hidden="true">
          {Array.from({ length: 25 }, (_, index) => (
            <span key={index} />
          ))}
        </div>
        <div className="light-tone-picker" role="group" aria-label="Температура света">
          <button
            type="button"
            aria-pressed={settings.lightTone !== "cool"}
            onClick={() => updateSetting("lightTone", "warm")}
          >
            Теплый
          </button>
          <button
            type="button"
            aria-pressed={settings.lightTone === "cool"}
            onClick={() => updateSetting("lightTone", "cool")}
          >
            Холодный
          </button>
        </div>
      </section>
    </dialog>
  );
}

function ControlIcon({ name }) {
  return (
    <svg
      className="control-icon"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={controlIcons[name]} />
    </svg>
  );
}

function PreviewSwitch({ checked }) {
  return <span className="light-preview-switch" data-on={checked} aria-hidden="true" />;
}

function AlarmDialog({ alarm, onChange, feedback, onRetry, onClose }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const dialog = ref.current;
    const previous = document.body.style.overflow;
    dialog.showModal();
    const position = () =>
      positionLightCard(dialog, document.querySelector('[data-device="alarm"]'));
    position();
    document.body.style.overflow = "hidden";
    window.addEventListener("resize", position);
    return () => {
      window.removeEventListener("resize", position);
      dialog.close();
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="light-dialog"
      aria-labelledby="alarm-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        closeAnimatedCard(ref.current, onClose);
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) closeAnimatedCard(ref.current, onClose);
      }}
    >
      <section
        className="light-expanded-card expanded-device-card"
        data-kind="alarm"
        data-active={alarm.enabled}
      >
        <div className="expanded-device-heading">
          <h2 id="alarm-dialog-title">Будильник</h2>
          <DeviceSwitch
            label="Будильник"
            checked={alarm.enabled}
            onChange={(enabled) => onChange((current) => ({ ...current, enabled }))}
          />
        </div>
        <AlarmTimePicker
          value={alarm.time}
          onChange={(part, number) =>
            onChange((current) => ({
              ...current,
              time: setAlarmTimePart(current.time, part, number),
            }))
          }
        />
        <div className="alarm-mode-picker" role="group" aria-label="Режим будильника">
          {alarmModes.map((mode) => (
            <button
              type="button"
              key={mode.value}
              aria-pressed={alarm.mode === mode.value}
              onClick={() => onChange((current) => ({ ...current, mode: mode.value }))}
            >
              {mode.label}
            </button>
          ))}
        </div>
        <DeviceStatus feedback={feedback} saving="Сохраняем будильник…" onRetry={onRetry} />
      </section>
    </dialog>
  );
}

function AssistantChat({ messages, draft, setDraft, onSend, onClose, pending, voice }) {
  const dialogRef = useRef(null);
  const inputRef = useRef(null);
  const historyRef = useRef(null);
  const sheet = useChatSheetDrag(onClose);
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const sync = () => {
      const dialog = dialogRef.current;
      dialog.style.height = viewport.height + "px";
      dialog.style.top = viewport.offsetTop + "px";
      dialog.style.bottom = "auto";
    };
    sync();
    viewport.addEventListener("resize", sync);
    viewport.addEventListener("scroll", sync);
    return () => {
      viewport.removeEventListener("resize", sync);
      viewport.removeEventListener("scroll", sync);
    };
  }, []);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previous = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    inputRef.current?.focus();
    return () => {
      dialog.close();
      document.body.style.overflow = previous;
    };
  }, []);
  useEffect(() => {
    const history = historyRef.current;
    history.scrollTop = history.scrollHeight;
  }, [messages, pending]);
  return (
    <dialog
      ref={dialogRef}
      className="assistant-dialog"
      aria-labelledby="assistant-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={sheet.panelRef}
        className="assistant-sheet"
        data-full={sheet.full}
        data-dragging={sheet.dragging}
      >
        <button
          type="button"
          className="chat-drag-handle"
          aria-label={sheet.full ? "Свернуть чат" : "Развернуть чат"}
          aria-expanded={sheet.full}
          {...sheet.handlers}
        >
          <span />
        </button>
        <header className="assistant-header">
          <h2 id="assistant-title">
            <span
              className="voice-wave voice-wave--animated chat-wave"
              data-thinking={Boolean(pending)}
              aria-hidden="true"
            >
              {Array.from({ length: 7 }, (_, index) => (
                <span className="voice-wave-bar" key={index} />
              ))}
            </span>
            Помощник
          </h2>
          <button type="button" className="chat-close" aria-label="Закрыть чат" onClick={onClose}>
            ×
          </button>
        </header>
        <div
          ref={historyRef}
          className="chat-history"
          role="log"
          aria-label="Переписка с помощником"
          aria-live="polite"
        >
          {messages.map((message, index) => (
            <div key={index} className={"chat-message chat-message--" + message.role}>
              {message.audio ? <VoiceMessage message={message} /> : message.text}
            </div>
          ))}
          {pending && (
            <div
              className="chat-message chat-message--assistant chat-typing"
              role="status"
              aria-label="Применяем настройки"
            >
              <span />
              <span />
              <span />
            </div>
          )}
        </div>
        {voice.error && (
          <p className="chat-voice-notice" role="alert">
            {voice.error}
          </p>
        )}
        <form
          className="chat-composer"
          data-recording={voice.status !== "idle"}
          onSubmit={(event) => {
            event.preventDefault();
            onSend();
          }}
        >
          {voice.status !== "idle" ? (
            <>
              <div
                className="chat-recording-wave"
                role="img"
                aria-label={"Запись голоса: " + voice.seconds + " секунд"}
              >
                {voice.levels.map((level, index) => (
                  <span
                    key={index}
                    style={{ height: 3 + level * 29 + "px", "--bar-delay": `${index * -0.07}s` }}
                  />
                ))}
              </div>
              <button
                type="button"
                className="chat-recording-stop"
                aria-label={
                  voice.status === "requesting"
                    ? "Отменить доступ к микрофону"
                    : "Остановить и сохранить запись"
                }
                disabled={voice.status === "stopping"}
                onClick={voice.status === "requesting" ? voice.cancel : voice.stop}
              >
                <span />
              </button>
              <span className="visually-hidden" role="status">
                {voice.status === "requesting"
                  ? "Ожидаем разрешение на микрофон"
                  : voice.status === "stopping"
                    ? "Сохраняем запись"
                    : "Идёт запись"}
              </span>
            </>
          ) : (
            <>
              <input
                ref={inputRef}
                aria-label="Сообщение помощнику"
                placeholder="Хотите что то изменить?"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                autoComplete="off"
              />
              {draft.trim() ? (
                <button type="submit" aria-label="Отправить сообщение">
                  <ControlIcon name="arrow" />
                </button>
              ) : (
                <button
                  type="button"
                  className="chat-microphone"
                  aria-label="Голосовой ввод"
                  onClick={() => {
                    inputRef.current?.blur();
                    voice.start();
                  }}
                >
                  <img src={voiceMic} alt="" />
                </button>
              )}
            </>
          )}
        </form>
      </section>
    </dialog>
  );
}

function formatStayDates(stay) {
  const format = (value) =>
    new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "long",
      timeZone: stay.hotel_timezone || "Europe/Moscow",
    }).format(new Date(value));
  return format(stay.check_in_at) + " — " + format(stay.target_wake_at);
}
function formatClock(value, timeZone) {
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone }).format(
    new Date(value),
  );
}
