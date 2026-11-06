"""Manual legacy OAuth probe; run explicitly from the repository root.

Requires google-auth-oauthlib and google-api-python-client separately.
Reads credentials.json, writes token.json and lists event titles.
The application itself uses its database-backed OAuth flow instead.
"""


def main():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json", SCOPES
    )

    credentials = flow.run_local_server(

        host="localhost",
        port=8765,
        open_browser=False
    )

    with open("token.json", "w", encoding="utf-8") as f:
        f.write(credentials.to_json())

    service = build("calendar", "v3", credentials=credentials)

    events = service.events().list(
        calendarId="primary",
        maxResults=10,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    for event in events.get("items", []):
        print(event.get("summary"))


if __name__ == "__main__":
    main()
