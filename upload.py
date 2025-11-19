from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth.exceptions
import os, json

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

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
            print(f"Upload: {int(status.progress() * 100)}%")

    print("Uploaded:", response["id"])
    return response["id"]


if __name__ == "__main__":
    print("Running upload.py…")

    # test video path — pick anything local
    test_video = "final.mp4"

    # Just test OAuth & basic API call (no upload yet)
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    print("Starting OAuth…")
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=8080)
    print("OAuth success")

    youtube = build("youtube", "v3", credentials=creds)
    print("YouTube client ready")

    # Now test upload with dry run
    print("Attempting upload…")
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": "Test Upload Short",
                    "description": "Testing automation",
                    "tags": ["shorts"],
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": "private"
                }
            },
            media_body=test_video
        )
        response = request.execute()
        print("Upload response:", response)
    except Exception as e:
        print("Upload failed:", e)
