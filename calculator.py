from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database import TrainingDB
import matplotlib.pyplot as plt
import io
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class MuscleCalculator:
    """Класс для расчёта нагрузки и аналитики."""

    def __init__(self, db: TrainingDB):
        self.db = db

    def get_muscle_load_over_period(self, user_id: int, muscle_id: int, days: int) -> float:
        """Суммарная нагрузка на мышцу за последние N дней (оптимизированный SQL)."""
        end = datetime.now()
        start = end - timedelta(days=days)
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT SUM(we.sets * we.reps * 
                CASE WHEN e.load_type = 'bodyweight' THEN (uw.weight * e.bodyweight_factor)
                     ELSE we.weight END * (em.percentage / 100.0)) as total
            FROM workouts w
            JOIN workout_exercises we ON w.id = we.workout_id
            JOIN exercises e ON we.exercise_id = e.id
            JOIN exercise_muscle em ON e.id = em.exercise_id
            JOIN (
                SELECT user_id, date, weight FROM weight_history
            ) uw ON uw.user_id = w.user_id AND uw.date <= date(w.datetime)
            WHERE w.user_id = ? AND em.muscle_id = ? AND w.datetime BETWEEN ? AND ?
            GROUP BY w.id
        """, (user_id, muscle_id, start.isoformat(), end.isoformat()))
        rows = cursor.fetchall()
        return sum(row['total'] for row in rows if row['total'] is not None)

    @lru_cache(maxsize=128)
    def get_muscle_development(self, user_id: int, muscle_id: int) -> Dict:
        """Сравнение последних 30 дней с предыдущими 30 (с кэшированием)."""
        load_30 = self.get_muscle_load_over_period(user_id, muscle_id, 30)
        load_60 = self.get_muscle_load_over_period(user_id, muscle_id, 60)
        load_prev = load_60 - load_30

        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT w.id) as cnt
            FROM workouts w
            JOIN workout_exercises we ON w.id = we.workout_id
            JOIN exercise_muscle em ON we.exercise_id = em.exercise_id
            WHERE w.user_id = ? AND em.muscle_id = ? AND w.datetime >= ?
        """, (user_id, muscle_id, (datetime.now() - timedelta(days=30)).isoformat()))
        row = cursor.fetchone()
        count = row['cnt'] if row else 0

        avg_load = load_30 / count if count else 0
        delta = load_30 - load_prev
        delta_pct = (delta / load_prev * 100) if load_prev > 0 else 0

        return {
            'total_load_30d': round(load_30, 1),
            'avg_load_per_workout': round(avg_load, 1),
            'workout_count': count,
            'load_prev_30d': round(load_prev, 1),
            'delta_30d': round(delta, 1),
            'delta_percent': round(delta_pct, 1)
        }

    def clear_cache(self):
        """Сбрасывает кэш (например, после добавления новой тренировки)."""
        self.get_muscle_development.cache_clear()

    def optimal_training_frequency(self, user_id: int, muscle_id: int) -> Dict:
        """Анализ зависимости прироста нагрузки от интервала между тренировками."""
        workouts = self.db.get_workouts(user_id, limit=1000)
        workouts.sort(key=lambda x: x['datetime'])

        if len(workouts) < 2:
            return {}

        intervals = []
        gains = []
        prev_load = 0.0
        prev_date = None
        for w in workouts:
            load_dict = self.db.calculate_muscle_load_for_workout(w['id'])
            load = load_dict.get(muscle_id, 0.0)
            if prev_date is not None:
                interval = (datetime.fromisoformat(w['datetime']) - prev_date).days
                if interval > 0 and prev_load > 0 and load > 0:
                    intervals.append(interval)
                    gains.append(load - prev_load)
            prev_load = load
            prev_date = datetime.fromisoformat(w['datetime'])

        freq_map = {}
        for i, gain in zip(intervals, gains):
            if i not in freq_map:
                freq_map[i] = []
            freq_map[i].append(gain)

        result = {}
        for interval, gain_list in freq_map.items():
            result[interval] = {
                'count': len(gain_list),
                'avg_gain': round(sum(gain_list) / len(gain_list), 1),
                'gains': gain_list
            }
        return result

    def get_muscle_progress_plot(self, user_id: int, muscle_id: int, days: int = 90) -> Optional[bytes]:
        """Возвращает PNG график нагрузки на мышцу за последние days дней."""
        muscle = self.db.get_muscle(muscle_id)
        if not muscle:
            return None
        end = datetime.now()
        start = end - timedelta(days=days)
        workouts = self.db.get_workouts(user_id, limit=1000)
        dates = []
        loads = []
        for w in workouts:
            w_dt = datetime.fromisoformat(w['datetime'])
            if start <= w_dt <= end:
                load_dict = self.db.calculate_muscle_load_for_workout(w['id'])
                load = load_dict.get(muscle_id, 0.0)
                if load > 0:
                    dates.append(w_dt)
                    loads.append(load)
        if not dates:
            return None
        plt.figure(figsize=(10, 5))
        plt.plot(dates, loads, marker='o')
        plt.title(f'Прогресс: {muscle["name"]}')
        plt.xlabel('Дата')
        plt.ylabel('Нагрузка (кг)')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf.getvalue()

    def recommend_frequency(self, user_id: int, muscle_id: int, min_samples: int = 2) -> Optional[int]:
        freq_data = self.optimal_training_frequency(user_id, muscle_id)
        if not freq_data:
            return None
        best_interval = None
        best_gain = -float('inf')
        for interval, info in freq_data.items():
            if info['count'] >= min_samples and info['avg_gain'] > best_gain and interval >= 2:
                best_gain = info['avg_gain']
                best_interval = interval
        return best_interval

    def analyze_muscle_balance(self, user_id: int, days: int = 60) -> Dict:
        """
        Анализирует баланс нагрузки по мышцам за последние days дней.
        Возвращает словарь с результатами.
        """
        target_ratios = self.db.get_target_ratios()
        muscles = self.db.get_all_muscles()
        muscle_loads = {}
        total_load = 0.0
        for muscle in muscles:
            load = self.get_muscle_load_over_period(user_id, muscle['id'], days)
            muscle_loads[muscle['name']] = load
            total_load += load

        if total_load == 0:
            return {"error": f"Недостаточно данных за последние {days} дней"}

        actual_percent = {name: (load / total_load) * 100 for name, load in muscle_loads.items()}

        result = {}
        under = []
        over = []
        ok = []

        for name, target in target_ratios.items():
            actual = actual_percent.get(name, 0.0)
            deviation = actual - target
            status = "ok"
            if deviation < -2:
                status = "under"
                under.append(name)
            elif deviation > 2:
                status = "over"
                over.append(name)
            exercises = []
            if status == "under":
                muscle_id = next((m['id'] for m in muscles if m['name'] == name), None)
                if muscle_id:
                    exercises = self.db.get_exercises_for_muscle(muscle_id, min_percentage=30)
            result[name] = {
                "load": muscle_loads.get(name, 0),
                "target_percent": round(target, 1),
                "actual_percent": round(actual, 1),
                "deviation": round(deviation, 1),
                "status": status,
                "exercises": exercises[:3]
            }

        for name, actual in actual_percent.items():
            if name not in result and actual > 0.5:
                result[name] = {
                    "load": muscle_loads[name],
                    "target_percent": 0,
                    "actual_percent": round(actual, 1),
                    "deviation": round(actual, 1),
                    "status": "extra",
                    "exercises": []
                }

        return result