import React, { useState, useEffect, useRef } from "react";
import "./MainMenu.css";

const CARDS = [
  {
    id: 1,
    title: "Раздел 1",
    description: "Краткое описание первого блока или действия.",
    icon: (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </svg>
    ),
  },
  {
    id: 2,
    title: "Раздел 2",
    description: "Краткое описание второго блока или действия.",
    icon: (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M12 2v20M2 12h20" />
      </svg>
    ),
  },
  {
    id: 3,
    title: "Раздел 3",
    description: "Краткое описание третьего блока или действия.",
    icon: (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 3" />
      </svg>
    ),
  },
  {
    id: 4,
    title: "Раздел 4",
    description: "Краткое описание четвёртого блока или действия.",
    icon: (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
];

const MicIcon = () => (
  <svg
    width="19"
    height="19"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="9" y="2" width="6" height="11" rx="3" />
    <path d="M5 10a7 7 0 0 0 14 0" />
    <line x1="12" y1="17" x2="12" y2="21" />
    <line x1="8" y1="21" x2="16" y2="21" />
  </svg>
);

const SendIcon = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="12" y1="19" x2="12" y2="5" />
    <polyline points="5 12 12 5 19 12" />
  </svg>
);

export default function MainMenu() {
  // Состояния чата
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStyle, setDragStyle] = useState({});

  // Сообщения и ввод
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: "bot",
      text: "Привет! Чем помочь? Можешь написать текстом или нажать на микрофон.",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isRecording, setIsRecording] = useState(false);

  // Рефы
  const screenRef = useRef(null);
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const blobRefs = useRef([]);
  const recognitionRef = useRef(null);

  const dragState = useRef({
    active: false,
    startY: 0,
    startHeight: 0,
    deltaY: 0,
    moved: false,
  });

  // 1. Анимация живого фона (медленный дрейф + параллакс от курсора)
  useEffect(() => {
    const configs = [
      { speedX: 0.0007, speedY: 0.0005, range: 60, parallax: 45, phase: 0 },
      { speedX: 0.0005, speedY: 0.0008, range: 75, parallax: -55, phase: 2 },
      { speedX: 0.0006, speedY: 0.0006, range: 50, parallax: 30, phase: 4 },
    ];

    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let rafId;

    const handleMouseMove = (e) => {
      targetX = (e.clientX / window.innerWidth - 0.5) * 2;
      targetY = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    const handleTouchMove = (e) => {
      if (e.touches.length > 0) {
        targetX = (e.touches[0].clientX / window.innerWidth - 0.5) * 2;
        targetY = (e.touches[0].clientY / window.innerHeight - 0.5) * 2;
      }
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });

    const animate = (time) => {
      currentX += (targetX - currentX) * 0.04;
      currentY += (targetY - currentY) * 0.04;

      configs.forEach((cfg, idx) => {
        const el = blobRefs.current[idx];
        if (!el) return;

        const driftX = Math.sin(time * cfg.speedX + cfg.phase) * cfg.range;
        const driftY = Math.cos(time * cfg.speedY + cfg.phase) * cfg.range;
        const offsetX = currentX * cfg.parallax;
        const offsetY = currentY * cfg.parallax;

        el.style.transform = `translate3d(${driftX + offsetX}px, ${driftY + offsetY}px, 0)`;
      });

      rafId = requestAnimationFrame(animate);
    };

    rafId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("touchmove", handleTouchMove);
    };
  }, []);

  // 2. Инициализация голосового ввода (Web Speech API)
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((res) => res[0].transcript)
        .join("");
      setInputValue(transcript);
    };

    recognition.onend = () => {
      setIsRecording(false);
      inputRef.current?.focus();
    };

    recognition.onerror = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
    };
  }, []);

  // Автопрокрутка ленты при новых сообщениях
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isOpen]);

  // Управление открытием/закрытием чата
  const openChat = (withVoice = false) => {
    setIsOpen(true);
    if (withVoice) {
      toggleVoiceInput();
    } else {
      setTimeout(() => inputRef.current?.focus(), 250);
    }
  };

  const closeChat = () => {
    setIsOpen(false);
    setIsExpanded(false);
    setIsDragging(false);
    setDragStyle({});
    inputRef.current?.blur();
  };

  const toggleVoiceInput = () => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setIsRecording((prev) => !prev);
      return;
    }

    if (isRecording) {
      recognition.stop();
    } else {
      setIsRecording(true);
      recognition.start();
    }
  };

  const handleSendMessage = (e) => {
    e.preventDefault();
    const text = inputValue.trim();
    if (!text) return;

    const userMsg = { id: Date.now(), sender: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setInputValue("");

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, sender: "bot", text: `Принято: «${text}»` },
      ]);
    }, 450);
  };

  // 3. Жесты перетаскивания шторки вверх (на весь экран) и вниз
  const handlePointerDown = (e) => {
    if (e.target.closest("button")) return;
    const sheetEl = e.currentTarget.closest(".chat-sheet");
    if (!sheetEl) return;

    dragState.current = {
      active: true,
      startY: e.clientY,
      startHeight: sheetEl.getBoundingClientRect().height,
      deltaY: 0,
      moved: false,
    };

    setIsDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e) => {
    if (!dragState.current.active || !screenRef.current) return;

    const deltaY = e.clientY - dragState.current.startY;
    if (Math.abs(deltaY) > 4) {
      dragState.current.moved = true;
    }
    dragState.current.deltaY = deltaY;

    const screenHeight = screenRef.current.getBoundingClientRect().height;
    const { startHeight } = dragState.current;

    if (deltaY < 0) {
      // Тянем вверх -> раскрываем до 100% экрана
      const newHeight = Math.min(screenHeight, startHeight - deltaY);
      setDragStyle({ height: `${newHeight}px`, transform: "translateY(0)" });
    } else {
      // Тянем вниз -> уменьшаем высоту или сдвигаем вниз
      const baseHeight = screenHeight * 0.68;
      if (isExpanded && startHeight - deltaY > baseHeight) {
        setDragStyle({ height: `${startHeight - deltaY}px`, transform: "translateY(0)" });
      } else {
        const shiftDown = isExpanded ? deltaY - (startHeight - baseHeight) : deltaY;
        setDragStyle({
          height: `${baseHeight}px`,
          transform: `translateY(${Math.max(0, shiftDown)}px)`,
        });
      }
    }
  };

  const handlePointerUp = (e) => {
    if (!dragState.current.active) return;

    const { deltaY, moved } = dragState.current;
    dragState.current.active = false;
    setIsDragging(false);
    setDragStyle({});
    e.currentTarget.releasePointerCapture(e.pointerId);

    // Обычный клик по полоске-хэндлу переключает полноэкранный режим
    if (!moved) {
      if (e.currentTarget.classList.contains("sheet-handle")) {
        setIsExpanded((prev) => !prev);
      }
      return;
    }

    if (deltaY < -60) {
      setIsExpanded(true);
    } else if (isExpanded) {
      if (deltaY > 220) closeChat();
      else if (deltaY > 60) setIsExpanded(false);
    } else if (deltaY > 90) {
      closeChat();
    }
  };

  return (
    <div className="screen" ref={screenRef}>
      {/* Живой фон */}
      <div className="ambient-bg" aria-hidden="true">
        {[0, 1, 2].map((idx) => (
          <div
            key={idx}
            ref={(el) => (blobRefs.current[idx] = el)}
            className={`blob blob-${idx + 1}`}
          />
        ))}
      </div>

      <header>
        <p className="eyebrow">Добро пожаловать</p>
        <h1>Главное меню</h1>
      </header>

      <main>
        <div className="grid">
          {CARDS.map((card) => (
            <section key={card.id} className="card">
              <div className="icon" aria-hidden="true">
                {card.icon}
              </div>
              <h2>{card.title}</h2>
              <p className="description">{card.description}</p>
            </section>
          ))}
        </div>
      </main>

      {/* Нижняя полоска чата (свёрнутое состояние) */}
      <footer className="chat-bar" onClick={() => openChat(false)}>
        <div className="chat-pill">
          <span className="chat-placeholder">Спросить или написать...</span>
          <div className="chat-actions">
            <button
              type="button"
              className="icon-btn voice-btn"
              aria-label="Голосовой ввод"
              title="Голосовой ввод"
              onClick={(e) => {
                e.stopPropagation();
                openChat(true);
              }}
            >
              <MicIcon />
            </button>
            <button
              type="button"
              className="icon-btn send-btn"
              aria-label="Открыть чат"
              title="Отправить"
            >
              <SendIcon />
            </button>
          </div>
        </div>
      </footer>

      {/* Затемнение фона */}
      <div className={`chat-backdrop ${isOpen ? "open" : ""}`} onClick={closeChat} />

      {/* Выдвижное окно чата (Bottom Sheet) */}
      <section
        className={`chat-sheet ${isOpen ? "open" : ""} ${isExpanded ? "expanded" : ""} ${isDragging ? "dragging" : ""}`}
        style={dragStyle}
        aria-label="Окно чата"
        aria-hidden={!isOpen}
      >
        <div
          className="sheet-handle"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        />

        <div
          className="sheet-header"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <div className="sheet-title-wrap">
            <span className="status-dot" />
            <h3>Помощник</h3>
          </div>
          <button type="button" className="close-btn" onClick={closeChat} aria-label="Закрыть чат">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="chat-messages">
          {messages.map((msg) => (
            <div key={msg.id} className={`msg msg-${msg.sender}`}>
              {msg.text}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <form className="sheet-form" onSubmit={handleSendMessage}>
          <input
            ref={inputRef}
            type="text"
            className="chat-input"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={isRecording ? "Говорите..." : "Сообщение..."}
            autoComplete="off"
          />
          <div className="chat-actions">
            <button
              type="button"
              className={`icon-btn voice-btn ${isRecording ? "recording" : ""}`}
              onClick={toggleVoiceInput}
              aria-label="Голосовой ввод"
              title="Голосовой ввод"
            >
              <MicIcon />
            </button>
            <button
              type="submit"
              className="icon-btn send-btn"
              aria-label="Отправить"
              title="Отправить"
            >
              <SendIcon />
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
