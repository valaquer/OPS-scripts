#!/usr/bin/env python3
"""Bulk delete all files from Google Drive. One-time cleanup tool."""

import os
import sys
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = '/tmp/gdrive-cleanup-token.json'
CLIENT_CONFIG = {
    "installed": {
        "client_id": "1234567890.apps.googleusercontent.com",
        "client_secret": "",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"]
    }
}

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
        creds = flow.run_local_server(port=0, open_browser=False)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)


def list_all_files(service):
    files = []
    page_token = None
    while True:
        results = service.files().list(
            pageSize=1000,
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
            q="'me' in owners"
        ).execute()
        batch = results.get('files', [])
        files.extend(batch)
        print(f"  Listed {len(files)} files so far...", file=sys.stderr)
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return files


def delete_files(service, files):
    deleted = 0
    errors = 0
    for f in files:
        try:
            service.files().delete(fileId=f['id']).execute()
            deleted += 1
            if deleted % 50 == 0:
                print(f"  Deleted {deleted}/{len(files)}...", file=sys.stderr)
        except HttpError as e:
            errors += 1
            if errors <= 5:
                print(f"  Error deleting {f['name']}: {e}", file=sys.stderr)
    return deleted, errors


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--count':
        service = get_service()
        files = list_all_files(service)
        print(f"\n{len(files)} files found on Drive.")
        return

    service = get_service()
    print("Listing all files...", file=sys.stderr)
    files = list_all_files(service)
    print(f"\nFound {len(files)} files. Deleting all of them.", file=sys.stderr)

    if not files:
        print("Nothing to delete.")
        return

    deleted, errors = delete_files(service, files)
    print(f"\nDone. Deleted {deleted}, errors {errors}.")

    # Empty trash
    try:
        service.files().emptyTrash().execute()
        print("Trash emptied.")
    except HttpError as e:
        print(f"Empty trash failed: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
