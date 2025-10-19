from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from functools import wraps
from datetime import datetime
import json
import os
import requests as external_requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key-here')

# ========== CONFIG ==========
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI')
OWNER_ID = os.environ.get('OWNER_ID')
TURNSTILE_SECRET = os.environ.get('TURNSTILE_SECRET')

# Data storage
DATA_DIR = 'data'
USERS_FILE = f'{DATA_DIR}/users.json'
BANNED_FILE = f'{DATA_DIR}/banned.json'

os.makedirs(DATA_DIR, exist_ok=True)

# ========== HELPER FUNCTIONS ==========
def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_banned():
    try:
        with open(BANNED_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_banned(banned):
    with open(BANNED_FILE, 'w') as f:
        json.dump(banned, f, indent=2)

# ========== DECORATORS ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['user'].get('id') != OWNER_ID:
            return jsonify({'error': 'Access denied'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ========== CLIENT API ROUTES ==========
@app.route('/turnstile/verify', methods=['POST'])
def verify_turnstile():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"success": False}), 400
    
    verify_response = external_requests.post(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        json={
            'secret': TURNSTILE_SECRET,
            'response': token
        }
    )
    
    result = verify_response.json()
    return jsonify({"success": result.get('success', False)})

@app.route('/auth/login', methods=['POST'])
def auth_login():
    data = request.json
    user_id = data.get('id')
    
    if not user_id:
        return jsonify({"error": "Invalid data"}), 400
    
    users = load_users()
    
    if user_id not in users:
        users[user_id] = {
            "username": data.get('username'),
            "email": data.get('email'),
            "verified": data.get('verified', False),
            "hwid": data.get('hwid'),
            "first_login": datetime.now().isoformat(),
            "total_logins": 1
        }
    else:
        users[user_id]['total_logins'] = users[user_id].get('total_logins', 0) + 1
        users[user_id]['last_login'] = datetime.now().isoformat()
    
    save_users(users)
    return jsonify({"success": True})

@app.route('/auth/check_ban/<user_id>')
def check_ban(user_id):
    banned = load_banned()
    if user_id in banned:
        return jsonify({"banned": True, "reason": banned[user_id].get('reason')})
    return jsonify({"banned": False})

@app.route('/admin/users')
def admin_users():
    users = load_users()
    return jsonify({"total": len(users), "users": users})

@app.route('/admin/ban', methods=['POST'])
def admin_ban():
    data = request.json
    user_id = data.get('user_id')
    reason = data.get('reason', 'Banned by admin')
    
    banned = load_banned()
    banned[user_id] = {
        'reason': reason,
        'banned_at': datetime.now().isoformat()
    }
    save_banned(banned)
    
    return jsonify({"success": True})

# ========== WEB ROUTES ==========
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/auth/discord')
def auth_discord():
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20email"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Login failed", 400
    
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    
    try:
        token_response = external_requests.post('https://discord.com/api/oauth2/token', data=data)
        token_data = token_response.json()
        
        user_response = external_requests.get('https://discord.com/api/users/@me', 
                               headers={'Authorization': f"Bearer {token_data['access_token']}"})
        user_data = user_response.json()
        
        # Check if banned
        banned = load_banned()
        if user_data.get('id') in banned:
            return f"You are banned. Reason: {banned[user_data['id']].get('reason')}", 403
        
        # Save to users database
        users = load_users()
        user_id = user_data.get('id')
        
        if user_id not in users:
            users[user_id] = {
                "username": user_data.get('username'),
                "email": user_data.get('email'),
                "verified": user_data.get('verified', False),
                "first_login": datetime.now().isoformat(),
                "total_logins": 1
            }
        else:
            users[user_id]['total_logins'] = users[user_id].get('total_logins', 0) + 1
            users[user_id]['last_login'] = datetime.now().isoformat()
        
        save_users(users)
        
        session['user'] = user_data
        
        if user_data.get('id') == OWNER_ID:
            return redirect(url_for('panel'))
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/panel')
@login_required
@owner_required
def panel():
    return render_template('panel.html', user=session['user'])

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=session['user'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ========== PANEL API ROUTES ==========
@app.route('/api/verify-captcha', methods=['POST'])
def verify_captcha():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"success": False}), 400
    
    verify_response = external_requests.post(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        json={
            'secret': TURNSTILE_SECRET,
            'response': token
        }
    )
    
    result = verify_response.json()
    return jsonify({"success": result.get('success', False)})

@app.route('/api/panel/users')
@owner_required
def get_panel_users():
    users = load_users()
    return jsonify({'total': len(users), 'users': users})

@app.route('/api/panel/ban', methods=['POST'])
@owner_required
def ban_user_panel():
    data = request.json
    user_id = data.get('user_id')
    reason = data.get('reason', 'Banned by admin')
    
    banned = load_banned()
    banned[user_id] = {
        'reason': reason,
        'banned_at': datetime.now().isoformat(),
        'banned_by': session['user']['username']
    }
    save_banned(banned)
    return jsonify({'success': True})

@app.route('/api/panel/unban', methods=['POST'])
@owner_required
def unban_user_panel():
    data = request.json
    user_id = data.get('user_id')
    
    banned = load_banned()
    if user_id in banned:
        del banned[user_id]
        save_banned(banned)
    
    return jsonify({'success': True})

@app.route('/api/panel/stats')
@owner_required
def get_panel_stats():
    users = load_users()
    banned = load_banned()
    
    return jsonify({
        'total_users': len(users),
        'banned_users': len(banned),
        'active_users': len(users) - len(banned),
        'total_logins': sum(u.get('total_logins', 0) for u in users.values())
    })

# ========== RUN ==========
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
