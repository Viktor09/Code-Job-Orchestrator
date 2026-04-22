from flask import Flask, request, jsonify
import os
import jwt
import requests
import redis
import json
from functools import wraps

app = Flask(__name__)

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"

PERSISTENCE_BASE_URL = os.getenv("PERSISTENCE_BASE_URL")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

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

def get_job_from_persistence(job_id):
    return requests.get(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}")

@app.route("/jobs", methods=["POST"])
@token_required
def create_job():
    data = request.get_json(silent=True)

    label = data["label"]
    executable_path = data["executable_path"]
    parameters_json = data["parameters_json"]

    if not parameters_json:
        parameters_json = {}
    
    if not label or not executable_path:
        return jsonify({"error": "label and executable_path are required"}), 400
    
    owner_user_id = request.current_user["user_id"]

    payload = {"owner_user_id": owner_user_id, "label": label, "executable_path": executable_path, "parameters_json": parameters_json}
    
    try:
        response = requests.post(f"{PERSISTENCE_BASE_URL}/persistence/jobs", json=payload)
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if response.status_code != 201:
        return jsonify(response.json()), response.status_code
    
    queue_payload = {"job_id": response.json()["job"]["job_id"]}

    try:
        redis_client.rpush(JOB_QUEUE_NAME, json.dumps(queue_payload))
    except Exception as e:
        return jsonify({"error": f"Redis unavailable: {str(e)}"}), 500

    return jsonify({"message": "Job created and queued successfully", "job": response.json()["job"]}), 201

@app.route("/jobs", methods=["GET"])
@token_required
def get_jobs():
    user_role = request.current_user["user_role"]
    user_id = request.current_user["user_id"]

    try:
        if user_role == "admin":
            response = requests.get(f"{PERSISTENCE_BASE_URL}/persistence/jobs")
        else:
            response = requests.get(f"{PERSISTENCE_BASE_URL}/persistence/jobs", params={"owner_user_id": user_id})
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    return jsonify(response.json()), response.status_code

@app.route("/jobs/<int:job_id>", methods=["GET"])
@token_required
def get_job_by_id(job_id):
    user_role = request.current_user["user_role"]
    user_id = request.current_user["user_id"]

    try:
        response = get_job_from_persistence(job_id)
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if response.status_code != 200:
        return jsonify(response.json()), response.status_code

    if response.json()["owner_user_id"] != user_id and user_role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    return jsonify(response.json()), 200

@app.route("/jobs/<int:job_id>/cancel", methods=["POST"])
@token_required
def cancel_job(job_id):
    user_role = request.current_user["user_role"]
    user_id = request.current_user["user_id"]

    try:
        response = get_job_from_persistence(job_id)
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if response.status_code != 200:
        return jsonify(response.json()), response.status_code

    if response.json()["owner_user_id"] != user_id and user_role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    if response.json()["status"] in ["completed", "failed", "cancelled"]:
        return jsonify({"error": "Job cannot be cancelled in current state"}), 400

    try:
        cancel_response = requests.patch(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/cancel")
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    return jsonify(cancel_response.json()), cancel_response.status_code

@app.route("/jobs/<int:job_id>/retry", methods=["POST"])
@token_required
def retry_job(job_id):
    user_role = request.current_user["user_role"]
    user_id = request.current_user["user_id"]

    try:
        response = get_job_from_persistence(job_id)
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if response.status_code != 200:
        return jsonify(response.json()), response.status_code

    job = response.json()

    if job["owner_user_id"] != user_id and user_role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    if job["status"] not in ["failed", "cancelled"]:
        return jsonify({"error": "Job cannot be retried in current state"}), 400

    try:
        retry_response = requests.patch(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/retry")
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if retry_response.status_code != 200:
        return jsonify(retry_response.json()), retry_response.status_code

    retried_job = retry_response.json()["job"]
    queue_payload = {"job_id": retried_job["job_id"]}

    try:
        redis_client.rpush(JOB_QUEUE_NAME, json.dumps(queue_payload))
    except Exception as e:
        return jsonify({"error": f"Redis unavailable: {str(e)}"}), 500

    return jsonify({"message": "Job retried and queued successfully", "job": retried_job}), 200

@app.route("/jobs/<int:job_id>", methods=["DELETE"])
@token_required
def delete_job(job_id):
    user_role = request.current_user["user_role"]
    user_id = request.current_user["user_id"]

    try:
        response = get_job_from_persistence(job_id)
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if response.status_code != 200:
        return jsonify(response.json()), response.status_code

    if response.json()["owner_user_id"] != user_id and user_role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    try:
        delete_response = requests.patch(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/delete")
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    return jsonify(delete_response.json()), delete_response.status_code

@app.route("/jobs/<int:job_id>/status", methods=["GET"])
@token_required
def get_job_status(job_id):
    user_role = request.current_user["user_role"]
    user_id = request.current_user["user_id"]

    try:
        job_response = get_job_from_persistence(job_id)
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    if job_response.status_code != 200:
        return jsonify(job_response.json()), job_response.status_code

    if job_response.json()["owner_user_id"] != user_id and user_role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    try:
        status_response = requests.get(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/status")
    except Exception as e:
        return jsonify({"error": f"Persistence service unavailable: {str(e)}"}), 500

    return jsonify(status_response.json()), status_response.status_code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)