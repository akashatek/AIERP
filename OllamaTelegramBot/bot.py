import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging early so you can see environment diagnostics
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Force load .env from the exact directory where bot.py resides
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    logger.info(f"Loading environment variables from: {env_path}")
    load_dotenv(dotenv_path=env_path, override=True)
else:
    logger.warning(f"No .env file found at {env_path}, using system environment variables.")

# Read environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
POSTGRES_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:postgres@localhost:5432/postgres")

# Sanity check token loading
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set! Check your .env file.")
    sys.exit(1)
else:
    # Print masked token to verify the correct token was loaded
    masked_token = f"{TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-4:]}"
    logger.info(f"Loaded Telegram Bot Token: {masked_token}")


from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
import psycopg

# Initialize LLM
llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model=OLLAMA_MODEL,
)

# Change call_model to an ASYNC function and use ainvoke()
async def call_model(state: MessagesState):
    system_prompt = SystemMessage(
        content="You are an AI assistant integrated into an AI-ERP system. Provide clear, accurate, and helpful answers."
    )
    messages = [system_prompt] + state["messages"]
    
    # Use await llm.ainvoke(...) instead of llm.invoke(...)
    response = await llm.ainvoke(messages)
    return {"messages": [response]}

# StateGraph setup remains the same
builder = StateGraph(state_schema=MessagesState)
builder.add_node("model", call_model)
builder.add_edge(START, "model")
builder.add_edge("model", END)

# Global runtime objects
pool = None
checkpointer = None
app_graph = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "Hello! I am your AI-ERP assistant connected to Ollama. Ask me anything!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with persistent LangGraph state."""
    # Ensure update contains a valid text message
    if not update.message or not update.message.text:
        logger.info("Received update without text message body.")
        return

    user_text = update.message.text
    chat_id = str(update.message.chat_id)

    # LOG INCOMING MESSAGE IMMEDIATELY
    logger.info(f"Received message from chat_id {chat_id}: '{user_text}'")

    # Show typing indicator while Ollama processes
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    config = {"configurable": {"thread_id": chat_id}}

    try:
        inputs = {"messages": [HumanMessage(content=user_text)]}
        logger.info(f"Invoking Ollama graph for chat_id {chat_id}...")
        
        result = await app_graph.ainvoke(inputs, config=config)

        ai_message = result["messages"][-1].content
        logger.info(f"Response received from Ollama. Sending to chat_id {chat_id}...")
        
        await update.message.reply_text(ai_message)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.message.reply_text("Sorry, an error occurred while processing your query.")

async def main():
    global pool, checkpointer, app_graph

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")

    logger.info(f"Connecting to Postgres at {POSTGRES_URI}")
    logger.info(f"Connecting to Ollama at {OLLAMA_BASE_URL}")

    # 1. Run migrations in autocommit mode to allow CREATE INDEX CONCURRENTLY
    async with await psycopg.AsyncConnection.connect(POSTGRES_URI, autocommit=True) as setup_conn:
        setup_checkpointer = AsyncPostgresSaver(setup_conn)
        await setup_checkpointer.setup()
        logger.info("Database tables and indexes setup successfully.")

    # 2. Initialize connection pool for runtime checkpointing
    async with AsyncConnectionPool(conninfo=POSTGRES_URI, max_size=20) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        app_graph = builder.compile(checkpointer=checkpointer)

        # 3. Start Telegram Bot
        tg_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        tg_app.add_handler(CommandHandler("start", start_command))
        tg_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

        logger.info("Bot is starting up...")
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()

        stop_event = asyncio.Event()
        await stop_event.wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")