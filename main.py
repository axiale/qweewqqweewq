import logging
import os
from dotenv import load_dotenv, set_key
from database import TrainingDB
from calculator import MuscleCalculator
from telegram_bot import TrainingBot

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def add_exercise_if_not_exists(db: TrainingDB, name: str, load_type: str,
                               bodyweight_factor: float = None, description: str = "",
                               category_id: int = None, muscle_percentages: Dict[int, float] = None):
    """Добавляет упражнение, если его ещё нет в базе."""
    exercises = db.get_all_exercises()
    if any(ex['name'] == name for ex in exercises):
        print(f"Упражнение '{name}' уже существует, пропускаем.")
        return
    ex_id = db.add_exercise(name, load_type, bodyweight_factor, description, category_id)
    if muscle_percentages:
        db.set_exercise_muscles(ex_id, muscle_percentages)
    print(f"Добавлено упражнение: {name}")

def init_default_data(db: TrainingDB):
    """Инициализирует базу данных начальными данными (мышцы, упражнения, цели)."""
    # Если мышц нет, создаём их
    if not db.get_all_muscles():
        # --- Группы мышц (категории упражнений) ---
        group_chest = db.add_muscle_group("Грудь")
        group_back = db.add_muscle_group("Спина")
        group_legs = db.add_muscle_group("Ноги")
        group_shoulders = db.add_muscle_group("Плечи")
        group_arms = db.add_muscle_group("Руки")
        group_abs = db.add_muscle_group("Пресс")
        group_cardio = db.add_muscle_group("Кардио")
        group_plyo = db.add_muscle_group("Плиометрия")
        group_stretch = db.add_muscle_group("Растяжка")

        # --- Мышцы (с привязкой к группам) ---
        chest = db.add_muscle("Грудные", group_chest)
        triceps = db.add_muscle("Трицепс", group_arms)
        biceps = db.add_muscle("Бицепс", group_arms)
        delt_ant = db.add_muscle("Передняя дельта", group_shoulders)
        delt_mid = db.add_muscle("Средняя дельта", group_shoulders)
        delt_post = db.add_muscle("Задняя дельта", group_shoulders)
        latissimus = db.add_muscle("Широчайшие", group_back)
        trapezius = db.add_muscle("Трапеция", group_back)
        quadriceps = db.add_muscle("Квадрицепс", group_legs)
        hamstrings = db.add_muscle("Бицепс бедра", group_legs)
        glutes = db.add_muscle("Ягодичные", group_legs)
        calves = db.add_muscle("Икры", group_legs)
        abs_muscle = db.add_muscle("Пресс", group_abs)
        obliques = db.add_muscle("Косые мышцы живота", group_abs)
        lower_back = db.add_muscle("Разгибатели спины", group_back)
        forearms = db.add_muscle("Предплечья", group_arms)
        core = db.add_muscle("Кор", None)

        # Сохраняем ID групп для дальнейшего использования
        group_ids = {
            'chest': group_chest,
            'back': group_back,
            'legs': group_legs,
            'shoulders': group_shoulders,
            'arms': group_arms,
            'abs': group_abs,
            'cardio': group_cardio,
            'plyo': group_plyo,
            'stretch': group_stretch,
        }
        muscle_ids = {
            'chest': chest,
            'triceps': triceps,
            'biceps': biceps,
            'delt_ant': delt_ant,
            'delt_mid': delt_mid,
            'delt_post': delt_post,
            'latissimus': latissimus,
            'trapezius': trapezius,
            'quadriceps': quadriceps,
            'hamstrings': hamstrings,
            'glutes': glutes,
            'calves': calves,
            'abs': abs_muscle,
            'obliques': obliques,
            'lower_back': lower_back,
            'forearms': forearms,
            'core': core,
        }
    else:
        # Если мышцы уже есть, получаем их ID по именам
        group_chest = db.get_muscle_id_by_name("Грудь")  # но для категорий нужен другой метод
        # Получаем группы
        groups = db.get_all_muscle_groups()
        group_ids = {g['name']: g['id'] for g in groups}
        # Получаем мышцы
        muscles = db.get_all_muscles()
        muscle_ids = {m['name']: m['id'] for m in muscles}
        # Для удобства создадим переменные с теми же именами, что и в блоке создания
        chest = muscle_ids.get("Грудные")
        triceps = muscle_ids.get("Трицепс")
        biceps = muscle_ids.get("Бицепс")
        delt_ant = muscle_ids.get("Передняя дельта")
        delt_mid = muscle_ids.get("Средняя дельта")
        delt_post = muscle_ids.get("Задняя дельта")
        latissimus = muscle_ids.get("Широчайшие")
        trapezius = muscle_ids.get("Трапеция")
        quadriceps = muscle_ids.get("Квадрицепс")
        hamstrings = muscle_ids.get("Бицепс бедра")
        glutes = muscle_ids.get("Ягодичные")
        calves = muscle_ids.get("Икры")
        abs_muscle = muscle_ids.get("Пресс")
        obliques = muscle_ids.get("Косые мышцы живота")
        lower_back = muscle_ids.get("Разгибатели спины")
        forearms = muscle_ids.get("Предплечья")
        core = muscle_ids.get("Кор")

    # --- Базовые упражнения (со свободными весами) ---
    # Для каждого упражнения будем использовать add_exercise_if_not_exists
    # Это позволит добавлять только отсутствующие

    # Отжимания (Грудь)
    add_exercise_if_not_exists(db, "Отжимания классические", "bodyweight", 0.67,
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 55, triceps: 35, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания широким хватом", "bodyweight", 0.67,
                               description="Руки шире плеч, акцент на грудь",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 70, triceps: 20, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания узким хватом", "bodyweight", 0.67,
                               description="Ладони вместе или узко, локти прижаты",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={triceps: 60, chest: 30, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания ноги на возвышении", "bodyweight", 0.74,
                               description="Ноги на стуле/скамье, руки на полу",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 55, triceps: 35, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания руки на возвышении", "bodyweight", 0.60,
                               description="Руки на стуле/скамье, ноги на полу",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 50, triceps: 40, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания от стены", "bodyweight", 0.45,
                               description="Стоя лицом к стене, руки на стене",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 50, triceps: 40, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания алмазные", "bodyweight", 0.67,
                               description="Ладони вместе, большой и указательный палец образуют треугольник",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={triceps: 70, chest: 20, delt_ant: 10})
    add_exercise_if_not_exists(db, "Отжимания с хлопком", "bodyweight", 0.67,
                               description="Взрывные, с отрывом рук от пола",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 55, triceps: 35, delt_ant: 10})

    # Подтягивания (Спина)
    add_exercise_if_not_exists(db, "Подтягивания широким хватом к груди", "bodyweight", 0.95,
                               description="Хват сверху, шире плеч",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 70, biceps: 15, trapezius: 10, delt_post: 5})
    add_exercise_if_not_exists(db, "Подтягивания широким хватом за голову", "bodyweight", 0.95,
                               description="Осторожно, не травмировать плечи",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 60, trapezius: 20, delt_post: 15, biceps: 5})
    add_exercise_if_not_exists(db, "Подтягивания узким обратным хватом", "bodyweight", 0.95,
                               description="Ладони к себе, руки вместе",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={biceps: 60, latissimus: 30, trapezius: 10})
    add_exercise_if_not_exists(db, "Подтягивания узким прямым хватом", "bodyweight", 0.95,
                               description="Ладони от себя, руки вместе",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 50, biceps: 30, trapezius: 15, delt_post: 5})
    add_exercise_if_not_exists(db, "Австралийские подтягивания", "bodyweight", 0.60,
                               description="Низкая перекладина, тело под углом",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 50, biceps: 30, trapezius: 10, delt_post: 10})
    add_exercise_if_not_exists(db, "Вис на турнике", "bodyweight", 0.30,
                               description="Удержание прямых рук, можно с отягощением",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 40, biceps: 10, trapezius: 10, forearms: 40})

    # Пресс
    add_exercise_if_not_exists(db, "Скручивания", "bodyweight", 0.20,
                               description="Лёжа на спине, подъём корпуса",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 90, obliques: 10})
    add_exercise_if_not_exists(db, "Обратные скручивания", "bodyweight", 0.20,
                               description="Лёжа на спине, подъём таза и ног",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 80, obliques: 10, quadriceps: 10})
    add_exercise_if_not_exists(db, "Подъём ног в висе", "bodyweight", 0.70,
                               description="Вис на турнике, подъём прямых ног",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 70, obliques: 10, quadriceps: 20})
    add_exercise_if_not_exists(db, "Планка на локтях", "bodyweight", 0.30,
                               description="Удержание тела прямым на локтях и носках",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 60, core: 20, delt_ant: 5, glutes: 5, quadriceps: 10})
    add_exercise_if_not_exists(db, "Боковая планка", "bodyweight", 0.25,
                               description="Упор на одной руке/локте, тело боком",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={obliques: 70, abs_muscle: 20, delt_mid: 10})
    add_exercise_if_not_exists(db, "Складка (книжка)", "bodyweight", 0.25,
                               description="Лёжа на спине, одновременный подъём рук и ног",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 90, obliques: 10})
    add_exercise_if_not_exists(db, "Велосипед", "bodyweight", 0.20,
                               description="Лёжа на спине, имитация педалирования",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 50, obliques: 50})

    # Ноги
    add_exercise_if_not_exists(db, "Приседания", "bodyweight", 0.80,
                               description="Классические приседания без веса",
                               category_id=group_ids.get("Ноги"),
                               muscle_percentages={quadriceps: 50, hamstrings: 20, glutes: 30})
    add_exercise_if_not_exists(db, "Выпады", "bodyweight", 0.70,
                               description="Поочерёдные выпады вперёд",
                               category_id=group_ids.get("Ноги"),
                               muscle_percentages={quadriceps: 40, hamstrings: 30, glutes: 30})
    add_exercise_if_not_exists(db, "Ягодичный мостик", "bodyweight", 0.50,
                               description="Лёжа на спине, подъём таза",
                               category_id=group_ids.get("Ноги"),
                               muscle_percentages={glutes: 80, hamstrings: 20})
    add_exercise_if_not_exists(db, "Подъём на носки", "bodyweight", 1.0,
                               description="Стоя, подъём на носки",
                               category_id=group_ids.get("Ноги"),
                               muscle_percentages={calves: 100})

    # Спина дополнительно
    add_exercise_if_not_exists(db, "Гиперэкстензия на полу", "bodyweight", 0.30,
                               description="Лёжа на животе, подъём груди и ног",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={lower_back: 70, glutes: 20, hamstrings: 10})

    # --- НОВЫЕ ДОМАШНИЕ УПРАЖНЕНИЯ (для указанных мышц) ---
    add_exercise_if_not_exists(db, "Отжимания от скамьи (обратные)", "bodyweight", 0.50,
                               description="Руки на скамье/стуле сзади, ноги на полу",
                               category_id=group_ids.get("Руки"),
                               muscle_percentages={triceps: 80, chest: 10, delt_ant: 10})
    add_exercise_if_not_exists(db, "Сгибания рук с гантелями/бутылками", "weight",
                               description="Стоя, сгибания рук с весом (можно использовать бутылки с водой)",
                               category_id=group_ids.get("Руки"),
                               muscle_percentages={biceps: 90, forearms: 10})
    add_exercise_if_not_exists(db, "Сгибания запястий с гантелями", "weight",
                               description="Предплечья на бедре, сгибания кистей",
                               category_id=group_ids.get("Руки"),
                               muscle_percentages={forearms: 100})
    add_exercise_if_not_exists(db, "Шраги с гантелями/бутылками", "weight",
                               description="Пожимания плечами с весом",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={trapezius: 80, delt_mid: 10, delt_post: 10})
    add_exercise_if_not_exists(db, "Подъём гантелей перед собой", "weight",
                               description="Стоя, подъём прямых рук вперёд",
                               category_id=group_ids.get("Плечи"),
                               muscle_percentages={delt_ant: 90, delt_mid: 10})
    add_exercise_if_not_exists(db, "Махи гантелями в стороны", "weight",
                               description="Стоя, руки с гантелями в стороны",
                               category_id=group_ids.get("Плечи"),
                               muscle_percentages={delt_mid: 90, trapezius: 10})
    add_exercise_if_not_exists(db, "Разводка гантелей в наклоне", "weight",
                               description="Наклон вперёд, разведение рук в стороны",
                               category_id=group_ids.get("Плечи"),
                               muscle_percentages={delt_post: 80, trapezius: 10, latissimus: 10})
    add_exercise_if_not_exists(db, "Румынская тяга с гантелями", "weight",
                               description="Стоя, наклон с прямыми ногами, вес в руках",
                               category_id=group_ids.get("Ноги"),
                               muscle_percentages={hamstrings: 70, glutes: 20, lower_back: 10})
    add_exercise_if_not_exists(db, "Лодочка (супермен)", "bodyweight", 0.20,
                               description="Лёжа на животе, одновременный подъём рук и ног",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={lower_back: 70, glutes: 20, hamstrings: 10})
    add_exercise_if_not_exists(db, "Русский твист", "bodyweight", 0.20,
                               description="Сидя, ноги на весу, повороты корпуса с весом или без",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={obliques: 70, abs_muscle: 30})

    # --- НОВЫЕ УПРАЖНЕНИЯ НА ТУРНИКЕ (без оборудования) ---
    add_exercise_if_not_exists(db, "Подтягивания нейтральным хватом", "bodyweight", 0.95,
                               description="Ладони обращены друг к другу, хват уже плеч",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 65, biceps: 25, trapezius: 5, forearms: 5})
    add_exercise_if_not_exists(db, "Подтягивания с полотенцем", "bodyweight", 0.95,
                               description="Перекинуть полотенце через турник, держаться за его концы",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 50, biceps: 20, forearms: 30})
    add_exercise_if_not_exists(db, "Подтягивания уголком", "bodyweight", 0.95,
                               description="Подтягивания с удержанием прямых ног под углом 90°",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 60, abs_muscle: 20, biceps: 15, obliques: 5})
    add_exercise_if_not_exists(db, "Вис с подъёмом ног в стороны", "bodyweight", 0.30,
                               description="Вис на турнике, подъём прямых ног в стороны",
                               category_id=group_ids.get("Пресс"),
                               muscle_percentages={abs_muscle: 50, obliques: 40, quadriceps: 10})
    add_exercise_if_not_exists(db, "Выход силой", "bodyweight", 0.95,
                               description="Из виса выход в упор на прямые руки над турником",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 40, triceps: 30, chest: 15, delt_ant: 10, biceps: 5})
    add_exercise_if_not_exists(db, "Подтягивания с хлопком", "bodyweight", 0.95,
                               description="Взрывные подтягивания с хлопком в верхней точке",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 60, biceps: 20, trapezius: 10, delt_post: 10})

    # --- Базовые упражнения (со свободными весами) ---
    add_exercise_if_not_exists(db, "Жим штанги лёжа", "weight",
                               description="Классический жим",
                               category_id=group_ids.get("Грудь"),
                               muscle_percentages={chest: 70, triceps: 20, delt_ant: 10})
    add_exercise_if_not_exists(db, "Подтягивания широким хватом", "bodyweight", 0.90,
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 70, biceps: 20, trapezius: 10})
    add_exercise_if_not_exists(db, "Приседания со штангой", "weight",
                               category_id=group_ids.get("Ноги"),
                               muscle_percentages={quadriceps: 50, hamstrings: 30, glutes: 20})
    add_exercise_if_not_exists(db, "Жим гантелей стоя", "weight",
                               category_id=group_ids.get("Плечи"),
                               muscle_percentages={delt_ant: 50, delt_mid: 30, triceps: 20})
    add_exercise_if_not_exists(db, "Тяга штанги в наклоне", "weight",
                               category_id=group_ids.get("Спина"),
                               muscle_percentages={latissimus: 60, trapezius: 20, biceps: 20})

    # Сохраняем целевые проценты (если ещё не сохранены)
    target_ratios = db.get_target_ratios()
    if not target_ratios or all(v == 0 for v in target_ratios.values()):
        default_ratios = {
            "Грудные": 12,
            "Широчайшие": 12,
            "Трапеция": 5,
            "Разгибатели спины": 5,
            "Передняя дельта": 3.5,
            "Средняя дельта": 3.5,
            "Задняя дельта": 3,
            "Бицепс": 7,
            "Трицепс": 7,
            "Предплечья": 3,
            "Квадрицепс": 12,
            "Бицепс бедра": 8,
            "Ягодичные": 8,
            "Икры": 4,
            "Пресс": 7,
        }
        total = sum(default_ratios.values())
        factor = 100 / total
        norm_ratios = {k: round(v * factor, 1) for k, v in default_ratios.items()}
        db.set_target_ratios(norm_ratios)
        print("Целевые проценты сохранены.")

    print("База данных инициализирована/дополнена.")

def main():
    # Загружаем переменные из .env, если файл существует
    load_dotenv()
    db = TrainingDB("training.db")
    init_default_data(db)

    calc = MuscleCalculator(db)

    # Получаем токен из переменной окружения или предлагаем ввести
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        TOKEN = input("Введите токен Telegram бота: ").strip()
        # Сохраняем токен в .env (обновляем, если уже есть)
        set_key(".env", "BOT_TOKEN", TOKEN)
        os.environ["BOT_TOKEN"] = TOKEN

    bot = TrainingBot(TOKEN, db, calc)
    print("Бот запущен...")
    try:
        bot.run()
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()