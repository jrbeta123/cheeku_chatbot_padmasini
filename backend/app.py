import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
#from openai import OpenAI
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash

# Load .env first so os.getenv works everywhere below
load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# CORS: allow only your frontend link(s)
# ---------------------------------------------------------------------------
FRONTEND_URLS = os.getenv("FRONTEND_URLS", "").split(",")

CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                url.strip()
                for url in FRONTEND_URLS
                if url.strip()
            ]
        }
    },
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
JWT_EXPIRY_HOURS = 24

# OpenAI client
#client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MongoDB connection
mongo_client = MongoClient(os.getenv("MONGODB_URI"))
db = mongo_client["chatbot_db"]
chat_collection = db["chat_history"]
users = db["users"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def create_token(login_id):
    payload = {
        "login_id": login_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def token_required(f):
    """Protect a route: requires 'Authorization: Bearer <token>'."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"message": "Missing token"}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401

        return f(payload["login_id"], *args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    login_id = data.get("login_id", "").strip()
    password = data.get("password", "")

    if not login_id or not password:
        return jsonify({"message": "login_id and password are required"}), 400

    if users.find_one({"login_id": login_id}):
        return jsonify({"message": "User already exists"}), 400

    users.insert_one({
        "login_id": login_id,
        "password": generate_password_hash(password),
    })

    return jsonify({"message": "Registration successful"})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    login_id = data.get("login_id", "").strip()
    password = data.get("password", "")

    user = users.find_one({"login_id": login_id})

    if user and check_password_hash(user["password"], password):
        return jsonify({
            "message": "Login successful",
            "token": create_token(login_id),
            "login_id": login_id,
        })

    return jsonify({"message": "Invalid ID or Password"}), 401


# NOTE: This endpoint lets anyone who knows a login_id change that user's
# password. Before going to production, replace it with an email OTP or
# reset-token flow.
@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    login_id = data.get("login_id", "").strip()
    new_password = data.get("new_password", "")

    if not login_id or not new_password:
        return jsonify({"message": "login_id and new_password are required"}), 400

    result = users.update_one(
        {"login_id": login_id},
        {"$set": {"password": generate_password_hash(new_password)}},
    )

    if result.matched_count == 0:
        return jsonify({"message": "User not found"}), 404

    return jsonify({"message": "Password updated successfully"})


# ---------------------------------------------------------------------------
# Chat routes (protected)
# ---------------------------------------------------------------------------
@app.route("/chat", methods=["POST"])
@token_required
def chat(login_id):
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"message": "Message is required"}), 400

    try:
        ai_response = chat_with_gpt(user_message)
    except Exception as e:
        return jsonify({"message": f"AI error: {str(e)}"}), 500

    chat_collection.insert_one({
        "login_id": login_id,
        "user_message": user_message,
        "ai_response": ai_response,
        "timestamp": datetime.utcnow(),
    })

    return jsonify({"reply": ai_response})


@app.route("/history", methods=["GET"])
@token_required
def get_history(login_id):
    chats = list(
        chat_collection.find({"login_id": login_id}, {"_id": 0, "login_id": 0})
        .sort("timestamp", -1)
    )
    return jsonify(chats)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        port=int(os.getenv("PORT", 5000)),
    )