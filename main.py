#!/usr/bin/env python3
import os
import json
import time
import glob
import subprocess
import requests
import random
import psutil
import ffmpeg
from datetime import datetime
from prompts import generate_prompts_with_ollama, example_prompts

# -----------------------
# Config
# -----------------------
PORT = 8000
COMFY_URL_BASE = f"http://127.0.0.1:{PORT}"
OUTPUT_DIR = os.path.expanduser("~/Documents/ComfyUI/output")
PROJECT_OUTPUT = os.path.join(os.getcwd(), "outputs")
os.makedirs(PROJECT_OUTPUT, exist_ok=True)

# Replace hardcoded PROMPTS with Ollama-generated prompts (list of 4 strings)
PROMPTS = generate_prompts_with_ollama(example_prompts)


# ============================================================
# PROCESS MANAGEMENT
# ============================================================
def kill_comfy_processes():
    """
    Kill ComfyUI processes. Handles both Python-launched ComfyUI and the desktop exe.
    Returns number of processes killed.
    """
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = " ".join(str(x).lower() for x in cmdline)
            # match python processes running comfy or the ComfyUI.exe process itself
            if ('comfy' in name) or ('comfyui' in name) or ('comfy' in cmdline_str) or ('comfyui' in cmdline_str):
                print(f"Terminating ComfyUI process (PID: {proc.info['pid']}, name: {proc.info.get('name')})")
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
        except Exception:
            pass
        time.sleep(2)

    raise RuntimeError("ComfyUI did not start within timeout.")


def find_comfy_port():
    try:
        r = requests.get(f"{COMFY_URL_BASE}/system_stats", timeout=1)
        return r.status_code == 200
    except Exception:
        return False


# ============================================================
# WORKFLOW UTILITIES
# ============================================================
def randomize_workflow(workflow):
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if "seed" in inputs and isinstance(inputs["seed"], (int, float)):
            inputs["seed"] = random.randint(0, 2**31 - 1)
        if "noise_seed" in inputs and isinstance(inputs["noise_seed"], (int, float)):
            inputs["noise_seed"] = random.randint(0, 2**31 - 1)
    return workflow


def copy_to_input_folder(image_path):
    import shutil
    comfy_input = os.path.expanduser("~/Documents/ComfyUI/input")
    os.makedirs(comfy_input, exist_ok=True)
    dest = os.path.join(comfy_input, os.path.basename(image_path))
    shutil.copy2(image_path, dest)
    print(f"Copied to input: {os.path.basename(dest)}")


# ============================================================
# IMAGE GENERATION
# ============================================================
def generate_image(prompt, workflow_file="image_workflow.json"):
    import glob
    print("\n" + "="*60)
    print("GENERATING INITIAL IMAGE")
    print("="*60)

    # sanitize and show prompt
    prompt = str(prompt).replace("’", "'").replace("\n", " ").strip()
    print("Prompt being sent:", repr(prompt))

    with open(workflow_file, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    if "6" not in workflow or "inputs" not in workflow["6"]:
        raise RuntimeError("Node 6 with inputs not found in workflow")
    workflow["6"]["inputs"]["text"] = prompt
    workflow = randomize_workflow(workflow)

    url = f"{COMFY_URL_BASE}/prompt"
    data = {"prompt": workflow, "client_id": f"client_{random.randint(1000,9999)}"}
    r = requests.post(url, json=data)
    r.raise_for_status()
    print("Request sent to ComfyUI...")

    start = time.time()
    initial_imgs = set(glob.glob(os.path.join(OUTPUT_DIR, "ComfyUI_*.png")))
    latest = None
    print("Waiting for ComfyUI to generate the image...")
    while True:
        imgs = set(glob.glob(os.path.join(OUTPUT_DIR, "ComfyUI_*.png")))
        new_imgs = imgs - initial_imgs
        if new_imgs:
            latest = max(new_imgs, key=os.path.getmtime)
            break
        time.sleep(2)

    print(f"Generated: {os.path.basename(latest)}")
    copy_to_input_folder(latest)
    return latest


# ============================================================
# VIDEO GENERATION
# ============================================================
def generate_video(image_path, prompt, workflow_file="video_workflow.json", video_num=1):
    print(f"\n{'='*60}\nGENERATING VIDEO {video_num}\n{'='*60}")

    with open(workflow_file, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    workflow["6"]["inputs"]["text"] = str(prompt).replace("\n", " ").strip()
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


# ============================================================
# FRAME EXTRACTION
# ============================================================
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


# ============================================================
# SPLITTING
# ============================================================
def get_duration(path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def split_video_half(input_path, out1, out2):
    """
    Re-encode both halves to ensure accurate split and matching parameters.
    """
    dur = get_duration(input_path)
    mid = dur / 2.0

    # first half (re-encode)
    (
        ffmpeg
        .input(input_path, ss=0, t=mid)
        .output(out1, vcodec='libx264', acodec='aac', r=30, pix_fmt='yuv420p')
        .run(overwrite_output=True)
    )

    # second half (re-encode)
    (
        ffmpeg
        .input(input_path, ss=mid)
        .output(out2, vcodec='libx264', acodec='aac', r=30, pix_fmt='yuv420p')
        .run(overwrite_output=True)
    )


# ============================================================
# PICK REACTION WITH EXCLUDE
# ============================================================
def pick_random_from(folder, exclude=None):
    files = sorted(glob.glob(os.path.join(folder, "*.mp4")))
    if not files:
        raise RuntimeError(f"No reaction clips found in {folder}")
    if exclude:
        files = [f for f in files if f not in exclude]
    if not files:
        raise RuntimeError("No remaining clips available after exclusions.")
    return random.choice(files)


# ============================================================
# CONCAT (re-encode during concat)
# ============================================================
def concat_videos(video_list, output_path):
    """
    Re-encodes individual clips to uniform params, then concatenates re-encoding the final file.
    This is robust for sharing platforms and avoids frozen frames/black frames.
    """
    print("\n" + "="*60)
    print("CONCATENATING SEQUENCE SAFELY")
    print("="*60)

    temp_dir = os.path.join(os.path.dirname(output_path), "temp_concat")
    os.makedirs(temp_dir, exist_ok=True)

    temp_files = []
    for i, v in enumerate(video_list):
        temp_file = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
        (
            ffmpeg
            .input(v)
            .output(temp_file, vcodec='libx264', acodec='aac', r=30, pix_fmt='yuv420p')
            .run(overwrite_output=True, quiet=True)
        )
        temp_files.append(temp_file)

    list_path = os.path.join(temp_dir, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for tf in temp_files:
            f.write(f"file '{os.path.abspath(tf)}'\n")

    # Re-encode during concat (avoid -c copy)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "fast",
        "-c:a", "aac",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # show stderr for debugging
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")

    # cleanup
    import shutil
    shutil.rmtree(temp_dir)
    return output_path


# ============================================================
# ADD MUSIC
# ============================================================
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


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    print("\n" + "="*60)
    print("COMFYUI VIDEO GENERATION PIPELINE")
    print("="*60)
    print("Generated Prompts:")
    for i, p in enumerate(PROMPTS):
        print(i, repr(p))

    # kill existing comfy first
    kill_comfy_processes()

    if not find_comfy_port():
        launch_comfyui()
        wait_for_comfyui()
    else:
        print("ComfyUI already running.")

    print(f"Using: {COMFY_URL_BASE}")
    print("="*60)

    try:
        # --- INITIAL IMAGE ---
        initial_prompt = PROMPTS[0]
        current_image = generate_image(initial_prompt)

        # --- GENERATE VIDEOS (3) ---
        generated_videos = []
        video_prompts = PROMPTS[1:]
        for i, prompt in enumerate(video_prompts, start=1):
            v = generate_video(current_image, prompt, video_num=i)
            generated_videos.append(v)
            if i < len(video_prompts):
                current_image = extract_last_frame(v)

        if len(generated_videos) < 3:
            raise RuntimeError(f"Expected 3 generated videos, got {len(generated_videos)}")

        # --- REACTIONS (strict per-folder, no duplicates) ---
        reactions1_dir = os.path.join(os.getcwd(), "reactions", "1")
        reactions2_dir = os.path.join(os.getcwd(), "reactions", "2")

        def list_mp4s(path):
            return [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(".mp4")]

        r1_list = list_mp4s(reactions1_dir)
        r2_list = list_mp4s(reactions2_dir)

        if len(r1_list) < 2:
            raise RuntimeError("Need at least TWO reaction videos in reactions/1")
        if len(r2_list) < 2:
            raise RuntimeError("Need at least TWO reaction videos in reactions/2")

        # pick two unique from folder 1
        reaction1_a = random.choice(r1_list)
        r1_list.remove(reaction1_a)
        reaction1_b = random.choice(r1_list)

        # pick two unique from folder 2
        reaction2_a = random.choice(r2_list)
        r2_list.remove(reaction2_a)
        reaction2_b = random.choice(r2_list)

        # --- SPLIT FIRST GENERATED VIDEO ---
        v1 = generated_videos[0]
        v1_first = os.path.join(PROJECT_OUTPUT, "v1_first_half.mp4")
        v1_second = os.path.join(PROJECT_OUTPUT, "v1_second_half.mp4")
        split_video_half(v1, v1_first, v1_second)

        # --- BUILD FINAL SEQUENCE (exact order you specified) ---
        sequence = [
            v1_first,          # 1
            reaction1_a,       # 2 (from reactions/1)
            v1_second,         # 3
            reaction1_b,       # 4 (from reactions/1, different)
            generated_videos[1],  # 5 (video2)
            reaction2_a,       # 6 (from reactions/2)
            generated_videos[2],  # 7 (video3)
            reaction2_b        # 8 (from reactions/2, different)
        ]

        # --- STITCH ---
        stitched_path = os.path.join(PROJECT_OUTPUT, "stitched.mp4")
        concat_videos(sequence, stitched_path)

        # --- ADD MUSIC ---
        music_path = os.path.join(os.getcwd(), "song.mp3")
        final_path = os.path.join(PROJECT_OUTPUT, f"final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        final_output = add_music(stitched_path, music_path, final_path)

        print("\n" + "="*60)
        print("PIPELINE COMPLETE")
        print("="*60)
        print(f"Final Output: {final_output}")
        print("="*60 + "\n")

    finally:
        # ensure cleanup - kill comfy processes (desktop exe + python variants)
        kill_comfy_processes()


# ============================================================
# ENTRY
# ============================================================
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nERROR:", e)
        import traceback
        traceback.print_exc()
