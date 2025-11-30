import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
import os


# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ID администраторов (замените на реальные)
ADMINS = ['dedstart', 'Swat_ot_demona']  # Юзернеймы без @
GROUP_CHAT_ID = -5025893746  # Замените на ID вашей группы для файлов
MODERATION_GROUP_ID = -1003380097908  # Замените на ID группы для модерации
BOT_NAME = "Bot CheckerNFT"  # Название вашего бота


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, privilege TEXT DEFAULT 'user', 
                 status TEXT DEFAULT 'pending')''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_privileges
                 (privilege_name TEXT PRIMARY KEY, privilege_level INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS moderation_requests
                 (user_id INTEGER PRIMARY KEY, message_id INTEGER, status TEXT DEFAULT 'pending')''')
    conn.commit()
    conn.close()


# Проверка является ли пользователь администратором
def is_admin(username: str) -> bool:
    return username in ADMINS


# Главное меню для пользователей
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username
    
    # Добавляем пользователя в базу если его нет
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT status FROM users WHERE user_id = ?", (user.id,))
    result = c.fetchone()
    
    if not result:
        # Новый пользователь - отправляем запрос на модерацию
        c.execute("INSERT INTO users (user_id, username, status) VALUES (?, ?, ?)", 
                 (user.id, username, 'pending'))
        conn.commit()
        
        # Отправляем запрос в группу модерации
        await send_moderation_request(context, user)
        
        conn.close()
        
        await update.message.reply_text(
            "⏳ Ваш запрос на использование бота отправлен на модерацию. Ожидайте подтверждения."
        )
        return
    elif result[0] == 'pending':
        conn.close()
        await update.message.reply_text(
            "⏳ Ваш запрос еще находится на модерации. Пожалуйста, подождите."
        )
        return
    elif result[0] == 'banned':
        conn.close()
        await update.message.reply_text(
            "❌ Ваш доступ к боту заблокирован."
        )
        return
    
    conn.close()
    
    # Пользователь подтвержден - показываем главное меню
    keyboard = [
        [InlineKeyboardButton("📁 Скинуть файл", callback_data="upload_file")],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Добро пожаловать! Выберите действие:",
        reply_markup=reply_markup
    )


# Отправка запроса на модерацию
async def send_moderation_request(context: ContextTypes.DEFAULT_TYPE, user):
    keyboard = [
        [
            InlineKeyboardButton("✅ Разрешить", callback_data=f"mod_allow_{user.id}"),
            InlineKeyboardButton("❌ Запретить", callback_data=f"mod_deny_{user.id}"),
            InlineKeyboardButton("🚫 Забанить", callback_data=f"mod_ban_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        message = await context.bot.send_message(
            chat_id=MODERATION_GROUP_ID,
            text=f"👤 {user.username or 'Пользователь'} просит войти в бот {BOT_NAME}\nID: {user.id}",
            reply_markup=reply_markup
        )
        
        # Сохраняем ID сообщения модерации
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO moderation_requests (user_id, message_id) VALUES (?, ?)", 
                 (user.id, message.message_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка отправки запроса модерации: {e}")


# Обработчик модерации
async def moderation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = int(data.split('_')[2])
    action = data.split('_')[1]
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    if action == 'allow':
        # Разрешаем доступ
        c.execute("UPDATE users SET status = 'approved' WHERE user_id = ?", (user_id,))
        status_text = "✅ Доступ разрешен"
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🎉 Ваш доступ к боту подтвержден! Используйте /start для начала работы."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
            
    elif action == 'deny':
        # Запрещаем доступ
        c.execute("UPDATE users SET status = 'denied' WHERE user_id = ?", (user_id,))
        status_text = "❌ Доступ запрещен"
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ваш запрос на использование бота был отклонен."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
            
    elif action == 'ban':
        # Баним пользователя
        c.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (user_id,))
        status_text = "🚫 Пользователь забанен"
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 Ваш доступ к боту заблокирован."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
    
    conn.commit()
    conn.close()
    
    # Обновляем сообщение модерации
    original_text = query.message.text
    await query.edit_message_text(
        f"{original_text}\n\n{status_text} - @{query.from_user.username}"
    )


# Обработчик нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    # Проверяем статус пользователя
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT status FROM users WHERE user_id = ?", (user.id,))
    result = c.fetchone()
    conn.close()
    
    if not result or result[0] != 'approved':
        await query.edit_message_text("❌ Ваш доступ к боту не подтвержден или заблокирован.")
        return
    
    if data == "upload_file":
        # Удаляем предыдущее сообщение с кнопками
        await query.delete_message()
        
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel_upload")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=user.id,
            text="📤 Скиньте ваш файл:",
            reply_markup=reply_markup
        )
        context.user_data['waiting_for_file'] = True
        
    elif data == "support":
        await query.edit_message_text("🆘 Для связи с поддержкой перейдите: @dedstart")
        
    elif data == "cancel_upload":
        context.user_data.pop('waiting_for_file', None)
        await show_main_menu(user.id, context, "❌ Загрузка отменена.")
        
    elif data == "admin_panel":
        if is_admin(user.username):
            await show_admin_panel(query)
    
    elif data.startswith("admin_file_"):
        if is_admin(user.username):
            file_id = data.split("_")[2]
            await handle_admin_file_action(query, context, file_id)
    
    elif data.startswith("promote_"):
        if is_admin(user.username):
            target_user_id = int(data.split("_")[1])
            privilege = data.split("_")[2]
            await promote_user(context, target_user_id, privilege, query)
    
    elif data == "broadcast":
        if is_admin(user.username):
            context.user_data['waiting_for_broadcast'] = True
            await query.edit_message_text("📢 Введите сообщение для рассылки:")
    
    elif data == "add_admin":
        if is_admin(user.username):
            context.user_data['waiting_for_admin'] = True
            await query.edit_message_text("👤 Введите юзернейм нового администратора (без @):")
    
    elif data == "view_users":
        if is_admin(user.username):
            await view_users(query)


# Показать главное меню
async def show_main_menu(chat_id, context, text="👋 Добро пожаловать! Выберите действие:"):
    keyboard = [
        [InlineKeyboardButton("📁 Скинуть файл", callback_data="upload_file")],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
    ]
    
    # Добавляем кнопку админ-панели для администраторов
    user = context.user_data.get('user')
    if user and is_admin(user.username):
        keyboard.append([InlineKeyboardButton("⚙️ Админ Панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# Админ панель
async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("📊 Просмотр пользователей", callback_data="view_users")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
        [InlineKeyboardButton("👥 Добавить Админа бота", callback_data="add_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⚙️ Админ Панель:", reply_markup=reply_markup)


# Обработка файлов от пользователей
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем статус пользователя
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT status FROM users WHERE user_id = ?", (user.id,))
    result = c.fetchone()
    conn.close()
    
    if not result or result[0] != 'approved':
        await update.message.reply_text("❌ Ваш доступ к боту не подтвержден или заблокирован.")
        return
    
    if context.user_data.get('waiting_for_file'):
        file = None
        file_type = None
        
        if update.message.document:
            file = update.message.document
            file_type = "document"
        elif update.message.photo:
            file = update.message.photo[-1]
            file_type = "photo"
        elif update.message.video:
            file = update.message.video
            file_type = "video"
        elif update.message.audio:
            file = update.message.audio
            file_type = "audio"
        
        if file:
            # Сохраняем информацию о файле
            context.user_data['last_file'] = {
                'file_id': file.file_id,
                'file_type': file_type,
                'user_id': user.id,
                'username': user.username
            }
            
            # Отправляем файл в группу с кнопками для админов
            await send_file_to_admin_group(context, user, file, file_type)
            
            await update.message.reply_text("✅ Файл успешно отправлен!")
            context.user_data.pop('waiting_for_file', None)
            await show_main_menu(user.id, context, "✅ Файл отправлен! Что дальше?")
        else:
            await update.message.reply_text("❌ Пожалуйста, отправьте файл.")
    else:
        await update.message.reply_text("❌ Используйте кнопку 'Скинуть файл' для отправки файлов.")


# Отправка файла в группу с кнопками для админов
async def send_file_to_admin_group(context, user, file, file_type):
    caption = f"📁 Новый файл от @{user.username} (ID: {user.id})"
    
    keyboard = [
        [
            InlineKeyboardButton("👤 Профиль", url=f"https://t.me/{user.username}") if user.username else InlineKeyboardButton("👤 Профиль", callback_data="no_username"),
            InlineKeyboardButton("⬆️ Повысить", callback_data=f"admin_file_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if file_type == "document":
            await context.bot.send_document(
                chat_id=GROUP_CHAT_ID,
                document=file.file_id,
                caption=caption,
                reply_markup=reply_markup
            )
        elif file_type == "photo":
            await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=file.file_id,
                caption=caption,
                reply_markup=reply_markup
            )
        elif file_type == "video":
            await context.bot.send_video(
                chat_id=GROUP_CHAT_ID,
                video=file.file_id,
                caption=caption,
                reply_markup=reply_markup
            )
        elif file_type == "audio":
            await context.bot.send_audio(
                chat_id=GROUP_CHAT_ID,
                audio=file.file_id,
                caption=caption,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка отправки файла в группу: {e}")


# Обработка действий админа с файлом
async def handle_admin_file_action(query, context, file_user_id):
    keyboard = [
        [InlineKeyboardButton("⭐ Повысить до Модератора", callback_data=f"promote_{file_user_id}_moderator")],
        [InlineKeyboardButton("👑 Повысить до Администратора", callback_data=f"promote_{file_user_id}_administrator")],
        [InlineKeyboardButton("💎 Повысить до Владельца", callback_data=f"promote_{file_user_id}_owner")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👤 Выберите привилегию для пользователя (ID: {file_user_id}):",
        reply_markup=reply_markup
    )


# Повышение пользователя
async def promote_user(context, user_id, privilege, query):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Обновляем привилегию пользователя
    c.execute("UPDATE users SET privilege = ? WHERE user_id = ?", (privilege, user_id))
    conn.commit()
    
    # Получаем информацию о пользователе
    c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    username = result[0] if result else "Пользователь"
    conn.close()
    
    # Отправляем сообщение пользователю
    try:
        privilege_names = {
            'moderator': 'Модератора',
            'administrator': 'Администратора', 
            'owner': 'Владельца'
        }
        
        privilege_name = privilege_names.get(privilege, privilege)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 Поздравляем! Вы были повышены до {privilege_name}!"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
    
    await query.edit_message_text(f"✅ Пользователь @{username} повышен до {privilege}!")


# Рассылка сообщений
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_broadcast') and is_admin(update.effective_user.username):
        message = update.message
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        # Получаем всех подтвержденных пользователей
        c.execute("SELECT user_id FROM users WHERE status = 'approved'")
        users = c.fetchall()
        conn.close()
        
        sent_count = 0
        for user in users:
            try:
                # Пересылаем сообщение
                if message.text:
                    await context.bot.send_message(chat_id=user[0], text=message.text)
                elif message.photo:
                    await context.bot.send_photo(chat_id=user[0], photo=message.photo[-1].file_id, caption=message.caption)
                elif message.document:
                    await context.bot.send_document(chat_id=user[0], document=message.document.file_id, caption=message.caption)
                elif message.video:
                    await context.bot.send_video(chat_id=user[0], video=message.video.file_id, caption=message.caption)
                
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {user[0]}: {e}")
        
        context.user_data.pop('waiting_for_broadcast', None)
        await update.message.reply_text(f"✅ Рассылка завершена! Отправлено {sent_count} пользователям.")
        await show_admin_panel_from_message(update, context)


# Добавление администратора
async def handle_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_admin') and is_admin(update.effective_user.username):
        new_admin = update.message.text.strip()
        
        if new_admin not in ADMINS:
            ADMINS.append(new_admin)
            await update.message.reply_text(f"✅ Администратор @{new_admin} успешно добавлен!")
        else:
            await update.message.reply_text("❌ Этот пользователь уже является администратором!")
        
        context.user_data.pop('waiting_for_admin', None)
        await show_admin_panel_from_message(update, context)


# Показать админ панель из сообщения
async def show_admin_panel_from_message(update, context):
    user = update.effective_user
    if is_admin(user.username):
        keyboard = [
            [InlineKeyboardButton("📊 Просмотр пользователей", callback_data="view_users")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
            [InlineKeyboardButton("👥 Добавить Админа бота", callback_data="add_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⚙️ Админ Панель:", reply_markup=reply_markup)


# Просмотр пользователей
async def view_users(query):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, privilege, status FROM users LIMIT 50")
    users = c.fetchall()
    conn.close()
    
    if users:
        user_list = "📊 Список пользователей:\n\n"
        for user in users:
            status_icons = {
                'pending': '⏳',
                'approved': '✅',
                'denied': '❌',
                'banned': '🚫'
            }
            status_icon = status_icons.get(user[3], '❓')
            user_list += f"{status_icon} @{user[1]} (ID: {user[0]}) - {user[2]} [{user[3]}]\n"
        
        await query.edit_message_text(user_list)
    else:
        await query.edit_message_text("❌ Пользователи не найдены.")


# Основная функция
def main():
    # Замените '7986026588:AAHeSjTmpZyCa8x1AeJEx0-03yDh53xfYhw' на токен вашего бота
    application = Application.builder().token("YOUR_BOT_TOKEN").build()
    
    # Инициализация базы данных
    init_db()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", show_admin_panel_from_message))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(moderation_handler, pattern="^mod_"))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_admin))
    
    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()
