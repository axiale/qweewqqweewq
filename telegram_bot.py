import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler, JobQueue
)
from telegram.request import HTTPXRequest
from database import TrainingDB
from calculator import MuscleCalculator
from datetime import datetime, time
from telegram.error import TimedOut
import io

# Состояния для ConversationHandler
NAME, HEIGHT, WEIGHT, SLEEP = range(4)
EXERCISE_SELECT, SETS, REPS, LOAD, ADD_MORE = range(10, 15)  # Убрали CATEGORY_SELECT
UPDATE_WEIGHT_STATE = 20
TEMPLATE_NAME, TEMPLATE_EXERCISE, TEMPLATE_SETS, TEMPLATE_REPS, TEMPLATE_LOAD, TEMPLATE_ADD_MORE = range(30, 36)
PROFILE_EDIT_NAME, PROFILE_EDIT_HEIGHT, PROFILE_EDIT_WEIGHT, PROFILE_EDIT_SLEEP = range(40, 44)
REMINDER_SET = 50

logger = logging.getLogger(__name__)

class TrainingBot:
    def __init__(self, token: str, db: TrainingDB, calc: MuscleCalculator):
        self.token = token
        self.db = db
        self.calc = calc
        # Увеличиваем таймауты для предотвращения ошибок сети
        request = HTTPXRequest(connect_timeout=30, read_timeout=30)
        self.application = Application.builder().token(token).request(request).build()
        self._register_handlers()
        self.logger = logger

    def _register_handlers(self):
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("menu", self.menu))
        self.application.add_handler(CommandHandler("remind", self.set_reminder))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.Regex('^🔙 Назад$'), self.menu))
        self.application.add_error_handler(self.error_handler)

        # Регистрация
        reg_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^🔹 Регистрация$'), self.reg_start)],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reg_name)],
                HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reg_height)],
                WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reg_weight)],
                SLEEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reg_sleep)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.application.add_handler(reg_conv)

        # Добавление тренировки (без категорий, с нумерацией)
        workout_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^➕ Добавить тренировку$'), self.workout_start)],
            states={
                EXERCISE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.workout_exercise)],
                SETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.workout_sets)],
                REPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.workout_reps)],
                LOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.workout_load)],
                ADD_MORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.workout_add_more)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.application.add_handler(workout_conv)

        # Обновление веса
        weight_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^⚖️ Обновить вес$'), self.update_weight_start)],
            states={
                UPDATE_WEIGHT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.update_weight_done)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.application.add_handler(weight_conv)

        # Шаблоны тренировок (создание)
        template_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^📋 Создать шаблон$'), self.template_start)],
            states={
                TEMPLATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.template_name)],
                TEMPLATE_EXERCISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.template_exercise)],
                TEMPLATE_SETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.template_sets)],
                TEMPLATE_REPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.template_reps)],
                TEMPLATE_LOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.template_load)],
                TEMPLATE_ADD_MORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.template_add_more)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.application.add_handler(template_conv)

        # Редактирование профиля
        profile_edit_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^✏️ Редактировать профиль$'), self.profile_edit_start)],
            states={
                PROFILE_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.profile_edit_name)],
                PROFILE_EDIT_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.profile_edit_height)],
                PROFILE_EDIT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.profile_edit_weight)],
                PROFILE_EDIT_SLEEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.profile_edit_sleep)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.application.add_handler(profile_edit_conv)

        # Напоминания (установка)
        reminder_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^➕ Установить напоминание$'), self.reminder_set_start)],
            states={
                REMINDER_SET: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reminder_set_time)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.application.add_handler(reminder_conv)

        # Обработчики кнопок меню (сгруппированы по разделам)
        self.application.add_handler(MessageHandler(filters.Regex('^🏋️‍♂️ Тренировки$'), self.training_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^📊 Аналитика$'), self.analytics_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^👤 Профиль$'), self.profile_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^🔔 Напоминания$'), self.reminders_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^ℹ️ Помощь$'), self.help_command))

        # Обработчики кнопок второго уровня (из подменю)
        self.application.add_handler(MessageHandler(filters.Regex('^➕ Добавить тренировку$'), self.workout_start))
        self.application.add_handler(MessageHandler(filters.Regex('^📜 История тренировок$'), self.show_history))
        self.application.add_handler(MessageHandler(filters.Regex('^❌ Удалить последнюю$'), self.delete_last_workout))
        self.application.add_handler(MessageHandler(filters.Regex('^📋 Шаблоны$'), self.list_templates))
        self.application.add_handler(MessageHandler(filters.Regex('^📊 Моя статистика$'), self.show_stats))
        self.application.add_handler(MessageHandler(filters.Regex('^📈 Частота тренировок$'), self.show_frequency))
        self.application.add_handler(MessageHandler(filters.Regex('^📈 График прогресса$'), self.progress_start))
        self.application.add_handler(MessageHandler(filters.Regex('^📊 Сравнение групп$'), self.group_stats))
        self.application.add_handler(MessageHandler(filters.Regex('^📈 Рекомендации$'), self.frequency_recommendations))
        self.application.add_handler(MessageHandler(filters.Regex('^⚖️ Анализ баланса$'), self.balance_analysis))
        self.application.add_handler(MessageHandler(filters.Regex('^⚖️ Обновить вес$'), self.update_weight_start))
        self.application.add_handler(MessageHandler(filters.Regex('^✏️ Редактировать профиль$'), self.profile_edit_start))
        self.application.add_handler(MessageHandler(filters.Regex('^➕ Установить напоминание$'), self.reminder_set_start))
        self.application.add_handler(MessageHandler(filters.Regex('^❌ Удалить напоминания$'), self.delete_reminders))

        # Callback для графиков и шаблонов
        self.application.add_handler(CallbackQueryHandler(self.progress_callback, pattern="^progress_"))
        self.application.add_handler(CallbackQueryHandler(self.template_callback, pattern="^(template|apply)_"))

    # ----- Старт и главное меню -----
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if db_user:
            await update.message.reply_text(f"С возвращением, {db_user['name']}!\nИспользуй /menu для навигации.")
        else:
            await update.message.reply_text(
                "Привет! Я помогу отслеживать развитие мышц.\n"
                "Нажми '🔹 Регистрация', чтобы создать профиль."
            )
            keyboard = [[KeyboardButton("🔹 Регистрация")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Выбери действие:", reply_markup=reply_markup)

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню с разделами."""
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся через /start")
            return
        keyboard = [
            [KeyboardButton("🏋️‍♂️ Тренировки")],
            [KeyboardButton("📊 Аналитика")],
            [KeyboardButton("👤 Профиль")],
            [KeyboardButton("🔔 Напоминания")],
            [KeyboardButton("ℹ️ Помощь")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

    # ----- Подменю -----
    async def training_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [KeyboardButton("➕ Добавить тренировку")],
            [KeyboardButton("📜 История тренировок")],
            [KeyboardButton("❌ Удалить последнюю")],
            [KeyboardButton("📋 Шаблоны")],
            [KeyboardButton("🔙 Назад")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🏋️‍♂️ Управление тренировками", reply_markup=reply_markup)

    async def analytics_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [KeyboardButton("📊 Моя статистика")],
            [KeyboardButton("📈 Частота тренировок")],
            [KeyboardButton("📈 График прогресса")],
            [KeyboardButton("📊 Сравнение групп")],
            [KeyboardButton("📈 Рекомендации")],
            [KeyboardButton("⚖️ Анализ баланса")],
            [KeyboardButton("🔙 Назад")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("📊 Аналитика", reply_markup=reply_markup)

    async def profile_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        text = f"**Профиль пользователя**\n"
        text += f"Имя: {db_user['name']}\n"
        text += f"Рост: {db_user['height']} см\n"
        text += f"Вес: {db_user['weight']} кг\n"
        text += f"Сон: {db_user['sleep_hours']} ч\n"
        keyboard = [
            [KeyboardButton("⚖️ Обновить вес")],
            [KeyboardButton("✏️ Редактировать профиль")],
            [KeyboardButton("🔙 Назад")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def reminders_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [KeyboardButton("➕ Установить напоминание")],
            [KeyboardButton("❌ Удалить напоминания")],
            [KeyboardButton("🔙 Назад")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🔔 Управление напоминаниями", reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "ℹ️ **Помощь по боту**\n\n"
            "**🏋️‍♂️ Тренировки**\n"
            "• **➕ Добавить тренировку** – начать запись тренировки. Введи номер упражнения из списка.\n"
            "• **📜 История тренировок** – последние 5 тренировок.\n"
            "• **❌ Удалить последнюю** – удалить последнюю тренировку.\n"
            "• **📋 Шаблоны** – создание и применение шаблонов.\n\n"
            "**📊 Аналитика**\n"
            "• **📊 Моя статистика** – развитие каждой мышцы за 30 дней.\n"
            "• **📈 Частота тренировок** – анализ интервалов между тренировками.\n"
            "• **📈 График прогресса** – график нагрузки на выбранную мышцу.\n"
            "• **📊 Сравнение групп** – нагрузка по группам мышц.\n"
            "• **📈 Рекомендации** – оптимальная частота тренировок.\n"
            "• **⚖️ Анализ баланса** – сравнение с целевыми пропорциями.\n\n"
            "**👤 Профиль**\n"
            "• **⚖️ Обновить вес** – изменить текущий вес.\n"
            "• **✏️ Редактировать профиль** – изменить имя, рост, вес, сон.\n\n"
            "**🔔 Напоминания**\n"
            "• **➕ Установить напоминание** – ежедневное напоминание в указанное время.\n"
            "• **❌ Удалить напоминания** – удалить все напоминания.\n\n"
            "**🔙 Назад** – вернуться в главное меню.\n"
            "Используй /menu в любой момент."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    # ----- Регистрация -----
    async def reg_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if self.db.get_user_by_telegram_id(user.id):
            await update.message.reply_text("Ты уже зарегистрирован. Используй /menu.")
            return ConversationHandler.END
        await update.message.reply_text("Как тебя зовут?")
        return NAME

    async def reg_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['reg_name'] = update.message.text
        await update.message.reply_text("Твой рост (в см)?")
        return HEIGHT

    async def reg_height(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            height = float(update.message.text)
            if height <= 0:
                raise ValueError
            context.user_data['reg_height'] = height
            await update.message.reply_text("Твой текущий вес (в кг)?")
            return WEIGHT
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return HEIGHT

    async def reg_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            weight = float(update.message.text)
            if weight <= 0:
                raise ValueError
            context.user_data['reg_weight'] = weight
            await update.message.reply_text("Сколько часов ты обычно спишь?")
            return SLEEP
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return WEIGHT

    async def reg_sleep(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            sleep = float(update.message.text)
            if sleep <= 0:
                raise ValueError
            user_id = self.db.add_user(
                name=context.user_data['reg_name'],
                height=context.user_data['reg_height'],
                weight=context.user_data['reg_weight'],
                sleep_hours=sleep,
                telegram_id=update.effective_user.id
            )
            await update.message.reply_text("Регистрация завершена! Теперь можно добавлять тренировки через /menu.")
            await self.menu(update, context)
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return SLEEP

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Очищаем все данные пользователя, связанные с текущим диалогом
        keys_to_clear = [
            'workout_id', 'workout_exercise_id', 'workout_load_type',
            'workout_sets', 'workout_reps', 'workout_weight', 'template_name',
            'template_exercises', 'template_current_exercise', 'template_current_load_type',
            'template_current_sets', 'template_current_reps', 'template_current_weight',
            'edit_user_id', 'edit_name', 'edit_height', 'edit_weight', 'exercise_list'
        ]
        for key in keys_to_clear:
            context.user_data.pop(key, None)
        await update.message.reply_text("Действие отменено.")
        return ConversationHandler.END

    # ----- Добавление тренировки (с нумерованным списком упражнений) -----
    async def workout_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся!")
            return ConversationHandler.END
        context.user_data['workout_user_id'] = db_user['id']
        # Создаём новую тренировку
        workout_id = self.db.add_workout(db_user['id'], datetime.now())
        context.user_data['workout_id'] = workout_id

        # Получаем все упражнения и нумеруем их
        exercises = self.db.get_all_exercises()
        if not exercises:
            await update.message.reply_text("В базе пока нет упражнений.")
            return ConversationHandler.END
        context.user_data['exercise_list'] = exercises  # сохраняем список

        # Формируем текстовый список с номерами
        msg_lines = ["📋 Список упражнений (введи номер):"]
        for i, ex in enumerate(exercises, start=1):
            msg_lines.append(f"{i}. {ex['name']}")
        msg = "\n".join(msg_lines)

        # Отправляем список и просим ввести номер
        await update.message.reply_text(msg)
        await update.message.reply_text("Введи номер упражнения:")
        return EXERCISE_SELECT

    async def workout_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        try:
            num = int(text)
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи целое число.")
            return EXERCISE_SELECT

        exercises = context.user_data.get('exercise_list')
        if not exercises:
            # Если список пропал (ошибка), начинаем заново
            return await self.workout_start(update, context)

        if num < 1 or num > len(exercises):
            await update.message.reply_text(f"Номер должен быть от 1 до {len(exercises)}.")
            return EXERCISE_SELECT

        ex = exercises[num-1]
        context.user_data['workout_exercise_id'] = ex['id']
        context.user_data['workout_load_type'] = ex['load_type']

        await update.message.reply_text("Сколько подходов?")
        return SETS

    async def workout_sets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            sets = int(update.message.text)
            if sets <= 0:
                raise ValueError
            context.user_data['workout_sets'] = sets
            await update.message.reply_text("Сколько повторений в каждом подходе?")
            return REPS
        except ValueError:
            await update.message.reply_text("Введи целое положительное число.")
            return SETS

    async def workout_reps(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            reps = int(update.message.text)
            if reps <= 0:
                raise ValueError
            context.user_data['workout_reps'] = reps
            load_type = context.user_data['workout_load_type']
            if load_type == 'weight':
                await update.message.reply_text("Какой вес отягощения (в кг)?")
                return LOAD
            else:
                context.user_data['workout_weight'] = 0.0
                await self.save_workout_exercise(update, context)
                await self._show_add_more_options(update, context)
                return ADD_MORE
        except ValueError:
            await update.message.reply_text("Введи целое положительное число.")
            return REPS

    async def workout_load(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            weight = float(update.message.text)
            if weight < 0:
                raise ValueError
            context.user_data['workout_weight'] = weight
            await self.save_workout_exercise(update, context)
            await self._show_add_more_options(update, context)
            return ADD_MORE
        except ValueError:
            await update.message.reply_text("Введи неотрицательное число.")
            return LOAD

    async def _show_add_more_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [KeyboardButton("➕ Добавить ещё")],
            [KeyboardButton("✅ Завершить тренировку")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Хочешь добавить ещё упражнение или завершить тренировку?", reply_markup=reply_markup)

    async def save_workout_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            self.db.add_workout_exercise(
                workout_id=context.user_data['workout_id'],
                exercise_id=context.user_data['workout_exercise_id'],
                sets=context.user_data['workout_sets'],
                reps=context.user_data['workout_reps'],
                weight=context.user_data.get('workout_weight', 0.0)
            )
            self.calc.clear_cache()
            await update.message.reply_text("Упражнение добавлено.")
        except Exception as e:
            logger.error(f"Ошибка сохранения упражнения: {e}")
            await update.message.reply_text("Произошла ошибка при сохранении. Попробуй ещё раз.")
            await self.menu(update, context)
            return ConversationHandler.END

    async def workout_add_more(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "➕ Добавить ещё":
            # Возвращаемся к выбору упражнения (список уже есть в context)
            exercises = context.user_data.get('exercise_list')
            if exercises:
                msg_lines = ["📋 Список упражнений (введи номер):"]
                for i, ex in enumerate(exercises, start=1):
                    msg_lines.append(f"{i}. {ex['name']}")
                msg = "\n".join(msg_lines)
                await update.message.reply_text(msg)
                await update.message.reply_text("Введи номер упражнения:")
                return EXERCISE_SELECT
            else:
                # Если список пропал – начинаем заново
                return await self.workout_start(update, context)
        elif text == "✅ Завершить тренировку":
            await self.show_workout_summary(update, context)
            # Очищаем данные тренировки
            keys_to_clear = ['workout_id', 'workout_exercise_id', 'workout_load_type',
                             'workout_sets', 'workout_reps', 'workout_weight', 'exercise_list']
            for key in keys_to_clear:
                context.user_data.pop(key, None)
            await self.menu(update, context)
            return ConversationHandler.END
        else:
            await self._show_add_more_options(update, context)
            return ADD_MORE

    async def show_workout_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        workout_id = context.user_data.get('workout_id')
        if not workout_id:
            return
        exercises = self.db.get_workout_exercises(workout_id)
        text = "✅ **Тренировка завершена!**\n\n"
        for ex in exercises:
            text += f"• {ex['name']}: {ex['sets']}x{ex['reps']}"
            if ex['weight'] > 0:
                text += f" ({ex['weight']} кг)"
            text += "\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    # ----- Статистика и аналитика (без изменений) -----
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        muscles = self.db.get_all_muscles()
        if not muscles:
            await update.message.reply_text("Нет данных о мышцах.")
            return
        text = "📊 **Развитие мышц за последние 30 дней:**\n"
        for muscle in muscles:
            dev = self.calc.get_muscle_development(db_user['id'], muscle['id'])
            text += f"\n**{muscle['name']}**:\n"
            text += f"  • Всего нагрузки: {dev['total_load_30d']} кг\n"
            text += f"  • В среднем за тренировку: {dev['avg_load_per_workout']} кг\n"
            text += f"  • Тренировок: {dev['workout_count']}\n"
            text += f"  • Изменение к предыдущему периоду: {dev['delta_percent']}%\n"
        await self._send_long_message(update, text, parse_mode='Markdown')

    async def show_frequency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        muscles = self.db.get_all_muscles()
        if not muscles:
            await update.message.reply_text("Нет данных о мышцах.")
            return
        text = "📈 **Анализ частоты тренировок:**\n"
        for muscle in muscles:
            freq_data = self.calc.optimal_training_frequency(db_user['id'], muscle['id'])
            if freq_data:
                text += f"\n**{muscle['name']}**:\n"
                for interval, info in freq_data.items():
                    text += f"  Интервал {interval} дн. (примеров: {info['count']}): ср. прирост {info['avg_gain']} кг\n"
        await self._send_long_message(update, text, parse_mode='Markdown')

    async def progress_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        muscles = self.db.get_all_muscles()
        if not muscles:
            await update.message.reply_text("Нет данных о мышцах.")
            return
        keyboard = []
        for muscle in muscles:
            keyboard.append([InlineKeyboardButton(muscle['name'], callback_data=f"progress_{muscle['id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выбери мышцу для просмотра графика прогресса:", reply_markup=reply_markup)

    async def progress_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("progress_"):
            muscle_id = int(data.split("_")[1])
            user = update.effective_user
            db_user = self.db.get_user_by_telegram_id(user.id)
            if not db_user:
                await query.edit_message_text("Ошибка: пользователь не найден.")
                return
            plot_bytes = self.calc.get_muscle_progress_plot(db_user['id'], muscle_id, days=90)
            if plot_bytes is None:
                await query.edit_message_text("Недостаточно данных для построения графика.")
                return
            await query.message.reply_photo(photo=plot_bytes, caption=f"Прогресс мышцы")
            await query.delete_message()

    async def group_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        muscles = self.db.get_all_muscles()
        if not muscles:
            await update.message.reply_text("Нет данных о мышцах.")
            return
        group_load = {}
        for muscle in muscles:
            dev = self.calc.get_muscle_development(db_user['id'], muscle['id'])
            load = dev['total_load_30d']
            group_id = muscle.get('group_id')
            if group_id:
                if group_id not in group_load:
                    cursor = self.db.conn.cursor()
                    cursor.execute("SELECT name FROM muscle_groups WHERE id = ?", (group_id,))
                    row = cursor.fetchone()
                    group_name = row['name'] if row else "Без группы"
                    group_load[group_id] = {'name': group_name, 'load': 0}
                group_load[group_id]['load'] += load
            else:
                if 'other' not in group_load:
                    group_load['other'] = {'name': 'Прочие', 'load': 0}
                group_load['other']['load'] += load
        text = "📊 **Нагрузка по группам мышц за 30 дней:**\n"
        for item in group_load.values():
            text += f"\n• {item['name']}: {item['load']} кг"
        await update.message.reply_text(text, parse_mode='Markdown')

    async def frequency_recommendations(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        muscles = self.db.get_all_muscles()
        if not muscles:
            await update.message.reply_text("Нет данных о мышцах.")
            return
        text = "📈 **Рекомендуемая частота тренировок (на основе истории):**\n"
        for muscle in muscles:
            interval = self.calc.recommend_frequency(db_user['id'], muscle['id'], min_samples=2)
            if interval:
                text += f"\n• {muscle['name']}: {interval} дней"
            else:
                text += f"\n• {muscle['name']}: недостаточно данных"
        await update.message.reply_text(text, parse_mode='Markdown')

    async def balance_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return

        await update.message.reply_text("🔍 Анализирую баланс мышц за последние 60 дней...")

        result = self.calc.analyze_muscle_balance(db_user['id'], days=60)

        if "error" in result:
            await update.message.reply_text(result["error"])
            return

        text = "📊 **Анализ мышечного баланса**\n\n"
        text += "Целевые проценты – ориентировочные для сбалансированного развития.\n\n"

        under = []
        over = []
        ok = []

        for name, data in result.items():
            status = data['status']
            line = f"• {name}: факт {data['actual_percent']}% / цель {data['target_percent']}%"
            if status == "under":
                line += " 🔻 недогружена"
                under.append((name, data))
            elif status == "over":
                line += " 🔺 перегружена"
                over.append((name, data))
            elif status == "ok":
                line += " ✅ норма"
                ok.append((name, data))
            else:
                line += f" (не учтена в целях, факт {data['actual_percent']}%)"
            text += line + "\n"

        if under:
            text += "\n**Рекомендации для отстающих мышц:**\n"
            for name, data in under:
                text += f"\n🔹 {name}:\n"
                if data['exercises']:
                    for ex in data['exercises']:
                        text += f"   - {ex['name']} (задействует {ex['percentage']}%)\n"
                else:
                    text += "   (нет подходящих упражнений в базе)\n"

        await self._send_long_message(update, text, parse_mode='Markdown')

    # ----- История и удаление -----
    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        workouts = self.db.get_workouts(db_user['id'], limit=5)
        if not workouts:
            await update.message.reply_text("У тебя пока нет тренировок.")
            return
        text = "📜 **Последние тренировки:**\n"
        for w in workouts:
            dt = datetime.fromisoformat(w['datetime']).strftime('%d.%m.%Y %H:%M')
            text += f"\n🗓 {dt}\n"
            exercises = self.db.get_workout_exercises(w['id'])
            for e in exercises:
                text += f"  • {e['name']}: {e['sets']}x{e['reps']} "
                if e['weight'] > 0:
                    text += f"({e['weight']} кг)\n"
                else:
                    text += "\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    async def delete_last_workout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        workouts = self.db.get_workouts(db_user['id'], limit=1)
        if not workouts:
            await update.message.reply_text("Нет тренировок для удаления.")
            return
        workout_id = workouts[0]['id']
        try:
            self.db.delete_workout(workout_id)
            self.calc.clear_cache()
            await update.message.reply_text("Последняя тренировка удалена.")
        except Exception as e:
            logger.error(f"Ошибка удаления тренировки: {e}")
            await update.message.reply_text("Произошла ошибка при удалении.")

    # ----- Напоминания (без изменений) -----
    async def set_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            time_str = context.args[0]
            hour, minute = map(int, time_str.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            chat_id = update.effective_chat.id
            context.job_queue.run_daily(self.reminder_callback, time=time(hour, minute), chat_id=chat_id)
            await update.message.reply_text(f"Напоминание установлено на {hour:02d}:{minute:02d}")
        except (IndexError, ValueError):
            await update.message.reply_text("Использование: /remind ЧЧ:ММ")

    async def reminder_set_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Введи время для напоминания в формате ЧЧ:ММ (например, 19:30):")
        return REMINDER_SET

    async def reminder_set_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            time_str = update.message.text
            hour, minute = map(int, time_str.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            chat_id = update.effective_chat.id
            context.job_queue.run_daily(self.reminder_callback, time=time(hour, minute), chat_id=chat_id)
            await update.message.reply_text(f"Напоминание установлено на {hour:02d}:{minute:02d}")
            return ConversationHandler.END
        except (ValueError, IndexError):
            await update.message.reply_text("Неверный формат. Попробуй ещё раз или /cancel.")
            return REMINDER_SET

    async def delete_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Удаление напоминаний пока не реализовано. Используй /remind для установки нового (старое перезапишется).")

    async def reminder_callback(self, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_message(chat_id=context.job.chat_id, text="⏰ Время тренировки!")

    # ----- Обновление веса -----
    async def update_weight_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Введи новый вес в кг:")
        return UPDATE_WEIGHT_STATE

    async def update_weight_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            new_weight = float(update.message.text)
            if new_weight <= 0:
                raise ValueError
            user = update.effective_user
            db_user = self.db.get_user_by_telegram_id(user.id)
            if not db_user:
                await update.message.reply_text("Сначала зарегистрируйся.")
                return ConversationHandler.END
            self.db.update_user_weight(db_user['id'], new_weight)
            await update.message.reply_text(f"Вес обновлён: {new_weight} кг")
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return UPDATE_WEIGHT_STATE

    # ----- Шаблоны (без изменений) -----
    async def list_templates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return
        templates = self.db.get_templates(db_user['id'])
        if not templates:
            await update.message.reply_text("У тебя пока нет шаблонов. Создай через '📋 Создать шаблон'.")
            return
        text = "📋 **Твои шаблоны:**\n"
        keyboard = []
        for t in templates:
            text += f"• {t['name']}\n"
            keyboard.append([InlineKeyboardButton(t['name'], callback_data=f"template_{t['id']}")])
        keyboard.append([InlineKeyboardButton("➕ Создать новый", callback_data="template_create")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def template_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data == "template_create":
            await query.message.reply_text("Для создания шаблона используй кнопку '📋 Создать шаблон' в меню тренировок.")
        elif data.startswith("template_"):
            template_id = int(data.split("_")[1])
            exercises = self.db.get_template_exercises(template_id)
            text = "Упражнения в шаблоне:\n"
            for ex in exercises:
                text += f"• {ex['name']}: {ex['sets']}x{ex['reps']}"
                if ex['weight']:
                    text += f" ({ex['weight']} кг)"
                text += "\n"
            text += "\nПрименить этот шаблон к новой тренировке?"
            keyboard = [
                [InlineKeyboardButton("✅ Применить", callback_data=f"apply_{template_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="template_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
        elif data.startswith("apply_"):
            template_id = int(data.split("_")[1])
            user = update.effective_user
            db_user = self.db.get_user_by_telegram_id(user.id)
            if not db_user:
                await query.edit_message_text("Ошибка: пользователь не найден.")
                return
            workout_id = self.db.add_workout(db_user['id'], datetime.now())
            self.db.apply_template(template_id, workout_id)
            self.calc.clear_cache()
            await query.edit_message_text("✅ Шаблон применён, тренировка создана!")
        elif data == "template_cancel":
            await query.delete_message()

    async def template_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return ConversationHandler.END
        context.user_data['template_user_id'] = db_user['id']
        context.user_data['template_exercises'] = []
        await update.message.reply_text("Введи название нового шаблона:")
        return TEMPLATE_NAME

    async def template_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['template_name'] = update.message.text
        await self.template_ask_exercise(update, context)
        return TEMPLATE_EXERCISE

    async def template_ask_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Введи название упражнения для добавления (или 'готово' для завершения):")

    async def template_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text.lower() == 'готово':
            template_id = self.db.add_template(
                user_id=context.user_data['template_user_id'],
                name=context.user_data['template_name']
            )
            for ex in context.user_data['template_exercises']:
                self.db.add_template_exercise(
                    template_id=template_id,
                    exercise_id=ex['exercise_id'],
                    sets=ex['sets'],
                    reps=ex['reps'],
                    weight=ex['weight'] if ex['weight'] != 0 else None
                )
            await update.message.reply_text(f"Шаблон '{context.user_data['template_name']}' сохранён!")
            context.user_data.clear()
            return ConversationHandler.END
        exercises = self.db.get_all_exercises()
        ex = next((e for e in exercises if e['name'].lower() == text.lower()), None)
        if not ex:
            await update.message.reply_text("Упражнение не найдено. Попробуй ещё раз или введи 'готово'.")
            return TEMPLATE_EXERCISE
        context.user_data['template_current_exercise'] = ex['id']
        context.user_data['template_current_load_type'] = ex['load_type']
        await update.message.reply_text("Сколько подходов?")
        return TEMPLATE_SETS

    async def template_sets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            sets = int(update.message.text)
            if sets <= 0:
                raise ValueError
            context.user_data['template_current_sets'] = sets
            await update.message.reply_text("Сколько повторений?")
            return TEMPLATE_REPS
        except ValueError:
            await update.message.reply_text("Введи целое положительное число.")
            return TEMPLATE_SETS

    async def template_reps(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            reps = int(update.message.text)
            if reps <= 0:
                raise ValueError
            context.user_data['template_current_reps'] = reps
            load_type = context.user_data['template_current_load_type']
            if load_type == 'weight':
                await update.message.reply_text("Какой вес отягощения (в кг)? (можно пропустить, введя 0)")
                return TEMPLATE_LOAD
            else:
                context.user_data['template_current_weight'] = 0.0
                await self.template_save_exercise(update, context)
                return TEMPLATE_ADD_MORE
        except ValueError:
            await update.message.reply_text("Введи целое положительное число.")
            return TEMPLATE_REPS

    async def template_load(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            weight = float(update.message.text)
            if weight < 0:
                raise ValueError
            context.user_data['template_current_weight'] = weight
            await self.template_save_exercise(update, context)
            return TEMPLATE_ADD_MORE
        except ValueError:
            await update.message.reply_text("Введи неотрицательное число.")
            return TEMPLATE_LOAD

    async def template_save_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        ex = {
            'exercise_id': context.user_data['template_current_exercise'],
            'sets': context.user_data['template_current_sets'],
            'reps': context.user_data['template_current_reps'],
            'weight': context.user_data.get('template_current_weight', 0.0)
        }
        context.user_data['template_exercises'].append(ex)
        await update.message.reply_text("Упражнение добавлено.")

    async def template_add_more(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Введи следующее упражнение или 'готово' для завершения:")
        return TEMPLATE_EXERCISE

    # ----- Профиль (редактирование) -----
    async def profile_edit_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = self.db.get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Сначала зарегистрируйся.")
            return ConversationHandler.END
        context.user_data['edit_user_id'] = db_user['id']
        await update.message.reply_text("Введи новое имя (или /cancel для отмены):")
        return PROFILE_EDIT_NAME

    async def profile_edit_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['edit_name'] = update.message.text
        await update.message.reply_text("Введи новый рост (в см):")
        return PROFILE_EDIT_HEIGHT

    async def profile_edit_height(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            height = float(update.message.text)
            if height <= 0:
                raise ValueError
            context.user_data['edit_height'] = height
            await update.message.reply_text("Введи новый вес (в кг):")
            return PROFILE_EDIT_WEIGHT
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return PROFILE_EDIT_HEIGHT

    async def profile_edit_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            weight = float(update.message.text)
            if weight <= 0:
                raise ValueError
            context.user_data['edit_weight'] = weight
            await update.message.reply_text("Введи новое количество сна (часов):")
            return PROFILE_EDIT_SLEEP
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return PROFILE_EDIT_WEIGHT

    async def profile_edit_sleep(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            sleep = float(update.message.text)
            if sleep <= 0:
                raise ValueError
            user_id = context.user_data['edit_user_id']
            cursor = self.db.conn.cursor()
            cursor.execute("""
                UPDATE users SET name=?, height=?, weight=?, sleep_hours=?
                WHERE id=?
            """, (context.user_data['edit_name'], context.user_data['edit_height'],
                  context.user_data['edit_weight'], sleep, user_id))
            self.db.conn.commit()
            self.db.add_weight_record(user_id, context.user_data['edit_weight'])
            await update.message.reply_text("Профиль обновлён!")
            context.user_data.clear()
            await self.menu(update, context)
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Пожалуйста, введи положительное число.")
            return PROFILE_EDIT_SLEEP

    # ----- Управление тренировками (краткая статистика) -----
    async def workout_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.training_menu(update, context)

    # ----- Вспомогательные методы -----
    async def _send_long_message(self, update: Update, text: str, parse_mode: str = None):
        if len(text) <= 4000:
            await update.message.reply_text(text, parse_mode=parse_mode)
        else:
            for i in range(0, len(text), 4000):
                await update.message.reply_text(text[i:i+4000], parse_mode=parse_mode)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
        if isinstance(context.error, TimedOut):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ Произошла ошибка соединения. Пожалуйста, попробуйте ещё раз."
                )
            except:
                pass

    def run(self):
        self.application.run_polling()