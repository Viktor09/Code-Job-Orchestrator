from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import os
import bcrypt
import jwt
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7

def get_connection():
    host = os.getenv("DB_HOST", "postgres")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", 5432)

    if not database:
        raise ValueError("DB_NAME is not set")
    if not user:
        raise ValueError("DB_USER is not set")
    if not password:
        raise ValueError("DB_PASSWORD is not set")

    try:
        return psycopg2.connect(host=host, database=database, user=user, password=password, port=port)
    except psycopg2.OperationalError as e:
        print("Database connection failed:", e)
        raise

def create_tables():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            user_name VARCHAR(255) NOT NULL,
            user_email VARCHAR(255) NOT NULL UNIQUE,
            user_password_hashed TEXT NOT NULL,
            user_role VARCHAR(50) NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            refresh_token_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            refresh_token_hashed TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_refresh_tokens_user
                FOREIGN KEY (user_id)
                REFERENCES users(user_id)
                ON DELETE CASCADE
        )
        """)

        conn.commit()
        cur.close()
        print("Table users created successfully or already exists.")

    except Exception as e:
        print("Database error:", e)

    finally:
        if conn:
            conn.close()

def generate_access_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ACCESS_TOKEN_MINUTES) 

    subject = str(user["user_id"])
    user_name = user["user_name"]
    email = user["user_email"]
    role = user["user_role"]
    issuer = "auth-service"

    payload = {"sub": subject, "user_name": user_name, "email": email,
            "role": role, "iat": now, "exp": exp, "iss": issuer}

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def is_valid_password(password: str) -> bool:
    if len(password) < 8:
        return False

    has_upper = False
    has_lower = False
    has_digit = False
    has_special = False

    for c in password:
        if c.isupper():
            has_upper = True
        elif c.islower():
            has_lower = True
        elif c.isdigit():
            has_digit = True
        else:
            has_special = True

    if has_upper and has_lower and has_digit and has_special:
        return True

    return False

def get_user_by_email(user_email: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT user_id, user_name, user_email, user_password_hashed, user_role, is_active, created_at
            FROM users
            WHERE user_email = %s
            """,
            (user_email,))
        user = cur.fetchone()
        cur.close()
        return user
    finally:
        conn.close()

def get_user_by_username(user_name: str):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT user_id, user_name, user_email, user_role, is_active, created_at
            FROM users
            WHERE user_name = %s    
            """,
            (user_name,))
        user = cur.fetchone()
        cur.close()
        return user
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT user_id, user_name, user_email, user_role, is_active, created_at
            FROM users
            WHERE user_id = %s
            """,
            (user_id,))
        user = cur.fetchone()
        cur.close()
        return user
    finally:
        conn.close()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Authorization header is missing"}), 401

        parts = auth_header.split()

        if len(parts) != 2 or parts[0] != "Bearer":
            return jsonify({"error": "Invalid Authorization header format"}), 401

        token = parts[1]

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload["sub"])
            user_name = payload["user_name"]
            user_email = payload["email"]
            user_role = payload["role"]
            request.current_user = {"user_id": user_id, "user_name": user_name,
                "user_email": user_email, "user_role": user_role}
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Access token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid access token"}), 401

        return f(*args, **kwargs)

    return decorated


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    
    user_name = data["user_name"]
    user_email = data["user_email"]
    password = data["password"]

    if not user_name or not user_email or not password:
        return jsonify({"error": "user_name, user_email and password are required"}), 400
    
    if not is_valid_password(password):
        return jsonify({"error": "Password must be at least 8 characters long and contain uppercase, lowercase, number and special character"}), 400
    
    if get_user_by_email(user_email):
        return jsonify({"error": "Email already registered"}), 409

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            INSERT INTO users (user_name, user_email, user_password_hashed)
            VALUES (%s, %s, %s)
            RETURNING user_id, user_name, user_email, user_role, is_active, created_at
            """, 
        (user_name, user_email, password_hash))

        new_user = cur.fetchone()
        conn.commit()
        cur.close()

        return jsonify({"message": "User registered successfully", "user": new_user}), 201

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "Username or email already exists"}), 409
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)

    user_email = data["user_email"]
    password = data["password"]

    if not user_email or not password:
        return jsonify({"error": "user_email and password are required"}), 400
    
    user = get_user_by_email(user_email)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    if not user["is_active"]:
        return jsonify({"error": "User account is inactive"}), 403
    
    password_ok = bcrypt.checkpw(password.encode("utf-8"), user["user_password_hashed"].encode("utf-8"))
    if not password_ok:
        return jsonify({"error": "Invalid credentials"}), 401
    
    access_token = generate_access_token(user)
    refresh_token = secrets.token_urlsafe(64)
    refresh_token_hashed = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO refresh_tokens (user_id, refresh_token_hashed, expires_at)
            VALUES (%s, %s, %s)
            """, 
        (user["user_id"], refresh_token_hashed, expires_at))

        conn.commit()
        cur.close()

        payload = {"message": "Login successful", "access_token": access_token,
            "refresh_token": refresh_token, "user": {"user_id": user["user_id"],
            "user_name": user["user_name"], "user_email": user["user_email"],
            "user_role": user["user_role"]}}

        return jsonify(payload), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True)
    refresh_token = data["refresh_token"]

    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 400
    
    refresh_token_hashed = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT rt.refresh_token_id, rt.user_id, rt.expires_at, rt.revoked_at,
                   u.user_name, u.user_email, u.user_role, u.is_active
            FROM refresh_tokens rt
            JOIN users u ON u.user_id = rt.user_id
            WHERE rt.refresh_token_hashed = %s
            """, 
        (refresh_token_hashed,))

        token_row = cur.fetchone()

        if not token_row:
            cur.close()
            return jsonify({"error": "Invalid refresh token"}), 401

        if token_row["revoked_at"] is not None:
            cur.close()
            return jsonify({"error": "Refresh token already revoked"}), 401

        expires_at = token_row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < datetime.now(timezone.utc):
            cur.close()
            return jsonify({"error": "Refresh token expired"}), 401

        if not token_row["is_active"]:
            cur.close()
            return jsonify({"error": "User account is inactive"}), 403

        cur.execute(
            """
            UPDATE refresh_tokens
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE refresh_token_id = %s
            """, 
            (token_row["refresh_token_id"], ))

        new_refresh_token = secrets.token_urlsafe(64)
        new_refresh_token_hashed = hashlib.sha256(new_refresh_token.encode("utf-8")).hexdigest()
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)

        cur.execute(
            """
            INSERT INTO refresh_tokens (user_id, refresh_token_hashed, expires_at)
            VALUES (%s, %s, %s)
            """,
            (token_row["user_id"], new_refresh_token_hashed, new_expires_at))

        access_token = generate_access_token({"user_id": token_row["user_id"], "user_name": token_row["user_name"], 
                    "user_email": token_row["user_email"], "user_role": token_row["user_role"]})

        conn.commit()
        cur.close()

        payload = {"message": "Token refreshed successfully", "access_token": access_token, "refresh_token": new_refresh_token}

        return jsonify(payload), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/logout", methods=["POST"])
def logout():
    data = request.get_json(silent=True)
    refresh_token = data["refresh_token"]

    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 400
    
    refresh_token_hashed = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE refresh_tokens
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE refresh_token_hashed = %s AND revoked_at IS NULL
            """, 
            (refresh_token_hashed,))

        conn.commit()
        affected_rows = cur.rowcount
        cur.close()

        if affected_rows == 0:
            return jsonify({"error": "Refresh token not found or already revoked"}), 404

        return jsonify({"message": "Logout successful"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/me", methods=["GET"])
@token_required
def me():
    user_id = request.current_user["user_id"]
    user = get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify(user), 200

if __name__ == "__main__":
    create_tables()
    app.run(host="0.0.0.0", port=5000)