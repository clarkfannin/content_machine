import os
import json
from glob import glob
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth.exceptions

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
PROJECT_OUTPUT = os.path.join(os.getcwd(), "outputs")  # matches main.py
COMFY_OUTPUT = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "ComfyUI",
    "output"
)

    

def get_youtube():
    creds = None
    if os.path.exists("token.json"):
        with open("token.json", "r") as f:
            creds = google.oauth2.credentials.Credentials.from_authorized_user_info(json.load(f), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except google.auth.exceptions.RefreshError:
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=8080)

        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def upload_short(video_path, title, description="", tags=None):
    youtube = get_youtube()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or ["shorts"],
            "categoryId": "22"  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",   # or "private" during testing
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    print("Upload complete:", response["id"])
    return response["id"]

def get_latest_upscaled_video():
    files = glob(os.path.join(COMFY_OUTPUT, "SEEDVR_*.mp4"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


if __name__ == "__main__":
    from prompts import generate_full_video_metadata
    # Generate video metadata from Ollama
    metadata = generate_full_video_metadata()
    video_path = get_latest_upscaled_video()

    print(f"Uploading latest video: {os.path.basename(video_path)}")
    print(f"Title: {metadata['title']}")
    print(f"Description: {metadata['description']}")
    print(f"Tags: {metadata['tags']}")

    try:
        upload_short(
            video_path,
            title=metadata['title'],
            description=metadata['description'],
            tags=metadata['tags']
        )
    except Exception as e:
        print("Upload failed:", e)
