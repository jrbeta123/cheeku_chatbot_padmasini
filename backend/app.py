
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

FRONTEND_URL = os.getenv("FRONTEND_URL")

CORS(
    app,
    resources={
        r"/*": {
            "origins": [FRONTEND_URL]
        }
    },
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
JWT_EXPIRY_HOURS = 24

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing")

mongo_client = MongoClient(MONGODB_URI)

db = mongo_client["chatbot_db"]

users = db["users"]
chat_collection = db["chat_history"]
reset_tokens = db["password_reset_tokens"]

# --------------------------------------------------
# JWT TOKEN
# --------------------------------------------------

def create_token(login_id):
    payload = {
        "login_id": login_id,
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=JWT_EXPIRY_HOURS)
    }

    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def token_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"message": "Missing token"}), 401

        token = auth_header.split(" ", 1)[1]

        try:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=["HS256"]
            )

        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401

        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401

        return f(payload["login_id"], *args, **kwargs)

    return decorated


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/api/register", methods=["POST"])
@app.route("/register", methods=["POST"])
def register():

    data = request.get_json(silent=True) or {}

    login_id = data.get("login_id", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not login_id or not email or not password:
        return jsonify({
            "message": "All fields are required"
        }), 400

    if len(password) < 8:
        return jsonify({
            "message": "Password must contain at least 8 characters"
        }), 400

    if users.find_one({"login_id": login_id}):
        return jsonify({
            "message": "Login ID already exists"
        }), 400

    if users.find_one({"email": email}):
        return jsonify({
            "message": "Email already registered"
        }), 400

    users.insert_one({
        "login_id": login_id,
        "email": email,
        "password": generate_password_hash(password)
    })

    return jsonify({
        "message": "Registration successful"
    }), 201


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/api/login", methods=["POST"])
@app.route("/login", methods=["POST"])
def login():

    data = request.get_json(silent=True) or {}

    login_id = data.get("login_id", "").strip()
    password = data.get("password", "")

    user = users.find_one({
        "login_id": login_id
    })

    if user and check_password_hash(user["password"], password):

        return jsonify({
            "message": "Login successful",
            "token": create_token(login_id),
            "login_id": login_id
        })

    return jsonify({
        "message": "Invalid ID or Password"
    }), 401


# --------------------------------------------------
# FORGOT PASSWORD
# --------------------------------------------------

@app.route("/api/forgot-password", methods=["POST"])
@app.route("/forgot-password", methods=["POST"])
def forgot_password():

    data = request.get_json(silent=True) or {}

    login_id = data.get("login_id", "").strip()

    user = users.find_one({
        "login_id": login_id
    })

    if not user:
        return jsonify({
            "message": "If the account exists, reset instructions will be sent."
        })

    # Generate a random, temporary reset token
    token = secrets.token_urlsafe(32)

    reset_tokens.insert_one({
        "login_id": login_id,
        "token": token,
        "expires_at": datetime.now(timezone.utc)
        + timedelta(minutes=15)
    })

    frontend_url = FRONTEND_URL

    reset_link = f"{frontend_url}/?token={token}"

    # Temporary development approach:
    # Check Render logs to retrieve the reset link.
    print("PASSWORD RESET LINK:", reset_link)

    return jsonify({
        "message": "Reset link generated. Check backend logs for the link."
    })


# --------------------------------------------------
# RESET PASSWORD
# --------------------------------------------------

@app.route("/api/reset-password", methods=["POST"])
@app.route("/reset-password", methods=["POST"])
def reset_password():

    data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    new_password = data.get("new_password", "")

    if not token or not new_password:
        return jsonify({
            "message": "Token and new password are required"
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "message": "Password must contain at least 8 characters"
        }), 400

    reset_record = reset_tokens.find_one({
        "token": token
    })

    if not reset_record:
        return jsonify({
            "message": "Invalid reset token"
        }), 400

    expires_at = reset_record["expires_at"]

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        reset_tokens.delete_one({"_id": reset_record["_id"]})

        return jsonify({
            "message": "Reset link expired"
        }), 400

    users.update_one(
        {"login_id": reset_record["login_id"]},
        {
            "$set": {
                "password": generate_password_hash(new_password)
            }
        }
    )

    # Token can only be used once
    reset_tokens.delete_one({
        "_id": reset_record["_id"]
    })

    return jsonify({
        "message": "Password updated successfully"
    })


# --------------------------------------------------
# CHATBOT FUNCTION
# --------------------------------------------------

def chat_with_gpt(prompt):

    # Connect your existing OpenAI implementation here.
    # This placeholder prevents a missing client from crashing the app.

    raise RuntimeError("OpenAI chatbot integration is not configured")


# --------------------------------------------------
# CHAT API
# --------------------------------------------------

@app.route("/api/chat", methods=["POST"])
@app.route("/chat", methods=["POST"])
@token_required
def chat(login_id):

    data = request.get_json(silent=True) or {}

    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({
            "message": "Message is required"
        }), 400

    try:
        ai_response = chat_with_gpt(user_message)

    except Exception as e:
        return jsonify({
            "message": f"AI error: {str(e)}"
        }), 500

    chat_collection.insert_one({
        "login_id": login_id,
        "user_message": user_message,
        "ai_response": ai_response,
        "timestamp": datetime.now(timezone.utc)
    })

    return jsonify({
        "reply": ai_response
    })


# --------------------------------------------------
# CHAT HISTORY
# --------------------------------------------------

@app.route("/api/history", methods=["GET"])
@app.route("/history", methods=["GET"])
@token_required
def get_history(login_id):

    chats = list(
        chat_collection.find(
            {"login_id": login_id},
            {"_id": 0, "login_id": 0}
        ).sort("timestamp", -1)
    )

    for chat_item in chats:
        if isinstance(chat_item.get("timestamp"), datetime):
            chat_item["timestamp"] = chat_item["timestamp"].isoformat()

    return jsonify(chats)


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "ok",
        "message": "Flask backend is running"
    })


# --------------------------------------------------
# RUN SERVER
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )
