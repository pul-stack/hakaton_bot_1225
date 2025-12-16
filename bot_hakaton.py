import asyncio
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv  # <-- ДОБАВИТЬ ИМПОРТ

# Загружаем переменные окружения из .env файла
load_dotenv()  # <-- ДОБАВИТЬ ЭТУ СТРОЧКУ

# Настройка логирования
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))  # <-- ИЗМЕНИТЬ
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # <-- ИЗМЕНИТЬ
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]  # <-- ИЗМЕНИТЬ

# Проверка наличия токена
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

# Инициализация бота
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ========== МОК-ДАННЫЕ И ЗАГЛУШКИ ==========

class MockDatabase:
    """Заглушка для работы с базой знаний"""
    
    @staticmethod
    async def search_knowledge_base(query: str) -> Dict[str, Any]:
        """Поиск в базе знаний"""
        return {
            "found": True,
            "answer": "Это типовой ответ из базы знаний. Для решения проблемы выполните следующие шаги: 1. Проверьте доступ 2. Перезапустите сервис 3. Обратитесь к инструкции",
            "confidence": 0.85,
            "source": "База знаний: Инструкция по работе с сервисом"
        }
    
    @staticmethod
    async def get_similar_tickets(problem: str) -> list:
        """Поиск похожих обращений"""
        return [
            {"id": 123, "problem": "Не работает доступ", "solution": "Обновить права доступа"},
            {"id": 456, "problem": "Ошибка при входе", "solution": "Очистить кэш браузера"}
        ]

class MockLLMService:
    """Заглушка для LLM сервиса"""
    
    @staticmethod
    async def analyze_problem(user_message: str) -> Dict[str, Any]:
        """Анализ проблемы с помощью LLM"""
        return {
            "category": "Техническая проблема",
            "subcategory": "Проблемы с доступом",
            "critical_level": "medium",  # low, medium, high, critical
            "requires_human": False,
            "confidence": 0.78,
            "summary": "Пользователь испытывает проблемы с доступом к внутреннему сервису"
        }
    
    @staticmethod
    async def generate_response(problem: str, context: Dict = None) -> str:
        """Генерация ответа с помощью LLM"""
        return f"На основе анализа вашей проблемы '{problem[:50]}...', рекомендую выполнить стандартную процедуру устранения неполадок."

class MockTicketSystem:
    """Заглушка для системы тикетов"""
    
    @staticmethod
    async def create_ticket(problem: str, user_id: int, category: str, critical_level: str) -> Dict[str, Any]:
        """Создание тикета"""
        return {
            "ticket_id": f"TICKET-{datetime.now().strftime('%Y%m%d')}-{user_id}",
            "status": "created",
            "assigned_to": "first_line_support",
            "estimated_response": "30 минут",
            "message": "Обращение создано и передано специалисту 1-й линии поддержки"
        }
    
    @staticmethod
    async def escalate_ticket(ticket_id: str, reason: str, target_line: str = "second_line") -> Dict[str, Any]:
        """Эскалация тикета на другую линию поддержки"""
        return {
            "success": True,
            "message": f"Тикет {ticket_id} эскалирован на {target_line} линию поддержки",
            "new_line": target_line
        }

# ========== СОСТОЯНИЯ БОТА ==========

class SupportStates(StatesGroup):
    waiting_for_problem = State()
    evaluating_solution = State()
    waiting_feedback = State()
    in_human_support = State()

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard():
    """Основная клавиатура"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать обращение")],
            [KeyboardButton(text="❓ Частые вопросы"), KeyboardButton(text="📊 Статус обращения")],
            [KeyboardButton(text="🆘 Срочная помощь"), KeyboardButton(text="👨‍💻 Связаться с оператором")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_feedback_keyboard():
    """Клавиатура для обратной связи"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, помогло", callback_data="feedback_yes"),
                InlineKeyboardButton(text="❌ Нет, не помогло", callback_data="feedback_no")
            ],
            [InlineKeyboardButton(text="🔄 Нужна дополнительная помощь", callback_data="feedback_more")]
        ]
    )

def get_escalation_keyboard():
    """Клавиатура для эскалации"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Эскалировать на 2-ю линию", callback_data="escalate_second")],
            [InlineKeyboardButton(text="🚨 Эскалировать на 3-ю линию", callback_data="escalate_third")],
            [InlineKeyboardButton(text="⏱ Оставить на 1-й линии", callback_data="escalate_no")]
        ]
    )

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = """🤖 Добро пожаловать в AI-агент поддержки Сбер!
    
Я помогу вам решить проблемы с внутренними сервисами банка:
• Автоматически анализирую вашу проблему
• Предлагаю решения из базы знаний
• Создаю обращения к специалистам
• Эскалирую сложные вопросы

Выберите действие или просто опишите вашу проблему:"""
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(F.text == "📝 Создать обращение")
@dp.message(F.text == "🆘 Срочная помощь")
async def start_problem_dialog(message: types.Message, state: FSMContext):
    """Начало диалога по проблеме"""
    await message.answer("Пожалуйста, подробно опишите вашу проблему или вопрос:")
    await state.set_state(SupportStates.waiting_for_problem)

@dp.message(F.text == "❓ Частые вопросы")
async def show_faq(message: types.Message):
    """Показать частые вопросы"""
    faq_text = """📚 Частые вопросы:
    
1. Как получить доступ к системе?
   - Обратитесь к руководителю для оформления заявки

2. Не работает вход в личный кабинет
   - Проверьте подключение к VPN
   - Очистите кэш браузера

3. Ошибка при формировании отчета
   - Проверьте права доступа
   - Убедитесь, что все обязательные поля заполнены

4. Медленная работа системы
   - Проверьте скорость интернета
   - Закройте неиспользуемые вкладки"""
    
    await message.answer(faq_text)

@dp.message(F.text == "📊 Статус обращения")
async def check_ticket_status(message: types.Message):
    """Проверка статуса обращения"""
    # Заглушка для проверки статуса
    status = await MockTicketSystem.create_ticket("", message.from_user.id, "check", "low")
    await message.answer(f"📊 Ваше последнее обращение:\nID: {status['ticket_id']}\nСтатус: В обработке\nОжидайте ответа в течение 30 минут")

@dp.message(F.text == "👨‍💻 Связаться с оператором")
async def connect_to_human(message: types.Message, state: FSMContext):
    """Подключение к оператору"""
    await message.answer("🔄 Подключаю вас к специалисту поддержки...")
    
    # Заглушка создания тикета для оператора
    ticket = await MockTicketSystem.create_ticket(
        "Запрос на подключение оператора",
        message.from_user.id,
        "human_support",
        "medium"
    )
    
    await message.answer(
        f"✅ Обращение создано: {ticket['ticket_id']}\n"
        f"Специалист свяжется с вами в течение 15 минут\n"
        f"Текущий статус: {ticket['status']}"
    )
    
    await state.set_state(SupportStates.in_human_support)

@dp.message(SupportStates.waiting_for_problem)
async def handle_problem_description(message: types.Message, state: FSMContext):
    """Обработка описания проблемы"""
    user_problem = message.text
    
    await message.answer("🔍 Анализирую вашу проблему...")
    
    # 1. Анализ проблемы через LLM
    analysis = await MockLLMService.analyze_problem(user_problem)
    await asyncio.sleep(1)  # Имитация обработки
    
    # 2. Поиск в базе знаний
    knowledge_result = await MockDatabase.search_knowledge_base(user_problem)
    
    # Сохраняем данные в состоянии
    await state.update_data(
        problem=user_problem,
        analysis=analysis,
        knowledge_result=knowledge_result
    )
    
    # Формируем ответ
    response_text = f"""📋 Результат анализа:
    
**Категория:** {analysis['category']}
**Критичность:** {analysis['critical_level']}
**Уверенность:** {analysis['confidence']*100:.1f}%

💡 **Рекомендуемое решение:**
{knowledge_result['answer'] if knowledge_result['found'] else 'Решение не найдено в базе знаний'}

Это решение помогло?"""
    
    if knowledge_result['found']:
        await message.answer(response_text, reply_markup=get_feedback_keyboard())
        await state.set_state(SupportStates.evaluating_solution)
    else:
        # Если решение не найдено, сразу создаем тикет
        await message.answer("❌ Решение не найдено в базе знаний. Создаю обращение к специалисту...")
        await create_support_ticket(message, state, user_problem, analysis)

@dp.callback_query(F.data.startswith("feedback_"))
async def handle_feedback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка обратной связи"""
    feedback = callback.data.split("_")[1]
    user_data = await state.get_data()
    
    if feedback == "yes":
        await callback.message.answer("✅ Отлично! Рад, что смог помочь! Если возникнут еще вопросы - обращайтесь!")
        await state.clear()
    elif feedback == "no":
        await callback.message.answer("❌ Жаль, что не помогло. Создаю обращение к специалисту поддержки...")
        await create_support_ticket(
            callback.message, 
            state, 
            user_data.get('problem', 'Проблема не решена'),
            user_data.get('analysis', {})
        )
    elif feedback == "more":
        await callback.message.answer("🔄 Ищу дополнительные решения...")
        # Поиск похожих тикетов
        similar = await MockDatabase.get_similar_tickets(user_data.get('problem', ''))
        if similar:
            similar_text = "\n".join([f"• {t['problem']}: {t['solution']}" for t in similar[:3]])
            await callback.message.answer(f"📚 Нашел похожие решения:\n{similar_text}")
        else:
            await callback.message.answer("Дополнительных решений не найдено. Создаю обращение...")
            await create_support_ticket(
                callback.message, 
                state, 
                user_data.get('problem', ''),
                user_data.get('analysis', {})
            )
    
    await callback.answer()

async def create_support_ticket(message, state, problem, analysis):
    """Создание тикета поддержки"""
    # Определяем линию поддержки на основе критичности
    critical_level = analysis.get('critical_level', 'medium')
    
    if critical_level in ['high', 'critical']:
        support_line = "second_line"
        line_name = "2-ю линию"
    else:
        support_line = "first_line"
        line_name = "1-ю линию"
    
    # Создаем тикет
    ticket = await MockTicketSystem.create_ticket(
        problem=problem,
        user_id=message.from_user.id,
        category=analysis.get('category', 'Общая проблема'),
        critical_level=critical_level
    )
    
    ticket_text = f"""✅ Обращение создано!

📋 **Детали обращения:**
ID: {ticket['ticket_id']}
Категория: {analysis.get('category', 'Не определена')}
Критичность: {critical_level}
Назначено: {line_name}
Ожидайте ответа: {ticket.get('estimated_response', 'в ближайшее время')}

Ваш вопрос будет обработан специалистом."""
    
    await message.answer(ticket_text)
    
    # Предлагаем эскалацию для критичных проблем
    if critical_level in ['high', 'critical']:
        await message.answer("⚠️ Проблема определена как критичная. Эскалировать на более высокую линию?", 
                           reply_markup=get_escalation_keyboard())
    
    await state.set_state(SupportStates.waiting_feedback)

@dp.callback_query(F.data.startswith("escalate_"))
async def handle_escalation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка эскалации"""
    action = callback.data.split("_")[1]
    user_data = await state.get_data()
    
    if action == "second":
        result = await MockTicketSystem.escalate_ticket("TICKET-123", "Критичная проблема", "second_line")
        await callback.message.answer(f"🚀 {result['message']}")
    elif action == "third":
        result = await MockTicketSystem.escalate_ticket("TICKET-123", "Очень критичная проблема", "third_line")
        await callback.message.answer(f"🚨 {result['message']}")
    else:
        await callback.message.answer("⏱ Обращение осталось на текущей линии поддержки")
    
    await state.clear()
    await callback.answer()

@dp.message(SupportStates.in_human_support)
async def handle_human_support(message: types.Message):
    """Обработка сообщений в режиме поддержки от человека"""
    await message.answer("💬 Ваше сообщение передано специалисту. Ожидайте ответа.")

@dp.message()
async def handle_any_message(message: types.Message, state: FSMContext):
    """Обработка любых других сообщений"""
    current_state = await state.get_state()
    
    if current_state is None:
        # Если нет активного состояния, начинаем диалог о проблеме
        await message.answer("Чтобы начать работу с поддержкой, опишите вашу проблему или используйте меню:")
        await state.set_state(SupportStates.waiting_for_problem)
    else:
        await message.answer("Пожалуйста, используйте меню или дождитесь обработки текущего запроса.")

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика бота (только для админов)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде")
        return
    
    stats_text = """📊 Статистика AI-агента поддержки:
    
• Обработано запросов: 1567
• Автоматически решено: 1243 (79.3%)
• Эскалировано на 2-ю линию: 187
• Эскалировано на 3-ю линию: 45
• Среднее время ответа: 2.1 мин
• Удовлетворенность: 92%"""
    
    await message.answer(stats_text)

@dp.message(Command("update_kb"))
async def cmd_update_kb(message: types.Message):
    """Обновление базы знаний (заглушка)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде")
        return
    
    await message.answer("🔄 Запрос на обновление базы знаний отправлен. Это может занять несколько минут.")

# ========== ЗАПУСК БОТА ==========

async def main():
    """Основная функция запуска бота"""
    print("🤖 AI-агент поддержки Сбер запускается...")
    print("Бот готов к работе!")
    
    # Пропускаем накопившиеся апдейты и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())