from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
import json
import os
import requests
from typing import List, Dict

app = FastAPI(title="Cheat Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")

# Database
users_db: Dict[str, dict] = {}
banned_db: List[str] = []

class UserLogin(BaseModel):
    id: str
    username: str
    email: str
    verified: bool
    hwid: str

class TurnstileVerify(BaseModel):
    token: str

class BanRequest(BaseModel):
    user_id: str
    reason: str = "Banned by admin"

def send_webhook(title, message, color=5814783):
    try:
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass

# HTML Dashboard
@app.get("/", response_class=HTMLResponse)
def home():
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cheat Scanner API</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 900px;
            width: 100%;
            animation: fadeIn 0.5s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .header { text-align: center; margin-bottom: 40px; }
        .logo { font-size: 60px; margin-bottom: 10px; }
        h1 { color: #333; font-size: 32px; margin-bottom: 10px; }
        .subtitle { color: #666; font-size: 16px; }
        .status-badge {
            display: inline-block;
            background: #10b981;
            color: white;
            padding: 8px 20px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
            margin: 20px 0;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 15px;
            padding: 30px;
            color: white;
            text-align: center;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            cursor: pointer;
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(102, 126, 234, 0.6);
        }
        .stat-icon { font-size: 45px; margin-bottom: 15px; }
        .stat-value { font-size: 42px; font-weight: bold; margin: 10px 0; }
        .stat-label { 
            font-size: 14px; 
            opacity: 0.9; 
            text-transform: uppercase;
            letter-spacing: 1.5px;
        }
        .endpoints {
            margin-top: 30px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }
        .endpoints h3 {
            color: #333;
            margin-bottom: 20px;
            font-size: 20px;
        }
        .endpoint {
            background: white;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
            transition: all 0.2s ease;
        }
        .endpoint:hover {
            transform: translateX(5px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        .endpoint-method {
            background: #667eea;
            color: white;
            padding: 5px 12px;
            border-radius: 5px;
            font-size: 12px;
            font-weight: bold;
            margin-right: 15px;
            min-width: 50px;
            text-align: center;
        }
        .endpoint-method.post { background: #f59e0b; }
        .endpoint-path {
            color: #333;
            font-family: 'Courier New', monospace;
            flex: 1;
            font-size: 14px;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 14px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🛡️</div>
            <h1>Cheat Scanner API</h1>
            <p class="subtitle">Real-time Minecraft Cheat Detection System</p>
            <div class="status-badge">✅ Online & Running</div>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-icon">👥</div>
                <div class="stat-value" id="users">
                    <div class="loading"></div>
                </div>
                <div class="stat-label">Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">🚫</div>
                <div class="stat-value" id="banned">
                    <div class="loading"></div>
                </div>
                <div class="stat-label">Banned Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">⚡</div>
                <div class="stat-value">2.0</div>
                <div class="stat-label">API Version</div>
            </div>
        </div>

        <div class="endpoints">
            <h3>📡 Available Endpoints</h3>
            <div class="endpoint">
                <span class="endpoint-method">GET</span>
                <span class="endpoint-path">/</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method">GET</span>
                <span class="endpoint-path">/health</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method post">POST</span>
                <span class="endpoint-path">/turnstile/verify</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method post">POST</span>
                <span class="endpoint-path">/auth/login</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method">GET</span>
                <span class="endpoint-path">/auth/check_ban/{user_id}</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method post">POST</span>
                <span class="endpoint-path">/admin/ban</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method post">POST</span>
                <span class="endpoint-path">/admin/unban/{user_id}</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method">GET</span>
                <span class="endpoint-path">/admin/users</span>
            </div>
            <div class="endpoint">
                <span class="endpoint-method">GET</span>
                <span class="endpoint-path">/admin/banned</span>
            </div>
        </div>

        <div class="footer">
            <p>🚀 Powered by <strong>FastAPI</strong> • Deployed on <strong>Render.com</strong></p>
            <p style="margin-top: 10px; font-size: 12px; opacity: 0.7;">
                © 2025 Cheat Scanner API • All rights reserved
            </p>
        </div>
    </div>

    <script>
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                document.getElementById('users').textContent = data.users || 0;
                document.getElementById('banned').textContent = data.banned || 0;
            } catch (error) {
                document.getElementById('users').textContent = '0';
                document.getElementById('banned').textContent = '0';
            }
        }
        loadStats();
        setInterval(loadStats, 30000);
    </script>
</body>
</html>
    """
    return html

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/stats")
def api_stats():
    return {
        "users": len(users_db),
        "banned": len(banned_db),
        "version": "2.0"
    }

@app.post("/turnstile/verify")
def verify_turnstile(data: TurnstileVerify):
    try:
        response = requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            json={'secret': TURNSTILE_SECRET, 'response': data.token},
            timeout=5
        )
        return {"success": response.json().get("success", False)}
    except:
        return {"success": False}

@app.post("/auth/login")
def user_login(user: UserLogin):
    user_id = user.id
    
    if user_id in banned_db:
        raise HTTPException(status_code=403, detail="User is banned")
    
    if user_id not in users_db:
        users_db[user_id] = {
            "username": user.username,
            "email": user.email,
            "hwid": user.hwid,
            "first_login": datetime.now().isoformat(),
            "last_login": datetime.now().isoformat(),
            "total_logins": 1
        }
        send_webhook("🆕 New User", f"**{user.username}**\nID: {user_id}", 3447003)
    else:
        if users_db[user_id]["hwid"] != user.hwid:
            raise HTTPException(status_code=403, detail="HWID mismatch")
        users_db[user_id]["last_login"] = datetime.now().isoformat()
        users_db[user_id]["total_logins"] += 1
    
    return {"success": True}

@app.get("/auth/check_ban/{user_id}")
def check_ban(user_id: str):
    return {"banned": user_id in banned_db}

@app.post("/admin/ban")
def ban_user(ban: BanRequest):
    if ban.user_id not in banned_db:
        banned_db.append(ban.user_id)
        send_webhook("🚫 User Banned", f"ID: {ban.user_id}", 15158332)
    return {"success": True}

@app.post("/admin/unban/{user_id}")
def unban_user(user_id: str):
    if user_id in banned_db:
        banned_db.remove(user_id)
        send_webhook("✅ Unbanned", f"ID: {user_id}", 3066993)
    return {"success": True}

@app.get("/admin/users")
def get_users():
    return {"total": len(users_db), "users": users_db}

@app.get("/admin/banned")
def get_banned():
    return {"total": len(banned_db), "banned": banned_db}
