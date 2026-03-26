import os
import secrets
import sqlite3
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_urlsafe(32))

# OpenRouter API
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# 🔥 ТОПОВЫЕ МОДЕЛИ С АВТОМАТИЧЕСКИМ FALLBACK
FALLBACK_MODELS = [
    {
        "id": "minimax/minimax-m2.5:free",
        "name": "🏆 MiniMax M2.5",
        "description": "Глобальный лидер! 80.2% SWE-bench, #1 в мире",
        "features": ["Агенты", "Кодинг", "#1 в мире", "197K контекст"]
    },
    {
        "id": "stepfun/step-3.5-flash:free",
        "name": "⚡ Step 3.5 Flash",
        "description": "1.35 трлн токенов/неделю, 256K контекста",
        "features": ["Скорость", "Бесплатно", "256K контекст"]
    },
    {
        "id": "arcee-ai/trinity-large-preview:free",
        "name": "🎨 Trinity Large",
        "description": "400B параметров, отлично для творчества",
        "features": ["Творчество", "400B", "131K контекст"]
    },
    {
        "id": "nvidia/nemotron-3-super:free",
        "name": "⚡ NVIDIA Nemotron 3 Super",
        "description": "1M контекста, скорость выше в 5 раз",
        "features": ["Скорость", "1M контекст", "OpenClaw"]
    },
    {
        "id": "qwen/qwen3-coder-480b-a35b-instruct:free",
        "name": "💻 Qwen3 Coder 480B",
        "description": "Специалист по программированию",
        "features": ["Кодинг", "262K", "Специалист"]
    },
    {
        "id": "google/gemini-2.5-flash-lite",
        "name": "🚀 Gemini 2.5 Flash-Lite",
        "description": "Быстрая модель от Google",
        "features": ["Скорость", "Google", "1M контекст"]
    }
]

# Основная модель
MAIN_MODEL = FALLBACK_MODELS[0]

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

class User(UserMixin):
    def __init__(self, id, email, name, avatar=None):
        self.id = id
        self.email = email
        self.name = name
        self.avatar = avatar

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['email'], user['name'], user.get('avatar'))
    return None

def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), 'users.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            avatar TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            email TEXT,
            message TEXT,
            rating INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            model TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных готова!")

def get_ai_response(messages):
    """Автоматическое переключение между моделями при ошибках"""
    if not OPENROUTER_API_KEY:
        return """⚠️ API ключ OpenRouter не настроен.

Получи бесплатный ключ:
1. Зарегистрируйся на https://openrouter.ai
2. Перейди в раздел Keys
3. Создай новый ключ
4. Добавь в .env: OPENROUTER_API_KEY=sk-or-v1-твой_ключ"""

    last_error = None
    used_models = []

    for model in FALLBACK_MODELS:
        try:
            used_models.append(model['name'])

            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "DeepSeek AI Chat"
            }

            data = {
                "model": model["id"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4000
            }

            response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']

            elif response.status_code == 429:
                last_error = f"Модель {model['name']} перегружена (429)"
                continue

            elif response.status_code == 402:
                last_error = f"Лимит {model['name']} исчерпан (402)"
                continue

            elif response.status_code == 404:
                last_error = f"Модель {model['name']} временно недоступна (404)"
                continue

            else:
                last_error = f"Ошибка {response.status_code} для {model['name']}"
                continue

        except requests.exceptions.Timeout:
            last_error = f"Таймаут {model['name']}"
            continue
        except Exception as e:
            last_error = f"Ошибка: {str(e)}"
            continue

    # Если все модели не сработали
    return f"""❌ Все модели временно недоступны.

Проверенные модели: {', '.join(used_models)}

Последняя ошибка: {last_error}

Рекомендации:
• Подожди 2-3 минуты и попробуй снова
• Проверь API ключ в .env файле
• Бесплатный лимит: 50 сообщений/день на модель
• Лимит сбрасывается в 22:00 МСК

💡 Альтернатива: используй бесплатный чат на chat.deepseek.com"""

@app.route('/')
def index():
    conn = get_db_connection()
    feedbacks = conn.execute('SELECT * FROM feedback ORDER BY created_at DESC LIMIT 10').fetchall()
    conn.close()
    return render_template('index.html', user=current_user, feedbacks=feedbacks, models=FALLBACK_MODELS)

@app.route('/chat')
def chat():
    history = []
    if current_user.is_authenticated:
        conn = get_db_connection()
        history = conn.execute('''
            SELECT * FROM chat_history WHERE user_id = ? ORDER BY created_at ASC LIMIT 50
        ''', (current_user.id,)).fetchall()
        conn.close()

    return render_template('chat.html', user=current_user, history=history, models=FALLBACK_MODELS, main_model=MAIN_MODEL)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'error': 'Пустое сообщение'}), 400

    # Сохраняем сообщение пользователя
    if current_user.is_authenticated:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO chat_history (user_id, model, role, content)
            VALUES (?, ?, ?, ?)
        ''', (current_user.id, MAIN_MODEL["name"], 'user', user_message))
        conn.commit()

        history = conn.execute('''
            SELECT role, content FROM chat_history
            WHERE user_id = ? ORDER BY created_at DESC LIMIT 10
        ''', (current_user.id,)).fetchall()
        conn.close()

        messages = []
        for msg in reversed(history):
            messages.append({"role": msg['role'], "content": msg['content']})
    else:
        messages = [{"role": "user", "content": user_message}]

    # Получаем ответ от AI (с автоматическим fallback)
    ai_response = get_ai_response(messages)

    # Сохраняем ответ
    if current_user.is_authenticated:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO chat_history (user_id, model, role, content)
            VALUES (?, ?, ?, ?)
        ''', (current_user.id, MAIN_MODEL["name"], 'assistant', ai_response))
        conn.commit()
        conn.close()

    return jsonify({'response': ai_response, 'model': MAIN_MODEL["name"]})

@app.route('/login')
def login():
    return google.authorize_redirect(url_for('authorize', _external=True))

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (user_info['email'],)).fetchone()

    if not user:
        conn.execute('INSERT INTO users (email, name, avatar) VALUES (?, ?, ?)',
                    (user_info['email'], user_info['name'], user_info.get('picture')))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (user_info['email'],)).fetchone()

    conn.close()

    login_user(User(user['id'], user['email'], user['name'], user.get('avatar')))
    flash('Добро пожаловать!', 'success')
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    feedbacks = conn.execute('SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC',
                            (current_user.id,)).fetchall()
    conn.close()
    return render_template('dashboard.html', user=current_user, feedbacks=feedbacks)

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        rating = request.form.get('rating', 5)

        if not name or not email or not message:
            flash('Заполните все поля', 'error')
            return redirect(url_for('feedback'))

        conn = get_db_connection()
        if current_user.is_authenticated:
            conn.execute('INSERT INTO feedback (user_id, name, email, message, rating) VALUES (?, ?, ?, ?, ?)',
                        (current_user.id, name, email, message, rating))
        else:
            conn.execute('INSERT INTO feedback (name, email, message, rating) VALUES (?, ?, ?, ?)',
                        (name, email, message, rating))
        conn.commit()
        conn.close()

        flash('Спасибо за отзыв!', 'success')
        return redirect(url_for('index'))

    return render_template('feedback.html', user=current_user)

@app.route('/api/feedback')
def api_feedback():
    conn = get_db_connection()
    feedbacks = conn.execute('SELECT * FROM feedback ORDER BY created_at DESC LIMIT 20').fetchall()
    conn.close()
    return jsonify([dict(f) for f in feedbacks])

if __name__ == '__main__':
    init_db()
    print("\n" + "="*60)
    print("🚀 СЕРВЕР ЗАПУЩЕН: http://localhost:5000")
    print("\n🤖 АКТИВНЫЕ МОДЕЛИ (автоматический fallback):")
    for i, model in enumerate(FALLBACK_MODELS, 1):
        print(f"   {i}. {model['name']} - {model['description'][:40]}...")
    print("\n💡 Как это работает:")
    print("   • Если MiniMax M2.5 недоступна → автоматически переключается на Step 3.5 Flash")
    print("   • Если Step недоступен → Trinity Large, и так далее")
    print("   • 50 сообщений/день на каждую модель!")
    print("\n📝 Получи ключ: https://openrouter.ai/keys")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)