import os
import json
import time
import glob
import subprocess
import requests
import random
import psutil
from datetime import datetime

PORT = 8000
COMFY_URL_BASE = f"http://127.0.0.1:{PORT}"
OUTPUT_DIR = os.path.expanduser("~/Documents/ComfyUI/output")
PROJECT_OUTPUT = os.path.join(os.getcwd(), "outputs")
os.makedirs(PROJECT_OUTPUT, exist_ok=True)

PROMPTS = [
    "An incredibly old, frail man with thin white hair facing directly toward the camera, standing on the huge glossy AGT stage, surrounded by bright blue and purple stage lights, glowing star patterns...",
    "The old man facing the camera begins a grotesque transformation into a frail turkey-human hybrid...",
    "The turkey-human hybrid transforms into a magnificent golden phoenix with a beautiful human face..."
]

# Prevent ComfyUI conflicts from existing processes
def kill_comfy_processes():
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('comfy' in str(arg).lower() for arg in cmdline):
                    print(f"Terminating ComfyUI process (PID: {proc.info['pid']})")
                    proc.kill()
                    killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed > 0:
        time.sleep(2)
    return killed


def launch_comfyui():
    print("Launching ComfyUI...")
    comfy_path = r"C:\Users\User\AppData\Local\Programs\ComfyUI\ComfyUI.exe"
    if not os.path.exists(comfy_path):
        raise RuntimeError(f"ComfyUI.exe not found at: {comfy_path}")

    subprocess.Popen([comfy_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("ComfyUI launched.")


def wait_for_comfyui(timeout=60):
    print("Waiting for ComfyUI to start...")
    stats_url = f"{COMFY_URL_BASE}/system_stats"
    start = time.time()

    while time.time() - start < timeout:
        try:
            r = requests.get(stats_url, timeout=2)
            if r.status_code == 200:
                print("ComfyUI is ready.")
                return True
        except:
            pass

        time.sleep(2)

    raise RuntimeError("ComfyUI did not start within timeout.")

# Check if running
def find_comfy_port():
    try:
        r = requests.get(f"{COMFY_URL_BASE}/system_stats", timeout=1)
        return r.status_code == 200
    except:
        return False

# ComfyUI workflow stuff
def randomize_workflow(workflow):
    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue

        if "seed" in inputs:
            if isinstance(inputs["seed"], (int, float)):
                inputs["seed"] = random.randint(0, 2**31 - 1)

        if "noise_seed" in inputs:
            if isinstance(inputs["noise_seed"], (int, float)):
                inputs["noise_seed"] = random.randint(0, 2**31 - 1)

    return workflow


def copy_to_input_folder(image_path):
    import shutil
    comfy_input = os.path.expanduser("~/Documents/ComfyUI/input")
    os.makedirs(comfy_input, exist_ok=True)

    dest = os.path.join(comfy_input, os.path.basename(image_path))
    shutil.copy2(image_path, dest)
    print(f"Copied to input: {os.path.basename(dest)}")


# Generation pipeline
def generate_image(prompt, workflow_file="image_workflow.json"):
    print("\n" + "="*60)
    print("GENERATING INITIAL IMAGE")
    print("="*60)

    with open(workflow_file, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    workflow["6"]["inputs"]["text"] = prompt
    workflow = randomize_workflow(workflow)

    url = f"{COMFY_URL_BASE}/prompt"
    data = {"prompt": workflow, "client_id": f"client_{random.randint(1000,9999)}"}

    r = requests.post(url, json=data)
    r.raise_for_status()
    print("Request sent to ComfyUI...")

    start = time.time()
    initial_count = len(glob.glob(os.path.join(OUTPUT_DIR, "ComfyUI_*.png")))
    latest = None

    while time.time() - start < 120:
        imgs = sorted(glob.glob(os.path.join(OUTPUT_DIR, "ComfyUI_*.png")), key=os.path.getmtime)
        if len(imgs) > initial_count:
            latest = imgs[-1]
            break
        time.sleep(2)

    if not latest:
        raise RuntimeError("Image generation timeout.")

    print(f"Generated: {os.path.basename(latest)}")
    copy_to_input_folder(latest)
    return latest


def generate_video(image_path, prompt, workflow_file="video_workflow.json", video_num=1):
    print(f"\n{'='*60}\nGENERATING VIDEO {video_num}\n{'='*60}")

    with open(workflow_file, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    workflow["6"]["inputs"]["text"] = prompt
    workflow["52"]["inputs"]["image"] = os.path.basename(image_path)
    workflow = randomize_workflow(workflow)

    url = f"{COMFY_URL_BASE}/prompt"
    data = {"prompt": workflow, "client_id": f"client_{random.randint(1000,9999)}"}

    r = requests.post(url, json=data)
    r.raise_for_status()
    print("Request sent to ComfyUI...")

    video_dir = os.path.join(OUTPUT_DIR, "video")
    os.makedirs(video_dir, exist_ok=True)

    start = time.time()
    initial_count = len(glob.glob(os.path.join(video_dir, "ComfyUI_*.mp4")))
    latest = None

    while time.time() - start < 300:
        vids = sorted(glob.glob(os.path.join(video_dir, "ComfyUI_*.mp4")), key=os.path.getmtime)
        if len(vids) > initial_count:
            latest = vids[-1]
            break
        time.sleep(3)

    if not latest:
        raise RuntimeError(f"Video {video_num} generation timeout.")

    print(f"Generated: {os.path.basename(latest)}")
    return latest


def extract_last_frame(video_path, output_dir=None):
    print(f"\nExtracting final frame from: {os.path.basename(video_path)}")
    if output_dir is None:
        output_dir = OUTPUT_DIR

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    frame_path = os.path.join(output_dir, f"final_frame_{timestamp}.png")

    cmd = [
        "ffmpeg", "-y",
        "-sseof", "-0.1",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        frame_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg extraction failed: {result.stderr}")

    copy_to_input_folder(frame_path)
    return frame_path


def concat_videos(video_list, output_path):
    print("\n" + "="*60)
    print("CONCATENATING VIDEOS")
    print("="*60)

    list_path = os.path.join(os.path.dirname(output_path), "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for v in video_list:
            f.write(f"file '{os.path.abspath(v)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")

    return output_path


def add_music(video_path, music_path, output_path):
    print("\n" + "="*60)
    print("ADDING MUSIC")
    print("="*60)

    if not os.path.exists(music_path):
        print("Music not found, skipping.")
        return video_path

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", music_path,
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio merge failed: {result.stderr}")

    return output_path


# Main
def main():
    print("\n" + "="*60)
    print("COMFYUI VIDEO GENERATION PIPELINE")
    print("="*60)

    kill_comfy_processes()

    if not find_comfy_port():
        launch_comfyui()
        wait_for_comfyui()
    else:
        print("ComfyUI already running.")

    print(f"Using: {COMFY_URL_BASE}")
    print("="*60)

    initial_prompt = (
        "An incredibly old, frail man with thin white hair..."
    )

    current_image = generate_image(initial_prompt)
    generated_videos = []

    for i, prompt in enumerate(PROMPTS, 1):
        v = generate_video(current_image, prompt, video_num=i)
        generated_videos.append(v)

        if i < len(PROMPTS):
            current_image = extract_last_frame(v)

    reaction_dir = os.path.join(os.getcwd(), "reaction_videos")
    reaction_videos = []
    if os.path.exists(reaction_dir):
        reaction_videos = sorted(glob.glob(os.path.join(reaction_dir, "*.mp4")))

    all_videos = reaction_videos + generated_videos

    stitched = os.path.join(PROJECT_OUTPUT, "stitched.mp4")
    concat_videos(all_videos, stitched)

    music_path = os.path.join(os.getcwd(), "song.mp3")
    final_path = os.path.join(PROJECT_OUTPUT, f"final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
    final_output = add_music(stitched, music_path, final_path)

    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
    print("="*60)
    print(f"Output: {final_output}")
    print(f"Videos generated: {len(generated_videos)}")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nERROR:", e)
        import traceback
        traceback.print_exc()
