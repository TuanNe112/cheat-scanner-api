from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from functools import wraps
from datetime import datetime, timedelta
import json
import os
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Config
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

# Helper functions
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

# Decorators
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

# ========== CAPTCHA VERIFY ROUTE - FIX ==========
@app.route('/api/verify-captcha', methods=['POST'])
def verify_captcha():
    """Verify Cloudflare Turnstile CAPTCHA - FIXED VERSION"""
    try:
        data = request.get_json()
        if not data:
            print("❌ No JSON data received")
            return jsonify({"success": False, "error": "No data"}), 400
        
        token = data.get('token')
        if not token:
            print("❌ No token in request")
            return jsonify({"success": False, "error": "No token"}), 400
        
        print(f"✅ Received token: {token[:20]}...")
        print(f"🔑 Using secret: {TURNSTILE_SECRET[:10] if TURNSTILE_SECRET else 'NOT SET'}...")
        
        # Verify with Cloudflare
        verify_response = requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            json={
                'secret': TURNSTILE_SECRET,
                'response': token
            },
            timeout=10
        )
        
        result = verify_response.json()
        print(f"📡 Cloudflare response: {result}")
        
        if result.get('success'):
            print("✅ Verification SUCCESS")
            return jsonify({"success": True})
        else:
            print(f"❌ Verification FAILED: {result.get('error-codes', [])}")
            return jsonify({
                "success": False, 
                "error": "Verification failed",
                "error_codes": result.get('error-codes', [])
            }), 400
            
    except Exception as e:
        print(f"❌ Exception in verify_captcha: {str(e)}")
        return jsonify({
            "success": False, 
            "error": str(e)
        }), 500

# ========== WEB ROUTES ==========
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/auth/discord')
def auth_discord():
    remember = request.args.get('remember', 'false')
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20email&state={remember}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    remember = request.args.get('state', 'false')
    
    if not code:
        return "Login failed: No code", 400
    
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    
    try:
        token_response = requests.post('https://discord.com/api/oauth2/token', data=data)
        token_data = token_response.json()
        
        if 'error' in token_data:
            return f"Discord OAuth error: {token_data.get('error_description', 'Unknown error')}", 400
        
        user_response = requests.get('https://discord.com/api/users/@me', 
                               headers={'Authorization': f"Bearer {token_data['access_token']}"})
        user_data = user_response.json()
        
        # Check ban
        banned = load_banned()
        if user_data.get('id') in banned:
            return f"You are banned. Reason: {banned[user_data['id']].get('reason')}", 403
        
        # Save user
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
        
        # Set session
        if remember == 'true':
            session.permanent = True
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
    return render_template('panel.html', user=session['user'], owner_id=OWNER_ID)

@app.route('/dashboard')
@login_required
def dashboard():
    users = load_users()
    user_id = session['user'].get('id')
    user_stats = users.get(user_id, {})
    return render_template('dashboard.html', user=session['user'], stats=user_stats, owner_id=OWNER_ID)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ========== CLIENT API ROUTES ==========
@app.route('/turnstile/verify', methods=['POST'])
def verify_turnstile_client():
    """Verify from Minecraft client"""
    return verify_captcha()

@app.route('/auth/login', methods=['POST'])
def auth_login():
    data = request.json
    user_id = data.get('id')
    
    if not user_id:
        return jsonify({"error": "Invalid data"}), 400
    
    banned = load_banned()
    if user_id in banned:
        return jsonify({"error": "banned", "reason": banned[user_id].get('reason')}), 403
    
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
        if data.get('hwid'):
            users[user_id]['hwid'] = data.get('hwid')
    
    save_users(users)
    return jsonify({"success": True, "user": users[user_id]})

@app.route('/auth/check_ban/<user_id>')
def check_ban(user_id):
    banned = load_banned()
    if user_id in banned:
        return jsonify({"banned": True, "reason": banned[user_id].get('reason')})
    return jsonify({"banned": False})

@app.route('/api/stats')
def api_stats():
    users = load_users()
    banned = load_banned()
    return jsonify({
        "total_users": len(users),
        "banned_users": len(banned),
        "active_users": len(users) - len(banned)
    })

# ========== PANEL API ROUTES ==========
@app.route('/api/panel/users')
@owner_required
def get_panel_users():
    users = load_users()
    return jsonify({'total': len(users), 'users': users})

@app.route('/api/panel/banned')
@owner_required
def get_banned_users():
    banned = load_banned()
    return jsonify({'banned': banned})

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

# ========== HEALTH CHECK ==========
@app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
