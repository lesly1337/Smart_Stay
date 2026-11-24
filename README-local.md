# Запуск SmartStay

Общий README с ролями, ИИ, источниками и журналом решений будет добавлен
по материалам команды перед сдачей. Этот файл описывает технический запуск.

## Локальная разработка

Из корня проекта:

```powershell
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload --port 8000
```

Во втором терминале:

```powershell
cd FrontEnd/my-app
npm ci
npm run dev
```

Откройте http://localhost:5173. Vite перенаправляет `/api` на локальный бэкенд.
Токен берётся из `HACK_TEAM_TOKEN` или файла `HACK_TEAM_TOKEN_FILE`.
Локальный `simulator.local.json` исключён из Git; непустые переменные окружения
имеют приоритет. Секреты не добавляйте во фронтенд: все `VITE_*` публичны.

Интерфейс создаёт отдельный dev-сеанс через `/api/room/session`.
При истечении используйте обновление сеанса в интерфейсе. Этот режим
не заменяет конкурсный `/run`, который принимает токен и набор от стенда.
Голос по умолчанию отключён; локальное включение описано в `SPEECH_SETUP.md`.
Текстовые команды работают без Whisper.

## Клиент с бэкендом на стенде

Из `FrontEnd/my-app`:

```powershell
npm ci
npm run dev:stand
```

Клиент на http://localhost:5173 обращается к
https://team21.hack.be-healthy.tech/api из `.env.stand`.
Локальный Python-сервер в этом режиме не нужен. Бэкенд на стенде должен быть
развёрнут и доступен. Периоды закрытого доступа этот режим не обходит.

Для сборки клиента с тем же адресом:

```powershell
npm run build:stand
npm run preview
```

Откройте http://localhost:4173. После изменения `VITE_API_URL` пересоберите клиент.
На бэкенде разрешены localhost и 127.0.0.1 на портах 5173 и 4173.
Для другого адреса клиента задайте `SMARTSTAY_CLIENT_ORIGINS` на бэкенде:
полные origin через запятую, например `https://app.example.com`.
Значение заменяет список по умолчанию. Перезапустите бэкенд после изменения.

## Стенд

Python 3.11, зависимости из корневого `requirements.txt`, запуск:

```bash
bash start.sh
```

Скрипт слушает `0.0.0.0:$PORT` (8000 по умолчанию) и отключает локальный Whisper.
Ключи и адреса предоставляет окружение стенда. Workflow
`.github/workflows/deploy.yml` использует секрет GitHub `STAND_SSH_KEY`.
Push в main запускает деплой. Локальные модели и токены туда не отправляются.

## Проверки

Из корня:

```powershell
py -m pip install -r requirements-dev.txt
py -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs
```

Из `FrontEnd/my-app`: `npm run build` и `npm run build:stand`.
