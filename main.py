import os
import uuid
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from fastapi.responses import FileResponse
from moviepy.editor import VideoFileClip, concatenate_videoclips

app = FastAPI()

# Папки для файлов
UPLOAD_DIR = "temp_videos"
RESULT_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

# База данных задач
tasks = {}

# 1. Проверка соединения (для Make Connection)
@app.get("/api/validate")
async def validate_connection():
    return {"status": "ok", "user": "Admin-Owner"}

# 2. Процесс склейки (в фоновом режиме)
def merge_process(task_id: str, urls: list, aspect_ratio: str):
    try:
        clips = []
        for i, url in enumerate(urls):
            path = os.path.join(UPLOAD_DIR, f"{task_id}_{i}.mp4")
            resp = requests.get(url, stream=True)
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            clip = VideoFileClip(path)
            if aspect_ratio == "9:16":
                clip = clip.resize(height=1920)
                if clip.w > 1080: clip = clip.crop(x_center=clip.w/2, width=1080)
            elif aspect_ratio == "16:9":
                clip = clip.resize(width=1920)
                if clip.h > 1080: clip = clip.crop(y_center=clip.h/2, height=1080)
            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")
        result_path = os.path.join(RESULT_DIR, f"{task_id}.mp4")
        final_clip.write_videofile(result_path, codec="libx264", audio_codec="aac")
        
        for clip in clips: clip.close()
        tasks[task_id] = {"status": "completed", "download_url": f"/download/{task_id}.mp4"}
    except Exception as e:
        tasks[task_id] = {"status": "failed", "message": str(e)}

# 3. Эндпоинт запуска склейки
@app.post("/api/merge")
async def start_merge(data: dict, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    urls = data.get("video_urls", [])
    ratio = data.get("aspect_ratio", "9:16")
    if not urls: raise HTTPException(status_code=400, detail="No URLs")
    
    tasks[task_id] = {"status": "processing"}
    background_tasks.add_task(merge_process, task_id, urls, ratio)
    return {"task_id": task_id}

# 4. Эндпоинт проверки статуса
@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    return tasks.get(task_id, {"status": "not_found"})

# 5. Эндпоинт скачивания
@app.get("/download/{file_name}")
async def download_file(file_name: str):
    path = os.path.join(RESULT_DIR, file_name)
    if os.path.exists(path): return FileResponse(path)
    raise HTTPException(status_code=404, detail="File not found")
