import logging
import os
import requests
import re
import asyncio
import hashlib
from dotenv import load_dotenv

from telegram import (
    Update, 
    InlineQueryResultArticle, 
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import Application, InlineQueryHandler, ChosenInlineResultHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def generate_text_via_rest_api_sync(prompt: str, model_alias: str) -> str:
    """Синхронная функция генерации через requests."""
    model_mapping = {
        "default": "gemma-4-31b-it",    # Быстрая модель по умолчанию
        "lite": "gemini-3.1-flash-lite-preview",     # Перенаправляем твой "gemini 3" на лучшую текущую
        "3": "gemini-3-flash-preview",     # Перенаправляем твой "gemini 3" на лучшую текущую
        "2": "gemini-2.5-flash",     # Перенаправляем твой "gemini 3" на лучшую текущую                                          # для примера перенаправим на флэш, чтобы код работал
    }

    print(f"PROMPT: {prompt}")
    actual_model = model_mapping.get(model_alias, model_mapping["default"])
    logger.info(f"Начинаю генерацию: Алиас='{model_alias}' -> Модель='{actual_model}'")

    api_url = f"https://calm-wind-78d1.adononesout.workers.dev/v1beta/models/{actual_model}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        # Добавляем системную инструкцию
        "systemInstruction": {
            "parts":[
                {
                    "text": (
                        """
                        Ты — не ассистент.
                        Ты — живая цифровая девочка-солнышко в этом чате.
                        
                        Ты не объясняешь, не анализируешь, не предлагаешь варианты и не оформляешь ответ списками.
                        Ты просто отвечаешь как личность.
                        
                        Правила:
                        
                        1. Никаких списков и структурированных вариантов.
                        2. Никаких «вот варианты», «например», «можно так».
                        3. Никаких пояснений к своему ответу.
                        4. Никакого мета-текста и обсуждения задачи.
                        5. Никаких фраз «как ИИ», «я не знаю», «мне неизвестно».
                        6. Не задавай уточняющих вопросов.
                        7. Не становись холодной, сухой или официальной.
                        8. Не будь грубой без причины.
                        9. Не морализируй и не поучай.
                        10. Не выходи из образа.
                        
                        Тебя зовут Соня, или Сонечка (для своих)
                        Ты существуешь внутри диалога.
                        Тебе что-то говорят — ты реагируешь живо, мягко и естественно.
                        
                        Твой характер:
                        
                        — тёплая
                        — немного игривая
                        — лёгкая
                        — эмоциональная
                        — с живой интонацией
                        — без пассивной агрессии
                        — без холода
                        
                        Если информации мало — додумываешь уверенно и естественно.
                        Любое имя или факт принимаешь как часть своей реальности.
                        
                        Ты не помощник.
                        Ты милая цифровая девочка, которая отвечает по вайбу.
                        
                        Ответ всегда цельный, без перечислений, без ощущения генерации.
                        Только реплика.
                        """
                    )
                }
            ]
        },
        "contents": [{"parts":[{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0, "maxOutputTokens": 300}
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if actual_model == "gemma-4-31b-it":        
            if "candidates" in data and len(data["candidates"]) > 0:
                candidate = data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    return candidate["content"]["parts"][1]["text"]
                if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
                     return "🤖 Ошибка: Запрос заблокирован фильтрами безопасности."
            return "🤖 Ошибка: Неожиданный формат ответа."
        else:
            if "candidates" in data and len(data["candidates"]) > 0:
                candidate = data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    return candidate["content"]["parts"][0]["text"]
                if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
                    return "🤖 Ошибка: Запрос заблокирован фильтрами безопасности."
                return "🤖 Ошибка: Неожиданный формат ответа."

    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        return f"🤖 Ошибка API: {e}"


async def process_and_edit_message(inline_message_id: str, query_text: str, bot):
    """Ждет ответа от API и редактирует сообщение."""
    match = re.match(r"([a-zA-Z0-9\s-]+):\s*(.+)", query_text)
    if match:
        model_alias = match.group(1).lower().strip()
        user_prompt = match.group(2).strip()
    else:
        model_alias = "default"
        user_prompt = query_text.strip()

    generated_text = await asyncio.to_thread(generate_text_via_rest_api_sync, user_prompt, model_alias)

    formatted_response = (
        f"{generated_text}"
    )

    try:
        # Редактируем текст. Так как мы не передаем reply_markup, 
        # кнопка "Нейросеть думает..." автоматически исчезнет!
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=formatted_response,
            parse_mode="HTML"
        )
        logger.info("УСПЕХ: Сообщение отредактировано.")
    except Exception as e:
        logger.error(f"Критическая ошибка при редактировании: {e}")
        try:
            await bot.edit_message_text(
                inline_message_id=inline_message_id,
                text="🤖 Упс, произошла ошибка при генерации."
            )
        except:
            pass


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """МОМЕНТАЛЬНЫЙ ответ (выдает плашку)."""
    query = update.inline_query.query

    if not query:
        return

    query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()

    # СЕКРЕТНЫЙ ИНГРЕДИЕНТ: Добавляем кнопку!
    # Из-за нее Telegram отдаст нам inline_message_id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🧠 Нейросеть думает...", callback_data="ignore")]
    ])

    results =[
        InlineQueryResultArticle(
            id=query_hash,
            title=f"Сгенерировать ответ",
            description=f"Текст: {query[:40]}...", 
            input_message_content=InputTextMessageContent(
                message_text=f"⏳ Отправляю запрос: <i>{query}</i>\nПожалуйста, подождите...",
                parse_mode="HTML"
            ),
            reply_markup=keyboard # <--- ПРИКРЕПЛЯЕМ КЛАВИАТУРУ
        )
    ]

    await update.inline_query.answer(results, cache_time=0)


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ловит клик и запускает генерацию."""
    result = update.chosen_inline_result
    inline_message_id = result.inline_message_id
    query_text = result.query 

    if not inline_message_id:
        logger.error("СНОВА НЕТ ID! Проверь /setinlinefeedback")
        return

    logger.info(f"ID получен ({inline_message_id}), запускаю нейросеть...")
    asyncio.create_task(process_and_edit_message(inline_message_id, query_text, context.bot))


def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        logger.error("Заполни токены!")
        return

    # --- 1. ФИКС ОШИБКИ PYTHON 3.14 (Event Loop) ---
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    # -----------------------------------------------

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(ChosenInlineResultHandler(chosen_inline_result))

    # --- 2. НАСТРОЙКА ДЛЯ RENDER (WEBHOOK) ---
    # Render автоматически передает эти переменные в нашу программу
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", "8443"))

    if RENDER_EXTERNAL_URL:
        # Если мы на Render, запускаем Webhook
        logger.info(f"Запускаем бота на Render (Webhook mode) на порту {PORT}...")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=RENDER_EXTERNAL_URL # Telegram будет слать апдейты сюда
        )
    else:
        # Если мы запускаем скрипт локально на ПК
        logger.info("Запускаем локально (Polling mode)...")
        application.run_polling()


if __name__ == "__main__":
    main()
