# api_server.py - Optimized for Render.com
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import json
import os
import requests
from typing import List, Dict
import asyncio

app = FastAPI(title="Cheat Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables (set in Render dashboard)
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")

# In-memory database
users_db: Dict[str, dict] = {}
banned_db: List[str] = []
active_connections: List[WebSocket] = []

class UserLogin(BaseModel):
    id: str
    username: str
    email: str
    verified: bool
    avatar: str = None
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

@app.get("/")
def root():
    return {
        "status": "online",
        "version": "2.0",
        "deploy": "Render.com",
        "users": len(users_db),
        "banned": len(banned_db)
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

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
async def ban_user(ban: BanRequest):
    if ban.user_id not in banned_db:
        banned_db.append(ban.user_id)
        send_webhook("🚫 User Banned", f"ID: {ban.user_id}\nReason: {ban.reason}", 15158332)
    return {"success": True}

@app.post("/admin/unban/{user_id}")
async def unban_user(user_id: str):
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
