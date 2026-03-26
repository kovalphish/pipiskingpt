import os
from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

# OpenRouter API
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Модели с fallback
FALLBACK_MODELS = [
    {"id": "minimax/minimax-m2.5:free", "name": "MiniMax M2.5"},
    {"id": "stepfun/step-3.5-flash:free", "name": "Step 3.5 Flash"},
    {"id": "arcee-ai/trinity-large-preview:free", "name": "Trinity Large"},
    {"id": "nvidia/nemotron-3-super:free", "name": "NVIDIA Nemotron 3"}
]

def get_ai_response(message):
    """Получить ответ от AI"""
    if not OPENROUTER_API_KEY:
        return "⚠️ API ключ OpenRouter не настроен. Получи на openrouter.ai/keys"
    
    for model in FALLBACK_MODELS:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://your-domain.vercel.app",
                "X-Title": "DeepSeek Chat"
            }
            
            data = {
                "model": model["id"],
                "messages": [{"role": "user", "content": message}],
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            elif response.status_code in [429, 402, 404]:
                continue
                
        except Exception:
            continue
    
    return "❌ Все модели временно недоступны. Попробуйте позже."

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'Пустое сообщение'}), 400
    
    response = get_ai_response(message)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
