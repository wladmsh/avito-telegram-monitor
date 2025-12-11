import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler,
    filters, CallbackContext, JobQueue
)
from telegram.constants import ParseMode
from database import SessionLocal, UserTask
from avito_parser import parse_avito
from config import BOT_TOKEN, CHECK_INTERVAL
import asyncio

# Настройка логирования и состояний диалога
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GET_URL, GET_MIN_PRICE, GET_MAX_PRICE = range(3)

# Меню
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("➕ Добавить задание")],
        [KeyboardButton("📋 Мои задания"), KeyboardButton("⏸️ Остановить задание")],
        [KeyboardButton("▶️ Возобновить задание"), KeyboardButton("❌ Удалить задание")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Команда /start
async def start(update: Update, context: CallbackContext):
    welcome_text = (
        "Привет! Я бот для мониторинга новых объявлений на Авито.\n"
        "Я могу отслеживать изменения по вашим ссылкам и присылать уведомления.\n"
        "Используйте кнопки ниже для управления."
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

# Начало диалога добавления задачи
async def add_task_start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Отправьте мне ссылку на *отфильтрованную* страницу поиска на Авито.\n"
        "Например: `https://www.avito.ru/...?q=велосипед`",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_URL

# Получение ссылки
async def get_task_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    if 'avito.ru' not in url:
        await update.message.reply_text("❌ Это не похоже на ссылку Авито. Попробуйте еще раз.")
        return GET_URL
    context.user_data['task_url'] = url
    await update.message.reply_text("✅ Ссылка принята. Теперь введите *минимальную* цену (цифрами).\nИли 0, если ограничения нет.", parse_mode=ParseMode.MARKDOWN)
    return GET_MIN_PRICE

# Получение минимальной цены
async def get_task_min_price(update: Update, context: CallbackContext):
    try:
        min_price = int(update.message.text)
        if min_price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректное неотрицательное число.")
        return GET_MIN_PRICE
    context.user_data['min_price'] = min_price
    await update.message.reply_text("Теперь введите *максимальную* цену (цифрами).\nИли 0, если ограничения нет.", parse_mode=ParseMode.MARKDOWN)
    return GET_MAX_PRICE

# Получение максимальной цены и сохранение задачи
async def get_task_max_price_and_save(update: Update, context: CallbackContext):
    try:
        max_price = int(update.message.text)
        if max_price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректное неотрицательное число.")
        return GET_MAX_PRICE

    url = context.user_data['task_url']
    min_price = context.user_data['min_price']
    max_price = 999999999 if max_price == 0 else max_price

    db = SessionLocal()
    new_task = UserTask(
        user_id=update.effective_user.id,
        avito_url=url,
        min_price=min_price,
        max_price=max_price
    )
    db.add(new_task)
    db.commit()
    task_id = new_task.id
    db.close()

    await update.message.reply_text(
        f"✅ Задание #{task_id} создано!\n"
        f"• Ссылка: {url[:50]}...\n"
        f"• Цена от: {min_price if min_price > 0 else 'не задана'}\n"
        f"• Цена до: {max_price if max_price < 999999999 else 'не задана'}",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

# Отмена диалога
async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("Действие отменено.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# Показ списка задач пользователя
async def list_tasks(update: Update, context: CallbackContext):
    db = SessionLocal()
    tasks = db.query(UserTask).filter(UserTask.user_id == update.effective_user.id).all()
    db.close()

    if not tasks:
        await update.message.reply_text("У вас пока нет заданий.")
        return

    tasks_text = "📋 Ваши задания:\n\n"
    for task in tasks:
        status = "✅ Активно" if task.is_active else "⏸️ Остановлено"
        tasks_text += (
            f"ID: {task.id}\n"
            f"Ссылка: {task.avito_url[:40]}...\n"
            f"Цена: {task.min_price} – {task.max_price if task.max_price < 999999999 else '∞'}\n"
            f"Статус: {status}\n"
            f"{'-'*20}\n"
        )
    await update.message.reply_text(tasks_text)

# Основная функция мониторинга
async def check_all_tasks(context: CallbackContext):
    logger.info("Начинаю проверку заданий...")
    db = SessionLocal()
    tasks = db.query(UserTask).filter(UserTask.is_active == True).all()

    for task in tasks:
        try:
            new_items = parse_avito(task.avito_url, task.min_price, task.max_price)
            if not new_items:
                continue

            last_id = task.last_checked_ad_id
            new_items_sorted = sorted(new_items, key=lambda x: x['id'])

            if last_id:
                for item in new_items_sorted:
                    if item['id'] == last_id:
                        break
                    message = (
                        f"🚨 Новое объявление!\n"
                        f"Заголовок: {item['title']}\n"
                        f"Цена: {item['price']} ₽\n"
                        f"Ссылка: {item['link']}"
                    )
                    try:
                        await context.bot.send_message(chat_id=task.user_id, text=message)
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Не удалось отправить сообщение пользователю {task.user_id}: {e}")

            if new_items_sorted:
                task.last_checked_ad_id = new_items_sorted[0]['id']
        except Exception as e:
            logger.error(f"Ошибка при проверке задания {task.id}: {e}")
            continue

    db.commit()
    db.close()

# Главная функция
def main():
    if not BOT_TOKEN:
        logger.error("Не задан BOT_TOKEN!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ Добавить задание$'), add_task_start)],
        states={
            GET_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task_url)],
            GET_MIN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task_min_price)],
            GET_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task_max_price_and_save)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex('^📋 Мои задания$'), list_tasks))

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_all_tasks, interval=CHECK_INTERVAL, first=10)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
