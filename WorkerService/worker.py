from flask import Flask
import os
import json
import time
import threading
import subprocess
import requests
import redis
from datetime import datetime, timezone

app = Flask(__name__)

PERSISTENCE_BASE_URL = os.getenv("PERSISTENCE_BASE_URL")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def get_job(job_id):
    return requests.get(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}")

def get_cancel_flag(job_id):
    return requests.get(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/cancel-flag")

def start_job(job_id):
    return requests.patch(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/start")

def update_job_status(job_id, status, error_message=None, result_json=None, started_at=None, finished_at=None):
    payload = {"status": status, "error_message": error_message, "result_json": result_json,
        "started_at": started_at, "finished_at": finished_at}
    return requests.patch(f"{PERSISTENCE_BASE_URL}/persistence/jobs/{job_id}/status", json=payload)

def mark_job_cancelled(job_id):
    return update_job_status(job_id=job_id, status="cancelled", error_message=None, result_json=None, started_at=None, finished_at=datetime.now(timezone.utc).isoformat())

def mark_job_failed(job_id, error_message):
    return update_job_status(job_id=job_id, status="failed", error_message=error_message, result_json=None, started_at=None, finished_at=datetime.now(timezone.utc).isoformat())

def mark_job_completed(job_id, result_json):
    return update_job_status(job_id=job_id, status="completed", error_message=None, result_json=result_json, started_at=None, finished_at=datetime.now(timezone.utc).isoformat())

def execute_job(job):
    job_id = job["job_id"]
    executable_path = job["executable_path"]
    parameters_json = job.get("parameters_json")

    if parameters_json:
        parameters_json = {}

    args = []
    if isinstance(parameters_json, dict):
        for key, value in parameters_json.items():
            args.append(f"--{key}")
            args.append(str(value))

    command = ["python", executable_path] + args
    print(f"[WORKER] Running job {job_id}: {command}")

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception as e:
        print(f"[WORKER] Couldn't start job {job_id}: {e}")
        mark_job_failed(job_id, str(e))
        return

    while True:
        cancel_resp = get_cancel_flag(job_id)

        if cancel_resp.status_code == 200:
            if cancel_resp.json().get("cancel_requested"):
                print(f"[WORKER] Cancelling job {job_id}")
                process.terminate()

                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

                mark_job_cancelled(job_id)
                return

        if process.poll() is not None:
            break

        time.sleep(1)

    stdout, stderr = process.communicate()

    if stdout is None:
        stdout = ""
    else:
        stdout = stdout.strip()

    if stderr is None:
        stderr = ""
    else:
        stderr = stderr.strip()

    if process.returncode == 0:
        print(f"[WORKER] Job {job_id} done")
        mark_job_completed(job_id, {"stdout": stdout, "stderr": stderr, "return_code": process.returncode})
    else:
        if stderr:
            error_msg = stderr
        else:
            error_msg = f"Exited with code {process.returncode}"
        print(f"[WORKER] Job {job_id} failed: {error_msg}")
        mark_job_failed(job_id, error_msg)

def process_job(job_id):
    print(f"[WORKER] Processing job_id={job_id}")

    job_response = get_job(job_id)
    if job_response.status_code != 200:
        print(f"[WORKER] Job {job_id} not found in persistence. Status={job_response.status_code}, body={job_response.text}")
        return

    cancel_response = get_cancel_flag(job_id)
    if cancel_response.status_code == 200 and cancel_response.json().get("cancel_requested"):
        print(f"[WORKER] Job {job_id} already marked for cancel before start.")
        mark_job_cancelled(job_id)
        return

    start_response = start_job(job_id)
    if start_response.status_code != 200:
        print(f"[WORKER] Could not mark job {job_id} as running. Status={start_response.status_code}, body={start_response.text}")
        return

    job = job_response.json()
    execute_job(job)

def worker_loop():
    print("[WORKER] Worker started.")

    while True:
        try:
            result = redis_client.blpop(JOB_QUEUE_NAME, timeout=5)
            if result is None:
                continue

            queue_name, payload = result
            print(f"[WORKER] Got job from Redis: {payload}")

            job_id = json.loads(payload)["job_id"]
            if not job_id:
                print("[WORKER] Invalid payload, missing job_id")
                continue

            process_job(job_id)

        except Exception as e:
            print(f"[WORKER] Error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()

    app.run(host="0.0.0.0", port=5000)