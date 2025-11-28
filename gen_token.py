# One-time script to generate token for YouTube API access

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=8080)

with open("token.json", "w") as f:
    f.write(creds.to_json())

print("token.json created successfully!")
