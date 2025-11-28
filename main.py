#!/usr/bin/env python3
import os
import sys
import json
import time
import glob
import subprocess
import requests
import random
import psutil
import shutil
import ffmpeg
import socket
import websockets
import asyncio
import logging
import threading
from datetime import datetime

from prompts import generate_full_video_metadata
from upload import upload_short

log_file_path = r"C:\Users\User\Desktop\content_machine\output.log"
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)

sys.stdout.flush()


# Config

PORT = 8000
COMFY_URL_BASE = f"http://127.0.0.1:{PORT}"
PATH_TO_COMFY = r"C:\Users\User\AppData\Local\Programs\ComfyUI\ComfyUI.exe"
PATH_TO_OLLAMA = r"C:\Users\User\AppData\Local\Programs\Ollama\ollama.exe"
OUTPUT_DIR = os.path.expanduser("~/Documents/ComfyUI/output")
PROJECT_OUTPUT = os.path.join(os.getcwd(), "outputs")
os.makedirs(PROJECT_OUTPUT, exist_ok=True)

DISCORD_WEBHOOK = {YOUR_WEBHOOK_URL_HERE}
WS_URL = f"ws://127.0.0.1:{PORT}/ws"



# DISCORD NOTIFICATIONS

def send_discord(message):
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                DISCORD_WEBHOOK,
                json={"content": message},
                timeout=10
            )
            response.raise_for_status()
            logging.info(f"Discord: {message}")
            return True
        except requests.exceptions.RequestException as e:
            logging.warning(f"Discord notification failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logging.error(f"Failed to send Discord notification after {max_retries} attempts")
                return False

ws_monitor_active = False

def start_websocket_monitor():
    global ws_monitor_active

    def run_monitor():
        async def listen():
            global ws_monitor_active
            ws_monitor_active = True
            
            reconnect_delay = 5
            max_reconnect_delay = 300
            consecutive_failures = 0
            
            while ws_monitor_active:
                try:
                    logging.info(f"Attempting WebSocket connection to {WS_URL}")
                    
                    async with websockets.connect(
                        WS_URL,
                        ping_interval=20,
                        ping_timeout=10,
                        close_timeout=10
                    ) as ws:
                        logging.info("WebSocket monitor connected")
                        send_discord("WebSocket monitor connected")
                        
                        reconnect_delay = 5
                        consecutive_failures = 0
                        
                        while ws_monitor_active:
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                msg = json.loads(raw)
                                
                                msg_type = msg.get("type")
                                
                                if msg_type == "status":
                                    continue
                                elif msg_type == "progress":
                                    data = msg.get("data", {})
                                    value = data.get("value", "?")
                                    max_val = data.get("max", "?")
                                    try:
                                        requests.post(
                                            DISCORD_WEBHOOK,
                                            json={"content": f"Progress: {value}/{max_val}"},
                                            timeout=5
                                        )
                                    except Exception as e:
                                        logging.warning(f"Failed to send progress to Discord: {e}")
                                else:
                                    pretty = json.dumps(msg, indent=2)
                                    try:
                                        requests.post(
                                            DISCORD_WEBHOOK,
                                            json={"content": f"[ComfyUI] {pretty[:1800]}"},
                                            timeout=5
                                        )
                                    except Exception as e:
                                        logging.warning(f"Failed to send message to Discord: {e}")
                                        
                            except asyncio.TimeoutError:
                                continue
                            except websockets.exceptions.ConnectionClosed as e:
                                logging.warning(f"WebSocket connection closed: {e}")
                                break
                            except Exception as e:
                                logging.error(f"Error processing WebSocket message: {e}")
                                continue
                
                except (
                    websockets.exceptions.WebSocketException,
                    ConnectionRefusedError,
                    OSError,
                    asyncio.TimeoutError
                ) as e:
                    consecutive_failures += 1
                    logging.warning(
                        f"WebSocket connection failed (attempt {consecutive_failures}): {e}"
                    )
                    
                    if ws_monitor_active:
                        current_delay = min(
                            reconnect_delay * (1.5 ** (consecutive_failures - 1)),
                            max_reconnect_delay
                        )
                        
                        logging.info(f"Reconnecting in {current_delay:.1f} seconds...")
                        
                        if consecutive_failures == 1 or current_delay >= 60:
                            try:
                                send_discord(
                                    f"WebSocket disconnected. Reconnecting in {int(current_delay)}s..."
                                )
                            except:
                                pass
                        
                        wait_start = time.time()
                        while time.time() - wait_start < current_delay and ws_monitor_active:
                            await asyncio.sleep(1)
                
                except Exception as e:
                    logging.error(f"Unexpected WebSocket error: {e}", exc_info=True)
                    if ws_monitor_active:
                        await asyncio.sleep(10)
            
            logging.info("WebSocket monitor stopped")


        try:
            asyncio.run(listen())
        except Exception as e:
            logging.error(f"WebSocket monitor thread crashed: {e}", exc_info=True)
        finally:
            ws_monitor_active = False

    import threading
    thread = threading.Thread(target=run_monitor, daemon=True)
    thread.start()
    logging.info("WebSocket monitor thread started")


def stop_websocket_monitor():
    """Stop the WebSocket monitor gracefully"""
    global ws_monitor_active
    if ws_monitor_active:
        logging.info("Stopping WebSocket monitor...")
        ws_monitor_active = False
        time.sleep(2)
        logging.info("WebSocket monitor stopped")



# PROCESS MANAGEMENT

def kill_comfy_processes():
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(str(x).lower() for x in cmdline)

            if (
                ("comfy" in name)
                or ("comfyui" in name)
                or ("comfy" in cmdline_str)
                or ("comfyui" in cmdline_str)
            ):
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
    send_discord("Launching ComfyUI...")
    comfy_path = PATH_TO_COMFY

    if not os.path.exists(comfy_path):
        raise RuntimeError(f"ComfyUI.exe not found at: {comfy_path}")

    subprocess.Popen([comfy_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("ComfyUI launched.")


def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except:
        return False


def wait_for_ollama(
    hosts=("127.0.0.1", "::1"), port=11434, timeout=600, check_interval=5
):
    send_discord("Waiting for Ollama to start...")
    start_time = time.time()
    last_log = 0

    while time.time() - start_time < timeout:
        for host in hosts:
            try:
                family = socket.AF_INET6 if ":" in host else socket.AF_INET
                with socket.socket(family, socket.SOCK_STREAM) as s:
                    s.settimeout(1.0)
                    s.connect((host, port))
                    logging.info(f"Ollama ready on {host}:{port}")
                    send_discord("Ollama is ready")
                    return True
            except Exception:
                pass

        elapsed = int(time.time() - start_time)
        if elapsed - last_log >= 30:
            last_log = elapsed
            logging.info(f"Still waiting for Ollama... ({elapsed}s elapsed)")
            try:
                procs = [
                    f"{p.pid}:{p.info.get('name')}"
                    for p in psutil.process_iter(["name"])
                ][:50]
                logging.info("Top processes: " + ", ".join(procs))
            except Exception as e:
                logging.warning(f"Could not list processes: {e}")

            try:
                conns = []
                for c in psutil.net_connections(kind="inet"):
                    if c.laddr and c.laddr.port == port:
                        conns.append(f"{c.pid or '?'}:{c.status}")
                logging.info(f"Connections on port {port}: {conns}")
            except Exception as e:
                logging.debug(f"Could not inspect net_connections: {e}")

        time.sleep(check_interval)

    logging.error(f"Ollama did not start within {timeout}s")
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            n = proc.info.get("name") or ""
            if (
                "ollama" in (n or "").lower()
                or "ollama" in " ".join(proc.info.get("cmdline") or []).lower()
            ):
                logging.error(
                    f"Found Ollama-like process at timeout: pid={proc.pid} name={n} cmd={proc.info.get('cmdline')}"
                )
    except Exception:
        pass

    raise TimeoutError(f"Ollama on port {port} did not start within {timeout} seconds")


def wait_for_comfyui(timeout=600):
    print("Waiting for ComfyUI to fully start...")
    send_discord("Waiting for ComfyUI to start...")
    stats_url = f"{COMFY_URL_BASE}/system_stats"
    start = time.time()

    while time.time() - start < timeout:
        if port_open("127.0.0.1", PORT):
            try:
                r = requests.get(stats_url, timeout=2)
                if r.status_code == 200:
                    print("ComfyUI is ready.")
                    send_discord("ComfyUI is ready")
                    return True
            except:
                pass

        time.sleep(2)

    raise RuntimeError("ComfyUI did not start within timeout.")


def find_comfy_port():
    try:
        r = requests.get(f"{COMFY_URL_BASE}/system_stats", timeout=1)
        return r.status_code == 200
    except Exception:
        return False


def launch_ollama():
    """Start Ollama only if no existing process is present. Return PID if started, else None."""
    logging.info("Attempting to launch Ollama...")
    ollama_path = PATH_TO_OLLAMA

    if not os.path.exists(ollama_path):
        raise RuntimeError(f"Ollama not found at: {ollama_path}")

    if ollama_is_running():
        logging.info("launch_ollama: Ollama already present, skipping launch.")
        return None

    proc = subprocess.Popen(
        [ollama_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
            else 0
        ),
    )
    logging.info(f"Started Ollama (pid={proc.pid})")
    return proc.pid


def ollama_is_running():
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if "ollama" in name or "ollama" in cmd:
                logging.info(f"Found Ollama process: {proc.pid} {name} {cmd[:200]}")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for host in ("127.0.0.1", "::1"):
        try:
            with socket.socket(
                socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM
            ) as s:
                s.settimeout(1.0)
                s.connect((host, 11434))
                logging.info(f"Socket connect succeeded to {host}:11434")
                return True
        except Exception:
            pass

    return False



# INPUT/OUTPUT HELPERS

def copy_to_input_folder(path):
    comfy_input = os.path.expanduser("~/Documents/ComfyUI/input")
    os.makedirs(comfy_input, exist_ok=True)

    dest = os.path.join(comfy_input, os.path.basename(path))
    shutil.copy2(path, dest)
    print(f"Copied to input: {os.path.basename(dest)}")
    return dest


def pick_largest_mp4(paths):
    candidates = [p for p in paths if p.lower().endswith(".mp4") and os.path.exists(p)]
    if not candidates:
        return None
    return max(candidates, key=os.path.getsize)


def wait_for_file_complete(path, check_interval=3, stable_cycles=3):
    print(f"Waiting for file to finish writing: {path}")

    last_size = -1
    stable_count = 0

    while True:
        if os.path.exists(path):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1

            if size > 0:
                if size == last_size:
                    stable_count += 1
                    if stable_count >= stable_cycles:
                        print(f"File is complete. Size: {size:,} bytes")
                        return
                else:
                    stable_count = 0
                last_size = size

        time.sleep(check_interval)


def wait_for_new_output(before_files, check_interval=10, timeout=3600):
    print(f"Waiting for output (timeout: {timeout}s)...")
    start_time = time.time()

    candidate_file = None

    while time.time() - start_time < timeout:
        time.sleep(check_interval)
        if not os.path.exists(OUTPUT_DIR):
            continue

        current_files = {
            f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".mp4")
        }
        new_files = current_files - before_files

        if new_files:
            print(f"Found {len(new_files)} new file(s): {', '.join(new_files)}")
            full_paths = [os.path.join(OUTPUT_DIR, f) for f in new_files]
            chosen = pick_largest_mp4(full_paths)
            if chosen:
                candidate_file = chosen
                print(f"Selected: {os.path.basename(chosen)}")
                break
            candidate_file = full_paths[0]
            break

    if not candidate_file:
        raise RuntimeError(f"No output file appeared within {timeout}s")

    print(f"Waiting for {os.path.basename(candidate_file)} to complete writing...")
    last_size = -1
    stable_count = 0
    stable_cycles_needed = 3
    min_size = 1024 * 1024  # 1MB minimum

    while time.time() - start_time < timeout:
        try:
            current_size = os.path.getsize(candidate_file)

            if current_size != last_size:
                print(f"File size: {current_size / (1024*1024):.2f} MB")

            if current_size >= min_size:
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= stable_cycles_needed:
                        print(
                            f"File is complete and stable at {current_size / (1024*1024):.2f} MB"
                        )
                        return candidate_file
                else:
                    stable_count = 0
            else:
                stable_count = 0

            last_size = current_size

        except OSError as e:
            print(f"Warning: Could not read file size: {e}")
            last_size = -1

        time.sleep(check_interval)

    raise RuntimeError(f"File did not complete writing within {timeout}s")



# WORKFLOW UTILITIES - MARKED FOR CLEANING UP

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


def get_nodes_map(workflow):
    """
    Return a dict mapping node_id_str -> node_obj regardless of workflow shape.
    Supports either:
      - old format: { "1": {...}, "2": {...} }
      - new format: { "nodes": { "1": {...}, ... }, "links": [...] }
    """
    if (
        isinstance(workflow, dict)
        and "nodes" in workflow
        and isinstance(workflow["nodes"], dict)
    ):
        return workflow["nodes"]
    return workflow


def find_vhs_load_node(nodes_map):
    if "1" in nodes_map:
        n = nodes_map["1"]
        cls = n.get("class_type") or n.get("type") or ""
        if "VHS_LoadVideo" in str(cls):
            return "1"

    for nid, node in nodes_map.items():
        cls = node.get("class_type") or node.get("type") or ""
        if "VHS_LoadVideo" in str(cls):
            return nid
    return None



# IMAGE GENERATION

def generate_image(prompt, workflow_file="image_workflow.json"):
    print("\n" + "=" * 60)
    print("GENERATING INITIAL IMAGE")
    print("=" * 60)
    send_discord("Generating initial image")

    prompt = str(prompt).replace("'", "'").replace("\n", " ").strip()
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

    initial_imgs = set(glob.glob(os.path.join(OUTPUT_DIR, "ComfyUI_*.png")))
    latest = None

    while True:
        imgs = set(glob.glob(os.path.join(OUTPUT_DIR, "ComfyUI_*.png")))
        new_imgs = imgs - initial_imgs
        if new_imgs:
            latest = max(new_imgs, key=os.path.getmtime)
            break
        time.sleep(2)

    print(f"Generated: {os.path.basename(latest)}")
    send_discord("Initial image generated")
    copy_to_input_folder(latest)
    return latest



# VIDEO GENERATION

def generate_video(
    image_path, prompt, workflow_file="video_workflow.json", video_num=1, timeout=300
):
    print(f"\n{'='*60}\nGENERATING VIDEO {video_num}\n{'='*60}")
    send_discord(f"Generating video {video_num}/3")

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

    start_time = time.time()

    existing_files = {
        f: os.path.getmtime(f)
        for f in glob.glob(os.path.join(video_dir, "ComfyUI_*.mp4"))
    }
    latest_video = None

    while time.time() - start_time < timeout:
        all_videos = glob.glob(os.path.join(video_dir, "ComfyUI_*.mp4"))
        for f in all_videos:
            mtime = os.path.getmtime(f)
            if f not in existing_files or mtime > existing_files[f]:
                latest_video = f
                break
        if latest_video:
            break
        time.sleep(2)

    if not latest_video:
        raise RuntimeError(
            f"Video {video_num} generation timeout. No new file detected."
        )

    print(f"Generated: {os.path.basename(latest_video)}")
    send_discord(f"Video {video_num}/3 complete")
    return latest_video



# FRAME EXTRACTION

def extract_last_frame(video_path, output_dir=None):
    print(f"\nExtracting final frame from: {os.path.basename(video_path)}")
    if output_dir is None:
        output_dir = OUTPUT_DIR
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    frame_path = os.path.join(output_dir, f"final_frame_{timestamp}.png")
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.1",
        "-i",
        video_path,
        "-vframes",
        "1",
        "-q:v",
        "2",
        frame_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg extraction failed: {result.stderr}")
    copy_to_input_folder(frame_path)
    return frame_path



# SPLITTING

def get_duration(path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def split_video_half(input_path, out1, out2):
    dur = get_duration(input_path)
    mid = dur / 2.0

    (
        ffmpeg.input(input_path, ss=0, t=mid)
        .output(out1, vcodec="libx264", acodec="aac", r=30, pix_fmt="yuv420p")
        .run(overwrite_output=True)
    )

    (
        ffmpeg.input(input_path, ss=mid)
        .output(out2, vcodec="libx264", acodec="aac", r=30, pix_fmt="yuv420p")
        .run(overwrite_output=True)
    )



# CONCATENATION

def concat_videos(video_list, output_path, timeout=600):
    print("\n" + "=" * 60)
    print("CONCATENATING SEQUENCE")
    print("=" * 60)
    send_discord("Stitching videos together")

    missing = [v for v in video_list if not os.path.exists(v)]
    if missing:
        raise RuntimeError(f"Missing input files: {missing}")

    for v in video_list:
        size = os.path.getsize(v)
        print(f"Input: {v} ({size/1024/1024:.2f} MB)")
        if size == 0:
            raise RuntimeError(f"Input file {v} has size 0 — check it.")

    tmp_dir = os.path.join(os.path.dirname(output_path), "temp_concat")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    temp_files = []
    try:
        for i, v in enumerate(video_list):
            temp_file = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")
            print(f"Re-encoding -> {temp_file}")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                v,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-r",
                "30",
                "-pix_fmt",
                "yuv420p",
                temp_file,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
            if proc.returncode != 0:
                print("ffmpeg stderr:", proc.stderr)
                raise RuntimeError(
                    f"Re-encode failed for {v}: {proc.stderr.splitlines()[-1] if proc.stderr else 'unknown error'}"
                )
            temp_files.append(temp_file)
            print(
                f"Re-encoded: {temp_file} ({os.path.getsize(temp_file)/1024/1024:.2f} MB)"
            )

        list_path = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for tf in temp_files:
                ab = os.path.abspath(tf).replace("\\", "/")
                ab = ab.replace("'", r"'\''")
                f.write(f"file '{ab}'\n")

        print("Concat list written to:", list_path)
        print("Temp files count:", len(temp_files))

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "fast",
            "-c:a",
            "aac",
            output_path,
        ]
        print("Running ffmpeg concat...")
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )

        start = time.time()
        try:
            while True:
                if time.time() - start > timeout:
                    proc.kill()
                    raise RuntimeError(
                        f"ffmpeg concat timed out after {timeout} seconds."
                    )
                line = proc.stderr.readline()
                if line:
                    print(line.strip())
                elif proc.poll() is not None:
                    break
                else:
                    time.sleep(0.1)

            rc = proc.poll()
            if rc != 0:
                remaining = proc.stderr.read()
                raise RuntimeError(
                    f"ffmpeg concat failed (rc={rc}): {remaining.strip()[:1000]}"
                )
            print("ffmpeg concat finished successfully.")
            send_discord("Video stitching complete")
            return output_path

        finally:
            try:
                proc.stdout and proc.stdout.close()
                proc.stderr and proc.stderr.close()
            except Exception:
                pass

    finally:
        try:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
        except Exception as e:
            print("Warning: failed to remove temp dir:", e)



# ADD MUSIC

def add_music(video_path, music_path, output_path):
    print("\n" + "=" * 60)
    print("ADDING MUSIC")
    print("=" * 60)
    send_discord("Adding music")

    if not os.path.exists(music_path):
        print("Music not found, skipping.")
        return video_path

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        music_path,
        "-c:v",
        "copy",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio merge failed: {result.stderr}")

    send_discord("Music added")
    return output_path



# VIDEO UPSCALING VIA COMFYUI

def upscale_video(input_video_path, workflow_file="upscale_workflow.json"):
    print("\n" + "=" * 60)
    print("UPSCALE: STARTING WORKFLOW")
    print("=" * 60)
    send_discord("Starting upscale (this will take a while)")

    copy_to_input_folder(input_video_path)
    video_basename = os.path.basename(input_video_path)

    print(f"Loading workflow from: {os.path.abspath(workflow_file)}")
    with open(workflow_file, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    nodes_map = get_nodes_map(workflow)

    load_node_id = find_vhs_load_node(nodes_map)
    if not load_node_id:
        raise RuntimeError(
            "Workflow has no VHS_LoadVideo node (id '1' or class_type match)."
        )

    load_node = nodes_map[load_node_id]
    if "inputs" not in load_node:
        raise RuntimeError(
            f"VHS_LoadVideo node '{load_node_id}' has no 'inputs' field."
        )

    load_node["inputs"]["video"] = video_basename
    print(f"Set video filename to: {video_basename} on node {load_node_id}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    before_files = set(
        [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".mp4")]
    )
    print(f"Existing output files: {len(before_files)}")

    url = f"{COMFY_URL_BASE}/prompt"
    client_id = f"client_upscale_{random.randint(1000,9999)}"
    data = {"prompt": nodes_map, "client_id": client_id}

    print(f"Sending prompt to ComfyUI (client: {client_id})...")

    try:
        r = requests.post(url, json=data, timeout=30)
        print(f"Response: {r.status_code}")

        if r.status_code == 200:
            response_data = r.json()
            print(f"Response data: {json.dumps(response_data, indent=2)[:500]}")
        else:
            print(f"Error response: {r.text[:500]}")

        r.raise_for_status()

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        raise

    print("\nWaiting for output file...")
    output_path = wait_for_new_output(before_files, timeout=7200)

    file_size = os.path.getsize(output_path)
    print(f"Output file size: {file_size:,} bytes")

    if file_size == 0:
        raise RuntimeError(f"Output file is empty: {output_path}")

    wait_for_file_complete(output_path)

    print(f"\n{'='*60}")
    print(f"UPSCALE COMPLETE: {os.path.basename(output_path)}")
    print(f"{'='*60}")
    send_discord("Upscale complete")
    return output_path

def shutdown_pc(delay_seconds=10):
    """
    Initiates a full shutdown of the Windows PC.

    Args:
        delay_seconds (int): The delay in seconds before the shutdown occurs.
                             Defaults to 0 for immediate shutdown.
    """
    try:
        command = f"shutdown /s /t {delay_seconds}"
        os.system(command)
        print(f"Initiating shutdown in {delay_seconds} seconds...")
    except Exception as e:
        print(f"An error occurred: {e}")



# MAIN PIPELINE

def main():
    start_time = time.time()
    print("\n" + "=" * 60)
    print("COMFYUI SHORT GENERATION + UPLOAD")
    print("=" * 60)

    if not ollama_is_running():
        launch_ollama()
        wait_for_ollama(timeout=600)
    else:
        print("Ollama already running.")
        send_discord("Ollama already running")

    send_discord("Generating video metadata")
    meta = generate_full_video_metadata()
    PROMPTS = meta["prompts"]
    TITLE = meta["title"]
    DESCRIPTION = meta["description"]
    TAGS = meta["tags"]

    if len(PROMPTS) != 4:
        raise RuntimeError("Ollama must return exactly 4 prompts.")

    print("Title:", TITLE)
    print("Description:", DESCRIPTION)
    print("Tags:", TAGS)
    print("Start generation…")
    send_discord(f"Starting generation - Title: {TITLE[:100]}")

    kill_comfy_processes()

    if not find_comfy_port():
        launch_comfyui()
        wait_for_comfyui()
    else:
        print("ComfyUI already running.")
        send_discord("ComfyUI already running")
    start_websocket_monitor()

    current_image = generate_image(PROMPTS[0])

    generated_videos = []
    for i, prompt in enumerate(PROMPTS[1:], start=1):
        v = generate_video(current_image, prompt, video_num=i)
        generated_videos.append(v)
        if i < 3:
            current_image = extract_last_frame(v)

    send_discord("Selecting reaction clips")
    reactions1_dir = os.path.join(os.getcwd(), "reactions", "1")
    reactions2_dir = os.path.join(os.getcwd(), "reactions", "2")

    def list_mp4s(path):
        return [
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.lower().endswith(".mp4")
        ]

    r1_list = list_mp4s(reactions1_dir)
    r2_list = list_mp4s(reactions2_dir)

    reaction1_a = random.choice(r1_list)
    r1_list.remove(reaction1_a)
    reaction1_b = random.choice(r1_list)

    reaction2_a = random.choice(r2_list)
    r2_list.remove(reaction2_a)
    reaction2_b = random.choice(r2_list)

    v1 = generated_videos[0]
    v1_first = os.path.join(PROJECT_OUTPUT, "v1_first_half.mp4")
    v1_second = os.path.join(PROJECT_OUTPUT, "v1_second_half.mp4")
    split_video_half(v1, v1_first, v1_second)

    sequence = [
        v1_first,
        reaction1_a,
        v1_second,
        reaction1_b,
        generated_videos[1],
        reaction2_a,
        generated_videos[2],
        reaction2_b,
    ]

    stitched_path = os.path.join(PROJECT_OUTPUT, "stitched.mp4")
    concat_videos(sequence, stitched_path)

    print("\nDONE. Stitched path (no music yet):", stitched_path)

    # CLEAN SHUTDOWN OF COMFYUI
    print("\n" + "=" * 60)
    print("SHUTTING DOWN COMFYUI FOR UPSCALE RESTART")
    print("=" * 60)
    send_discord("Restarting ComfyUI for upscaling")

    stop_websocket_monitor()

    kill_comfy_processes()
    time.sleep(5)

    # Verify processes are gone
    remaining = kill_comfy_processes()
    if remaining > 0:
        print(f"Warning: {remaining} processes still found, waiting longer...")
        time.sleep(5)
        kill_comfy_processes()

    print("ComfyUI processes cleared.")

    # RESTART COMFYUI FOR UPSCALING
    print("\n" + "=" * 60)
    print("RESTARTING COMFYUI FOR UPSCALING")
    print("=" * 60)

    launch_comfyui()
    wait_for_comfyui(timeout=600)
    start_websocket_monitor()
    print("ComfyUI ready for upscaling.")

    # UPSCALE VIDEO
    upscaled_output = upscale_video(stitched_path)
    print("\nUPSCALED FINAL:", upscaled_output)

    # NOW ADD MUSIC TO UPSCALED VIDEO
    print("\n" + "=" * 60)
    print("ADDING MUSIC TO UPSCALED VIDEO")
    print("=" * 60)

    music_path = os.path.join(os.getcwd(), "song.mp3")
    final_path = os.path.join(
        PROJECT_OUTPUT, f"final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    )
    final_output_with_music = add_music(upscaled_output, music_path, final_path)

    print("\nFINAL OUTPUT WITH MUSIC:", final_output_with_music)

    # UPLOAD
    print("\nUPLOADING TO YOUTUBE…")
    send_discord("Uploading to YouTube")
    upload_short(final_output_with_music, TITLE, DESCRIPTION, TAGS)
    print("Upload complete.")
    send_discord("Upload complete! Video is live")

    # CLEANUP
    kill_comfy_processes()
    shutdown_pc()



# ENTRY

if __name__ == "__main__":
    send_discord("YouTube Shorts pipeline started")
    logging.info("Script started.")
    pipeline_start = time.time()
    try:
        main()
        elapsed = time.time() - pipeline_start
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        send_discord(f"Pipeline completed successfully in {hours}h {minutes}m {seconds}s")
    except Exception as e:
        error_msg = str(e)[:1000]
        logging.error(f"ERROR: {e}", exc_info=True)
        send_discord(f"ERROR: {error_msg}")
        print("\nERROR:", e)
        import traceback

        traceback.print_exc()
    logging.info("Script finished.")