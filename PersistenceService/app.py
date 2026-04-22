from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import os
import json
from functools import wraps
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

VALID_STATUSES = ["queued", "running", "completed", "failed", "cancelling", "cancelled"]

def get_connection():
    host = os.getenv("DB_HOST")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT")

    if not host:
        raise ValueError("DB_HOST is not set")
    if not database:
        raise ValueError("DB_NAME is not set")
    if not user:
        raise ValueError("DB_USER is not set")
    if not password:
        raise ValueError("DB_PASSWORD is not set")
    if not port:
        raise ValueError("DB_PORT is not set")

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

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id SERIAL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL,
                label VARCHAR(255) NOT NULL,
                executable_path TEXT NOT NULL,
                parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                status VARCHAR(50) NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelling', 'cancelled')),
                cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NULL,
                result_json JSONB NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP NULL,
                finished_at TIMESTAMP NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)

        conn.commit()
        cur.close()
        print("Table jobs created successfully or already exists.")

    except Exception as e:
        print("Database error:", e)

    finally:
        if conn:
            conn.close()

@app.route("/persistence/jobs", methods=["POST"])
def create_job():
    data = request.get_json(silent=True)

    owner_user_id = data["owner_user_id"]
    label = data["label"]
    executable_path = data["executable_path"]
    parameters_json = data["parameters_json"]
    if not parameters_json:
        parameters_json = {}
    
    if not owner_user_id or not label or not executable_path:
        return jsonify({"error": "owner_user_id, label and executable_path are required"}), 400
    
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            INSERT INTO jobs (
                owner_user_id,
                label,
                executable_path,
                parameters_json,
                status,
                cancel_requested,
                is_deleted,
                retry_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (owner_user_id, label, executable_path, json.dumps(parameters_json), "queued", False, False, 0))

        new_job = cur.fetchone()
        conn.commit()
        cur.close()

        return jsonify({"message": "Job created successfully", "job": new_job}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

@app.route("/persistence/jobs", methods=["GET"])
def get_jobs():
    owner_user_id = request.args.get("owner_user_id")
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if owner_user_id:
            cur.execute(
                """
                SELECT *
                FROM jobs
                WHERE owner_user_id = %s AND is_deleted = FALSE
                ORDER BY created_at DESC
                """,
                (owner_user_id,)
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM jobs
                WHERE is_deleted = FALSE
                ORDER BY created_at DESC
                """
            )

        jobs = cur.fetchall()
        cur.close()

        return jsonify({"jobs": jobs}), 200

    finally:
        conn.close()


@app.route("/persistence/jobs/<int:job_id>", methods=["GET"])
def get_job_by_id(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT *
            FROM jobs
            WHERE job_id = %s AND is_deleted = FALSE
            """,
            (job_id,))

        job = cur.fetchone()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(job), 200

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/status", methods=["GET"])
def get_job_status(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT job_id, status, cancel_requested, retry_count, started_at, finished_at, updated_at
            FROM jobs
            WHERE job_id = %s AND is_deleted = FALSE
            """,
            (job_id,))

        job = cur.fetchone()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(job), 200

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/cancel-flag", methods=["GET"])
def get_cancel_flag(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT cancel_requested
            FROM jobs
            WHERE job_id = %s AND is_deleted = FALSE
            """,
            (job_id,))

        row = cur.fetchone()
        cur.close()

        if not row:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({"cancel_requested": row[0]}), 200

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/start", methods=["PATCH"])
def start_job(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            UPDATE jobs
            SET status = 'running',
                started_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
              AND status = 'queued'
              AND cancel_requested = FALSE
              AND is_deleted = FALSE
            RETURNING *
            """,
            (job_id,))

        job = cur.fetchone()
        conn.commit()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({"message": "Job started successfully", "job": job}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/cancel", methods=["PATCH"])
def cancel_job(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            UPDATE jobs
            SET cancel_requested = TRUE,
                status = CASE
                    WHEN status IN ('queued', 'running') THEN 'cancelling'
                    ELSE status
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
              AND is_deleted = FALSE
            RETURNING *
            """,
            (job_id,))

        job = cur.fetchone()
        conn.commit()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({"message": "Cancel requested successfully", "job": job}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/status", methods=["PATCH"])
def update_job_status(job_id):
    data = request.get_json(silent=True)

    if "status" not in data:
        return jsonify({"error": "status is required"}), 400

    if "error_message" not in data:
        data["error_message"] = None

    if "result_json" not in data:
        data["result_json"] = None

    if "started_at" not in data:
        data["started_at"] = None

    if "finished_at" not in data:
        data["finished_at"] = None

    status = data["status"]
    error_message = data["error_message"]
    result_json = data["result_json"]
    started_at = data["started_at"]
    finished_at = data["finished_at"]

    if not status:
        return jsonify({"error": "status is required"}), 400
    
    if status not in VALID_STATUSES:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            UPDATE jobs
            SET status = %s,
                cancel_requested = CASE
                    WHEN %s = 'cancelled' THEN TRUE
                    ELSE cancel_requested
                END,
                error_message = %s,
                result_json = %s,
                started_at = COALESCE(%s, started_at),
                finished_at = COALESCE(%s, finished_at),
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
              AND is_deleted = FALSE
            RETURNING *
            """, 
            (status, status, error_message, json.dumps(result_json) if result_json is not None else None, started_at, finished_at, job_id))

        job = cur.fetchone()
        conn.commit()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({"message": "Job status updated successfully", "job": job}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/retry", methods=["PATCH"])
def retry_job(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                cancel_requested = FALSE,
                error_message = NULL,
                result_json = NULL,
                started_at = NULL,
                finished_at = NULL,
                retry_count = retry_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
              AND is_deleted = FALSE
              AND status IN ('failed', 'cancelled')
            RETURNING *
            """,
            (job_id,))

        job = cur.fetchone()
        conn.commit()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found or cannot be retried"}), 404

        return jsonify({"message": "Job retried successfully", "job": job}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

@app.route("/persistence/jobs/<int:job_id>/delete", methods=["PATCH"])
def delete_job(job_id):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            UPDATE jobs
            SET is_deleted = TRUE,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
              AND is_deleted = FALSE
            RETURNING *
            """,
            (job_id,))

        job = cur.fetchone()
        conn.commit()
        cur.close()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({"message": "Job deleted successfully", "job": job}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

if __name__ == "__main__":
    create_tables()
    app.run(host="0.0.0.0", port=5000)