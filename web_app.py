import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

from database import TrainingDB
from calculator import MuscleCalculator

# Конфигурация
SECRET_KEY = "your-secret-key"  # замените на реальный секрет
DATABASE_URL = "sqlite:///./training.db"  # используем ту же БД

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Подключение статики и шаблонов
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# SQLAlchemy для пользователей (добавляем таблицу веб-пользователей)
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class WebUser(Base):
    __tablename__ = "web_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))  # связь с существующей таблицей users

Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Инициализация нашей БД и калькулятора
db = TrainingDB("training.db")
calc = MuscleCalculator(db)

# Вспомогательные функции аутентификации
def get_current_user(request: Request, db: Session = None):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    if db is None:
        db = SessionLocal()
    user = db.query(WebUser).filter(WebUser.id == user_id).first()
    return user

# Маршруты
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    db_session = SessionLocal()
    user = db_session.query(WebUser).filter(WebUser.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверные данные")
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, username: str = Form(...), email: str = Form(...),
                   password: str = Form(...), name: str = Form(...),
                   height: float = Form(...), weight: float = Form(...),
                   sleep_hours: float = Form(...)):
    db_session = SessionLocal()
    # Проверяем, не занято ли имя
    if db_session.query(WebUser).filter(WebUser.username == username).first():
        raise HTTPException(status_code=400, detail="Имя пользователя занято")
    # Создаём запись в основной таблице users (TrainingDB)
    # Используем существующий метод add_user, который требует telegram_id=None
    user_id = db.add_user(name=name, height=height, weight=weight,
                          sleep_hours=sleep_hours, telegram_id=None)
    # Создаём веб-пользователя
    hashed = pwd_context.hash(password)
    web_user = WebUser(username=username, email=email, hashed_password=hashed, user_id=user_id)
    db_session.add(web_user)
    db_session.commit()
    request.session["user_id"] = web_user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

# Страница добавления тренировки
@app.get("/add_workout", response_class=HTMLResponse)
async def add_workout_page(request: Request, user: WebUser = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    exercises = db.get_all_exercises()
    return templates.TemplateResponse("add_workout.html", {"request": request, "exercises": exercises})

@app.post("/add_workout")
async def add_workout(request: Request, user: WebUser = Depends(get_current_user),
                      exercise_id: int = Form(...), sets: int = Form(...),
                      reps: int = Form(...), weight: float = Form(...)):
    if not user:
        return RedirectResponse(url="/login")
    # Создаём новую тренировку (на текущую дату)
    workout_id = db.add_workout(user.user_id, datetime.now())
    db.add_workout_exercise(workout_id, exercise_id, sets, reps, weight)
    calc.clear_cache()
    return RedirectResponse(url="/stats", status_code=303)

# Страница статистики
@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request, user: WebUser = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    muscles = db.get_all_muscles()
    stats_data = []
    for muscle in muscles:
        dev = calc.get_muscle_development(user.user_id, muscle['id'])
        stats_data.append({
            "name": muscle['name'],
            "total_load": dev['total_load_30d'],
            "avg_load": dev['avg_load_per_workout'],
            "workout_count": dev['workout_count'],
            "delta_percent": dev['delta_percent']
        })
    return templates.TemplateResponse("stats.html", {"request": request, "stats": stats_data})

# Страница баланса
@app.get("/balance", response_class=HTMLResponse)
async def balance(request: Request, user: WebUser = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    result = calc.analyze_muscle_balance(user.user_id, days=60)
    if "error" in result:
        error = result["error"]
        return templates.TemplateResponse("balance.html", {"request": request, "error": error})
    return templates.TemplateResponse("balance.html", {"request": request, "result": result})

# Страница сна/воды
@app.get("/sleep_water", response_class=HTMLResponse)
async def sleep_water(request: Request, user: WebUser = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    water_today = db.get_water_intake(user.user_id)
    sleep_today = db.get_sleep_history(user.user_id, days=1)[0]['hours'] if db.get_sleep_history(user.user_id, days=1) else None
    return templates.TemplateResponse("sleep_water.html", {"request": request, "water_today": water_today, "sleep_today": sleep_today})

@app.post("/add_water")
async def add_water(request: Request, user: WebUser = Depends(get_current_user),
                    amount: float = Form(...)):
    if not user:
        return RedirectResponse(url="/login")
    db.add_water_intake(user.user_id, amount)
    return RedirectResponse(url="/sleep_water", status_code=303)

@app.post("/add_sleep")
async def add_sleep(request: Request, user: WebUser = Depends(get_current_user),
                    hours: float = Form(...)):
    if not user:
        return RedirectResponse(url="/login")
    db.add_sleep_record(user.user_id, hours)
    return RedirectResponse(url="/sleep_water", status_code=303)

# Запуск
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)