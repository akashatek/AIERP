# OllamaTelegramBot

AI-ERP Project - Telegram Chatbot interface powered by Ollama (`llama3:8b`), LangGraph, and PostgreSQL.

---

## 1. Prerequisites & Telegram Setup

### Step 1: Create a Telegram Bot via BotFather
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow the instructions to set up a bot name and username.
3. BotFather will provide an **HTTP API Token**. Save this token safely.

### Step 2: Ensure Required Ollama Model is Pulled
Ensure your `ollama` service running inside the `aicp_net` network has loaded `llama3.1:8b`. If not, run:
```bash
docker exec -it ollama ollama pull llama3:8b

```

---

## 2. Deployment with Docker Compose

### Step 1: Create Environment Variables

Inside the `OllamaTelegramBot` folder, cope `sample.env` to `.env` file. Update the passwords and tokens.

```env
TELEGRAM_BOT_TOKEN=<your_telegram_bot_token_here>
POSTGRES_PASSWORD=<your_postgres_password>
```

### Step 2: Start the Service

Ensure the `aicp_net` network exists and your existing containers (`ollama`, `postgres`, etc.) are running.

Run:

```bash
docker compose up -d --build

```

### Step 3: Monitor Logs

To verify that the bot has connected successfully and initialized the PostgreSQL tables:

```bash
docker compose logs -f ollama-telegram-bot

```

---

## 3. Testing the Bot

1. Open Telegram and search for your bot username.
2. Click **Start** or type `/start`.
3. Send a message. The bot will send a query to Ollama and respond back while maintaining conversation history in PostgreSQL.

```
