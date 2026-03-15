from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, Router, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, WebAppInfo

from telegram_bot.config import PUBLIC_WEBAPP_URL, TELEGRAM_BOT_TOKEN


router = Router()


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    user_name = message.from_user.full_name if message.from_user else "Courier"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть карту в Telegram",
                    web_app=WebAppInfo(url=PUBLIC_WEBAPP_URL),
                )
            ]
        ]
    )

    await message.answer(
        f"Привет, {html.bold(user_name)}!\n\n"
        "Бот CourierAssist запущен.\n"
        "Нажми кнопку ниже, чтобы открыть карту как Telegram Mini App.",
        reply_markup=keyboard,
    )


async def main() -> None:
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())