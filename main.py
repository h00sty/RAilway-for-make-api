from fastapi import FastAPI, BackgroundTasks
from moviepy.editor import VideoFileClip, concatenate_videoclips
import uuid
import os
import requests

app = FastAPI()

# Папка для готовых видео
if not os.path.exists("downloads"): os.makedirs("downloads")

tasks = {}

def process_merge(task_id, video_urls, aspect_ratio):
    try:
        clips = []
        for url in video_urls:
            # Скачиваем файл во временную папку
            temp_name = f"temp_{uuid.uuid4()}.mp4"
            with open(temp_name, "wb") as f:
                f.write(requests.get(url).content)
            
            clip = VideoFileClip(temp_name)
            
            # Подгонка под размер (например 9:16)
            if aspect_ratio == "9:16":
                clip = clip.resize(height=1920).crop(x_center=clip.w/2, width=1080)
            
            clips.append(clip)
        
        final_clip = concatenate_videoclips(clips, method="compose")
        output_path = f"downloads/{task_id}.mp4"
        final_clip.write_videofile(output_path, codec="libx264")
        
        tasks[task_id] = {"status": "completed", "url": f"/download/{task_id}"}
    except Exception as e:
        tasks[task_id] = {"status": "failed", "error": str(e)}

@app.post("/merge")
async def merge(data: dict, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing"}
    background_tasks.add_task(process_merge, task_id, data["video_urls"], data.get("aspect_ratio", "16:9"))
    return {"task_id": task_id}

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    return tasks.get(task_id, {"status": "not_found"})
