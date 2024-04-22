import logging
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler, CallbackQueryHandler
import requests
import schedule
import threading
from telegram.error import BadRequest

# config
BOT_TOKEN = 'ТОКЕН БОТА'  # Замените на ваш токен
RELOAD_INTERVAL = 60  # интервал перезагрузки в секундах
CODES_FILE = 'codes.txt'
codes = {}
WHITELIST = {ТВОЙ_USER_ID, ID_ХЕЛПЕРА}  # Добавьте сюда допустимые UserID

# constantas for ConversationHandler
ADDING, GET_KEY = range(2)

# log config
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def load_codes():
    global codes
    try:
        with open(CODES_FILE, 'r') as file:
            codes = {line.split(':')[0].strip(): line.split(':')[1].strip() for line in file.readlines()}
    except Exception as e:
        logger.error("load ___ERROR___: %s", str(e))

def get_otp(code):
    try:
        response = requests.get(f'https://2fa.fb.rip/api/otp/{code}')
        if response.status_code == 200:
            return response.json()['data']['otp']
        else:
            return None
    except Exception as e:
        logger.error("get OTP failed: %s", str(e))
        return None

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет друг, я хелпану тебе с OTP (конечно все логгируется и льется автору ;)")
    return ConversationHandler.END


def delete_last_messages(update: Update, context: CallbackContext, n: int):
    query = update.callback_query
    query.answer()
    for i in range(n):
        try:
            context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id - i)
        except BadRequest as e:
            logger.warning(f"Failed to delete message: {str(e)}")

def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        return  # Игнорировать пользователей не из списка
    text = update.message.text.lower()
    context.user_data['current_word'] = text
    update.message.delete()
    if text in codes:
        code = codes[text]
        otp = get_otp(code)
        if otp:
            keyboard = [[InlineKeyboardButton("Delete", callback_data=f"delete_{update.message.message_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(f"```\n{otp}\n```", parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            update.message.reply_text("Что-то пошло не так. Наверное ты что-то не то куда-то не туда ввел...")
        return ConversationHandler.END
    else:
        keyboard = [[InlineKeyboardButton("Да", callback_data='yes'), InlineKeyboardButton("Нет", callback_data='no')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text('Акк не найден. Добавим?', reply_markup=reply_markup)
        return ADDING

def handle_decision(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.delete()
    if query.data == 'yes':
        message = context.bot.send_message(chat_id=query.message.chat_id, text='Веди OTPseed (код генерации):')
        context.user_data['key_message_id'] = message.message_id
        return GET_KEY
    else:
        context.bot.send_message(chat_id=query.message.chat_id, text='Ну ладно. Мэйби некст тайм...')
        return ConversationHandler.END

def handle_add_code(update: Update, context: CallbackContext):
    key = update.message.text.upper()
    word = context.user_data.get('current_word')
    key_message_id = context.user_data.get('key_message_id')
    update.message.delete()
    if key_message_id:
        try:
            context.bot.delete_message(chat_id=update.message.chat_id, message_id=key_message_id)
        except BadRequest as e:
            logger.warning(f"Failed to delete message: {str(e)}")
    with open(CODES_FILE, 'a') as file:
        file.write(f'{word}:{key}\n')
    load_codes()
    keyboard = [[InlineKeyboardButton("Delete", callback_data="delete_last_5")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(f'OTPseed added for "{word}".', reply_markup=reply_markup)
    return ConversationHandler.END

def delete_message(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    try:
        context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
    except BadRequest as e:
        logger.warning(f"Failed to delete message: {str(e)}")

def reload_codes():
    load_codes()
    logger.info("Base updated")

def schedule_jobs():
    schedule.every(RELOAD_INTERVAL).seconds.do(reload_codes)
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    load_codes()
    thread = threading.Thread(target=schedule_jobs)
    thread.start()

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text & ~Filters.command, handle_message)],
        states={
            ADDING: [CallbackQueryHandler(handle_decision)],
            GET_KEY: [MessageHandler(Filters.text & ~Filters.command, handle_add_code)]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(delete_message, pattern='^delete_'))
    dispatcher.add_handler(CallbackQueryHandler(lambda update, context: delete_last_messages(update, context, 5), pattern='^delete_last_5$'))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
