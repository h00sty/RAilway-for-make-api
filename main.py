import os
import uuid
import requests
import subprocess
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()

UPLOAD_DIR = "temp_videos"
RESULT_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

tasks = {}

@app.get("/api/validate")
async def validate_connection():
    return {"status": "ok", "user": "Admin-Owner"}

def merge_process_ffmpeg(task_id: str, urls: list, aspect_ratio: str):
    try:
        downloaded_files = []
        normalized_files = []

        # 1. Скачивание
        for i, url in enumerate(urls):
            raw_path = os.path.join(UPLOAD_DIR, f"{task_id}_{i}_raw.mp4")
            resp = requests.get(url, stream=True)
            with open(raw_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded_files.append(raw_path)

            # 2. Нормализация (приводим каждое видео к одному стандарту, чтобы они склеились)
            # Это делается по очереди, чтобы не забить память
            norm_path = os.path.join(UPLOAD_DIR, f"{task_id}_{i}_norm.ts")
            
            # Настройка размера под формат
            scale = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if aspect_ratio == "9:16" else "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
            
            cmd_norm = [
                'ffmpeg', '-y', '-i', raw_path,
                '-vf', f"{scale},fps=30",
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                '-c:a', 'aac', '-ar', '44100',
                '-f', 'mpegts', norm_path
            ]
            subprocess.run(cmd_norm, check=True)
            normalized_files.append(norm_path)

        # 3. Склейка (Concat)
        result_path = os.path.join(RESULT_DIR, f"{task_id}.mp4")
        concat_str = "|".join(normalized_files)
        
        cmd_merge = [
            'ffmpeg', '-y', '-i', f"concat:{concat_str}",
            '-c', 'copy', '-bsf:a', 'aac_adtstoasc', result_path
        ]
        subprocess.run(cmd_merge, check=True)

        # 4. Чистка
        for f in downloaded_files + normalized_files:
            if os.path.exists(f): os.remove(f)

        tasks[task_id] = {"status": "completed", "download_url": f"/download/{task_id}.mp4"}
    except Exception as e:
        tasks[task_id] = {"status": "failed", "message": str(e)}

@app.post("/api/merge")
async def start_merge(data: dict, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    urls = data.get("video_urls", [])
    ratio = data.get("aspect_ratio", "9:16")
    tasks[task_id] = {"status": "processing"}
    background_tasks.add_task(merge_process_ffmpeg, task_id, urls, ratio)
    return {"task_id": task_id}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    return tasks.get(task_id, {"status": "not_found"})

@app.get("/download/{file_name}")
async def download_file(file_name: str):
    path = os.path.join(RESULT_DIR, file_name)
    return FileResponse(path) if os.path.exists(path) else HTTPException(status_code=404)
