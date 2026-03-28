import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class TrainingDB:
    """Класс для работы с базой данных SQLite."""

    def __init__(self, db_path="training.db"):
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()
        self._add_indexes()

    def _connect(self):
        """Устанавливает соединение с БД и включает поддержку внешних ключей."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _create_tables(self):
        cursor = self.conn.cursor()
        # Мышечные группы (категории упражнений)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS muscle_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
        # Мышцы
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS muscles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                group_id INTEGER,
                FOREIGN KEY (group_id) REFERENCES muscle_groups(id)
            )
        """)
        # Упражнения
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                load_type TEXT CHECK(load_type IN ('weight', 'bodyweight')) NOT NULL,
                bodyweight_factor REAL,
                category_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES muscle_groups(id)
            )
        """)
        # Связь упражнения-мышцы
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exercise_muscle (
                exercise_id INTEGER,
                muscle_id INTEGER,
                percentage REAL NOT NULL,
                PRIMARY KEY (exercise_id, muscle_id),
                FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
                FOREIGN KEY (muscle_id) REFERENCES muscles(id) ON DELETE CASCADE
            )
        """)
        # Пользователи
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                height REAL,
                weight REAL,
                sleep_hours REAL,
                telegram_id INTEGER UNIQUE
            )
        """)
        # История веса
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weight_history (
                user_id INTEGER,
                date DATE,
                weight REAL,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Тренировки
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                datetime DATETIME NOT NULL,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Выполненные упражнения
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workout_exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id INTEGER NOT NULL,
                exercise_id INTEGER NOT NULL,
                sets INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight REAL,
                FOREIGN KEY (workout_id) REFERENCES workouts(id) ON DELETE CASCADE,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)
        # Личные рекорды
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personal_bests (
                user_id INTEGER,
                exercise_id INTEGER,
                weight REAL,
                date DATETIME,
                PRIMARY KEY (user_id, exercise_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)
        # Шаблоны тренировок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workout_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS template_exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                exercise_id INTEGER NOT NULL,
                sets INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight REAL,
                FOREIGN KEY (template_id) REFERENCES workout_templates(id) ON DELETE CASCADE,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)
        # Целевые проценты для анализа баланса
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS target_ratios (
                muscle_name TEXT PRIMARY KEY,
                target_percent REAL NOT NULL
            )
        """)
        self.conn.commit()

    def _add_indexes(self):
        """Добавляет индексы для ускорения запросов."""
        cursor = self.conn.cursor()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workouts_user_id ON workouts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workouts_datetime ON workouts(datetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workout_exercises_workout ON workout_exercises(workout_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exercise_muscle_muscle ON exercise_muscle(muscle_id)")
        self.conn.commit()

    # ---------- Работа с пользователями ----------
    def add_user(self, name: str, height: float, weight: float, sleep_hours: float, telegram_id: int = None) -> int:
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (name, height, weight, sleep_hours, telegram_id)
                VALUES (?, ?, ?, ?, ?)
            """, (name, height, weight, sleep_hours, telegram_id))
            self.conn.commit()
            user_id = cursor.lastrowid
            self.add_weight_record(user_id, weight)
            return user_id
        except sqlite3.IntegrityError as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            raise

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_user_weight(self, user_id: int, new_weight: float):
        cursor = self.conn.cursor()
        try:
            cursor.execute("UPDATE users SET weight = ? WHERE id = ?", (new_weight, user_id))
            self.add_weight_record(user_id, new_weight)
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления веса: {e}")
            self.conn.rollback()
            raise

    def add_weight_record(self, user_id: int, weight: float, date: str = None):
        """Добавляет запись веса за указанную дату (по умолчанию сегодня)."""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM weight_history WHERE user_id = ? AND date = ?", (user_id, date))
            if cursor.fetchone():
                cursor.execute("UPDATE weight_history SET weight = ? WHERE user_id = ? AND date = ?",
                               (weight, user_id, date))
            else:
                cursor.execute("INSERT INTO weight_history (user_id, date, weight) VALUES (?, ?, ?)",
                               (user_id, date, weight))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления записи веса: {e}")
            self.conn.rollback()
            raise

    def get_user_weight_at_date(self, user_id: int, target_date: datetime) -> float:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT weight FROM weight_history
            WHERE user_id = ? AND date <= date(?)
            ORDER BY date DESC LIMIT 1
        """, (user_id, target_date.strftime('%Y-%m-%d')))
        row = cursor.fetchone()
        if row:
            return row['weight']
        cursor.execute("SELECT weight FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return row['weight'] if row else 0.0

    # ---------- Работа с мышцами и группами ----------
    def add_muscle_group(self, name: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO muscle_groups (name) VALUES (?)", (name,))
        self.conn.commit()
        cursor.execute("SELECT id FROM muscle_groups WHERE name = ?", (name,))
        return cursor.fetchone()['id']

    def get_all_muscle_groups(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM muscle_groups ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def add_muscle(self, name: str, group_id: int = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO muscles (name, group_id) VALUES (?, ?)", (name, group_id))
        self.conn.commit()
        cursor.execute("SELECT id FROM muscles WHERE name = ?", (name,))
        return cursor.fetchone()['id']

    def get_muscle(self, muscle_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM muscles WHERE id = ?", (muscle_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_muscles(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM muscles ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def get_muscles_by_group(self, group_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM muscles WHERE group_id = ? ORDER BY name", (group_id,))
        return [dict(row) for row in cursor.fetchall()]

    # ---------- Работа с упражнениями ----------
    def add_exercise(self, name: str, load_type: str, bodyweight_factor: float = None, description: str = "",
                     category_id: int = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO exercises (name, description, load_type, bodyweight_factor, category_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, description, load_type, bodyweight_factor, category_id))
        self.conn.commit()
        return cursor.lastrowid

    def set_exercise_muscles(self, exercise_id: int, muscle_percentages: Dict[int, float]):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM exercise_muscle WHERE exercise_id = ?", (exercise_id,))
        for mid, pct in muscle_percentages.items():
            cursor.execute("INSERT INTO exercise_muscle (exercise_id, muscle_id, percentage) VALUES (?, ?, ?)",
                           (exercise_id, mid, pct))
        self.conn.commit()

    def get_exercise(self, exercise_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_exercises(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM exercises ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def get_exercise_muscles(self, exercise_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT m.id, m.name, em.percentage
            FROM exercise_muscle em
            JOIN muscles m ON em.muscle_id = m.id
            WHERE em.exercise_id = ?
        """, (exercise_id,))
        return [dict(row) for row in cursor.fetchall()]

    # ---------- Запись тренировок ----------
    def add_workout(self, user_id: int, dt: datetime, notes: str = "") -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO workouts (user_id, datetime, notes)
            VALUES (?, ?, ?)
        """, (user_id, dt.isoformat(), notes))
        self.conn.commit()
        return cursor.lastrowid

    def add_workout_exercise(self, workout_id: int, exercise_id: int, sets: int, reps: int, weight: float):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO workout_exercises (workout_id, exercise_id, sets, reps, weight)
                VALUES (?, ?, ?, ?, ?)
            """, (workout_id, exercise_id, sets, reps, weight))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления упражнения в тренировку: {e}")
            self.conn.rollback()
            raise

    def get_workouts(self, user_id: int, limit: int = 50) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM workouts
            WHERE user_id = ?
            ORDER BY datetime DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_workout_exercises(self, workout_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT we.*, e.name, e.load_type, e.bodyweight_factor
            FROM workout_exercises we
            JOIN exercises e ON we.exercise_id = e.id
            WHERE we.workout_id = ?
        """, (workout_id,))
        return [dict(row) for row in cursor.fetchall()]

    def delete_workout(self, workout_id: int):
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM workout_exercises WHERE workout_id = ?", (workout_id,))
            cursor.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Ошибка удаления тренировки: {e}")
            self.conn.rollback()
            raise

    # ---------- Расчёт нагрузки за тренировку ----------
    def calculate_muscle_load_for_workout(self, workout_id: int) -> Dict[int, float]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id, datetime FROM workouts WHERE id = ?", (workout_id,))
        wdata = cursor.fetchone()
        if not wdata:
            return {}
        user_id = wdata['user_id']
        workout_dt = datetime.fromisoformat(wdata['datetime'])
        user_weight = self.get_user_weight_at_date(user_id, workout_dt)

        exercises = self.get_workout_exercises(workout_id)
        muscle_load = {}
        for ex in exercises:
            if ex['load_type'] == 'bodyweight':
                if ex['bodyweight_factor'] is None:
                    continue
                load_per_set = user_weight * ex['bodyweight_factor']
            else:
                load_per_set = ex['weight']

            total_ex_load = load_per_set * ex['sets'] * ex['reps']

            muscles = self.get_exercise_muscles(ex['exercise_id'])
            for m in muscles:
                mid = m['id']
                muscle_load[mid] = muscle_load.get(mid, 0) + total_ex_load * (m['percentage'] / 100.0)

        return muscle_load

    # ---------- Шаблоны тренировок ----------
    def add_template(self, user_id: int, name: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO workout_templates (user_id, name) VALUES (?, ?)", (user_id, name))
        self.conn.commit()
        return cursor.lastrowid

    def get_templates(self, user_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM workout_templates WHERE user_id = ? ORDER BY name", (user_id,))
        return [dict(row) for row in cursor.fetchall()]

    def add_template_exercise(self, template_id: int, exercise_id: int, sets: int, reps: int, weight: float = None):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO template_exercises (template_id, exercise_id, sets, reps, weight)
            VALUES (?, ?, ?, ?, ?)
        """, (template_id, exercise_id, sets, reps, weight))
        self.conn.commit()

    def get_template_exercises(self, template_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT te.*, e.name, e.load_type
            FROM template_exercises te
            JOIN exercises e ON te.exercise_id = e.id
            WHERE te.template_id = ?
        """, (template_id,))
        return [dict(row) for row in cursor.fetchall()]

    def apply_template(self, template_id: int, workout_id: int):
        """Копирует упражнения из шаблона в тренировку."""
        exercises = self.get_template_exercises(template_id)
        for ex in exercises:
            self.add_workout_exercise(
                workout_id=workout_id,
                exercise_id=ex['exercise_id'],
                sets=ex['sets'],
                reps=ex['reps'],
                weight=ex['weight'] if ex['weight'] is not None else 0.0
            )

    # ---------- Вспомогательные методы ----------
    def get_muscle_id_by_name(self, name: str) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM muscles WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row['id'] if row else None

    def get_exercise_categories(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM muscle_groups ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def get_exercises_by_category(self, category_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM exercises WHERE category_id = ? ORDER BY name", (category_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_exercises_for_muscle(self, muscle_id: int, min_percentage: float = 30) -> List[Dict]:
        """Возвращает упражнения, в которых указанная мышца задействована не менее min_percentage процентов."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT e.*, em.percentage
            FROM exercises e
            JOIN exercise_muscle em ON e.id = em.exercise_id
            WHERE em.muscle_id = ? AND em.percentage >= ?
            ORDER BY em.percentage DESC
        """, (muscle_id, min_percentage))
        return [dict(row) for row in cursor.fetchall()]

    # ---------- Целевые проценты для баланса ----------
    def set_target_ratios(self, ratios: Dict[str, float]):
        """Сохраняет целевые проценты в БД."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM target_ratios")
        for muscle, percent in ratios.items():
            cursor.execute("INSERT INTO target_ratios (muscle_name, target_percent) VALUES (?, ?)",
                           (muscle, percent))
        self.conn.commit()

    def get_target_ratios(self) -> Dict[str, float]:
        """Загружает целевые проценты из БД."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT muscle_name, target_percent FROM target_ratios")
        rows = cursor.fetchall()
        if rows:
            return {row['muscle_name']: row['target_percent'] for row in rows}
        else:
            # Возвращаем стандартные, если таблица пуста
            default = {
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
            total = sum(default.values())
            factor = 100 / total
            return {k: round(v * factor, 1) for k, v in default.items()}