#!/usr/bin/env python3
"""Send the archived production screenshot via Microsoft Graph application mail."""
import base64
import json
import os
from pathlib import Path
import requests

tenant = os.environ["MS_TENANT_ID"]
client = os.environ["MS_CLIENT_ID"]
secret = os.environ["MS_CLIENT_SECRET"]
sender = os.environ["MS_SENDER_EMAIL"]
recipient = "tim@ksimetals.com"
image_path = Path(os.environ["SCREENSHOT_PATH"])
if not image_path.is_file():
    raise SystemExit(f"Screenshot missing: {image_path}")
if image_path.suffix.lower() != ".png":
    raise SystemExit("Expected a PNG screenshot")
date = image_path.stem
token_response = requests.post(
    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    data={"client_id": client, "client_secret": secret,
          "scope": "https://graph.microsoft.com/.default",
          "grant_type": "client_credentials"}, timeout=30)
token_response.raise_for_status()
token = token_response.json()["access_token"]
message = {
    "message": {
        "subject": f"KSI Metals End-of-Day Production - {date}",
        "body": {"contentType": "Text", "content":
                 f"Attached is the KSI Metals production board screenshot for {date} (4:00 PM Arizona scheduled capture)."},
        "toRecipients": [{"emailAddress": {"address": recipient}}],
        "attachments": [{"@odata.type": "#microsoft.graph.fileAttachment",
                         "name": image_path.name, "contentType": "image/png",
                         "contentBytes": base64.b64encode(image_path.read_bytes()).decode("ascii")}]
    },
    "saveToSentItems": True
}
response = requests.post(
    f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    data=json.dumps(message), timeout=60)
response.raise_for_status()
print(f"Microsoft Graph accepted end-of-day report to {recipient} for {date}")
