"""Wisp: private Telegram AI bot. Sending an image or text is the entire daily interface."""
import argparse
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
import logging

from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.error import RetryAfter, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ai_client import AIClient, AIError, make_user_message
from config import Config, ConfigError, load_environment, required
from conversation import ConversationStore
from formatting import format_solution
from guards import Deduplicator, RateLimiter
from images import ImageError, download_image, image_attachment

logger = logging.getLogger("wisp")


def configure_logging():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.setLevel(logging.INFO)
    # HTTP URLs can contain the bot token; SDK debug logs can contain payloads.
    for name in ("httpx", "httpcore", "openai", "telegram"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


@asynccontextmanager
async def typing(bot, chat_id):
    async def pulse():
        while True:
            with suppress(TelegramError):
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    task = asyncio.create_task(pulse())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def send_text(bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
    except RetryAfter as error:
        delay = error.retry_after
        delay = delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay)
        if delay > 60:
            raise
        await asyncio.sleep(delay + 0.1)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)


class WatchBot:
    def __init__(self, config: Config, ai=None):
        self.config = config
        self.ai = ai or AIClient(config)
        self.conversations = ConversationStore(config)
        self.dedup = Deduplicator()
        self.rates = RateLimiter(config.requests_per_minute)
        self.locks = defaultdict(asyncio.Lock)
        self.pending = defaultdict(int)
        self.cleanup_task = None

    def authorized(self, update: Update) -> bool:
        return bool(
            update.effective_user
            and update.effective_user.id in self.config.allowed_user_ids
            and update.effective_chat
            and update.effective_chat.type == ChatType.PRIVATE
        )

    async def notice(self, bot, chat_id, text):
        try:
            await send_text(bot, chat_id, text)
        except TelegramError:
            logger.warning("Could not deliver a status message.")

    async def log_receipt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if not message:
            return
        kind = (
            "photo" if message.photo else
            "document" if message.document else
            "command" if filters.COMMAND.check_update(update) else
            "text" if message.text else "other"
        )
        logger.info(
            "Message received from_id=%s chat_id=%s message_id=%s type=%s allowed=%s",
            update.effective_user.id if update.effective_user else None,
            message.chat_id, message.message_id, kind, self.authorized(update),
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Only fresh messages, never edited messages/channel posts.
        message = update.message
        if not message or not self.authorized(update):
            return
        user_id, chat_id = update.effective_user.id, update.effective_chat.id
        if not self.dedup.claim((chat_id, message.message_id)):
            return
        attachment = image_attachment(message)
        if message.document and attachment is None:
            await self.notice(context.bot, chat_id, "Send a PNG, JPEG, WebP, or non-animated GIF image; PDF and other documents are not supported.")
            return
        text = (message.caption if attachment else message.text) or ""
        if not attachment and not text.strip():
            return
        if len(text) > self.config.max_text_chars:
            await self.notice(context.bot, chat_id, f"Please shorten your message to {self.config.max_text_chars} characters.")
            return
        if self.pending[user_id] >= 3:
            await self.notice(context.bot, chat_id, "Please wait for your pending questions to finish, then resend this message.")
            return
        if not self.rates.allow(user_id):
            await self.notice(context.bot, chat_id, "Too many requests. Wait about a minute, then resend your message.")
            return
        self.pending[user_id] += 1
        try:
            # FIFO per user: a follow-up arriving during image solving sees its result.
            async with self.locks[user_id]:
                try:
                    async with typing(context.bot, chat_id):
                        async with asyncio.timeout(45):
                            image = await download_image(context.bot, attachment, self.config) if attachment else None
                        user = make_user_message(text.strip() or None, image, self.config.default_language)
                        solution = await self.ai.solve(self.conversations.history(user_id), user)
                        replies = format_solution(solution)
                    # Commit only complete successful answers, before delivery. A delivery
                    # failure must never cause another automatic billable model request.
                    self.conversations.add(user_id, user, "\n\n".join(replies))
                    for index, reply in enumerate(replies):
                        if index:
                            await asyncio.sleep(self.config.message_interval_ms / 1000)
                        await send_text(context.bot, chat_id, reply)
                    logger.info("Request completed from_id=%s message_id=%s.", user_id, message.message_id)
                except (AIError, ImageError) as error:
                    await self.notice(context.bot, chat_id, str(error))
                except TimeoutError:
                    await self.notice(context.bot, chat_id, "Image download timed out. Please resend the image.")
                except TelegramError:
                    logger.warning("Telegram transfer failed.")
                    await self.notice(context.bot, chat_id, "Telegram delivery or download failed. Some answer messages may be missing. Please try again.")
                except Exception as error:
                    # Deliberately never log str(error), traceback, update or message.
                    logger.error("Request failed (%s).", type(error).__name__)
                    await self.notice(context.bot, chat_id, "Something went wrong. Please try again.")
        finally:
            self.pending[user_id] -= 1

    async def start(self, update, context):
        if update.effective_chat.type != ChatType.PRIVATE:
            return
        if not self.authorized(update):
            await self.notice(context.bot, update.effective_chat.id,
                              f"Access is restricted. Your Telegram User ID is {update.effective_user.id}. Ask the owner to add it to ALLOWED_USER_IDS.")
            return
        await self.notice(context.bot, update.effective_chat.id,
                          "Send a question photo or screenshot. I will send one combined reply with answers and necessary steps. Send ordinary text to follow up.")

    async def reset(self, update, context):
        if not self.authorized(update):
            return
        async with self.locks[update.effective_user.id]:
            self.conversations.clear(update.effective_user.id)
            await self.notice(context.bot, update.effective_chat.id, "Conversation memory cleared. Send a new image or question.")

    async def on_error(self, update, context):
        logger.error("Telegram handler failed (%s).", type(context.error).__name__)

    async def on_init(self, application):
        async def cleanup():
            while True:
                await asyncio.sleep(60)
                self.conversations.prune()
        self.cleanup_task = asyncio.create_task(cleanup())
        logger.info("Bot started provider=%s model=%s. Send an image or text in a private chat.",
                    self.config.ai_provider, self.config.ai_model)

    async def on_shutdown(self, application):
        if self.cleanup_task:
            self.cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.cleanup_task
        await self.ai.close()

    def application(self) -> Application:
        app = (Application.builder().token(self.config.telegram_bot_token)
               .concurrent_updates(8).connection_pool_size(16)
               .connect_timeout(15).read_timeout(30).write_timeout(30)
               .post_init(self.on_init).post_shutdown(self.on_shutdown).build())
        # Separate group observes receipts before command routing and authorization,
        # including unsupported messages. It does not consume the normal handler.
        app.add_handler(MessageHandler(
            filters.UpdateType.MESSAGE & filters.ChatType.PRIVATE, self.log_receipt,
        ), group=-1)
        app.add_handler(CommandHandler("start", self.start, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("reset", self.reset, filters=filters.ChatType.PRIVATE))
        app.add_handler(MessageHandler(
            filters.UpdateType.MESSAGE & filters.ChatType.PRIVATE
            & (filters.PHOTO | filters.Document.ALL | (filters.TEXT & ~filters.COMMAND)),
            self.handle_message,
        ))
        app.add_error_handler(self.on_error)
        return app


def show_user_id():
    """One-time setup: only Telegram, no OpenAI credentials or API calls."""
    load_environment()
    app = Application.builder().token(required("TELEGRAM_BOT_TOKEN")).build()

    async def identify(update, context):
        uid = update.effective_user.id
        print(f"Telegram User ID: {uid}", flush=True)
        await send_text(context.bot, update.effective_chat.id, f"Your Telegram User ID: {uid}")

    async def safe_error(update, context):
        logger.warning("Telegram setup request failed (%s).", type(context.error).__name__)

    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.ChatType.PRIVATE, identify))
    app.add_error_handler(safe_error)
    print("Send any private message to your bot; press Ctrl+C after receiving your ID.", flush=True)
    app.run_polling(allowed_updates=["message"], drop_pending_updates=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-user-id", action="store_true", help="one-time ID setup; no AI requests")
    parser.add_argument("--check-config", action="store_true", help="validate .env locally without network calls")
    args = parser.parse_args()
    configure_logging()
    try:
        if args.show_user_id:
            show_user_id()
            return
        config = Config.from_env()
        if args.check_config:
            print(f"Configuration is valid. Provider: {config.ai_provider}; model: {config.ai_model}. Credentials and model access have not been tested.")
            return
        service = WatchBot(config)
        service.application().run_polling(allowed_updates=["message"], drop_pending_updates=True)
    except ConfigError as error:
        parser.exit(2, f"Configuration error: {error}\n")
    except Exception as error:
        parser.exit(1, f"Startup stopped ({type(error).__name__}). Check network access and configuration.\n")


if __name__ == "__main__":
    main()
