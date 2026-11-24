const blobs = [
  {
    el: document.querySelector(".blob-1"),
    speedX: 0.0007,
    speedY: 0.0005,
    range: 60,
    parallax: 45,
    phase: 0,
  },
  {
    el: document.querySelector(".blob-2"),
    speedX: 0.0005,
    speedY: 0.0008,
    range: 75,
    parallax: -55,
    phase: 2,
  },
  {
    el: document.querySelector(".blob-3"),
    speedX: 0.0006,
    speedY: 0.0006,
    range: 50,
    parallax: 30,
    phase: 4,
  },
];

let targetX = 0;
let targetY = 0;
let currentX = 0;
let currentY = 0;

// Отслеживаем курсор мыши
window.addEventListener(
  "mousemove",
  (e) => {
    targetX = (e.clientX / window.innerWidth - 0.5) * 2;
    targetY = (e.clientY / window.innerHeight - 0.5) * 2;
  },
  { passive: true },
);

// Отслеживаем движение пальца на сенсорных экранах
window.addEventListener(
  "touchmove",
  (e) => {
    if (e.touches.length > 0) {
      targetX = (e.touches[0].clientX / window.innerWidth - 0.5) * 2;
      targetY = (e.touches[0].clientY / window.innerHeight - 0.5) * 2;
    }
  },
  { passive: true },
);

function animate(time) {
  currentX += (targetX - currentX) * 0.1;
  currentY += (targetY - currentY) * 0.09;

  blobs.forEach((b) => {
    if (!b.el) return;

    // Медленный фоновый дрейф по умолчанию
    const driftX = Math.sin(time * b.speedX + b.phase) * b.range;
    const driftY = Math.cos(time * b.speedY + b.phase) * b.range;

    // Смещение от курсора
    const offsetX = currentX * b.parallax;
    const offsetY = currentY * b.parallax;

    b.el.style.transform = `translate3d(${driftX + offsetX}px, ${driftY + offsetY}px, 0)`;
  });

  requestAnimationFrame(animate);
}

requestAnimationFrame(animate);
