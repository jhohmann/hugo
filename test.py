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

service = build("calendar", "v3", credentials=credentials)

events = service.events().list(
    calendarId="primary",
    maxResults=10,
    singleEvents=True,
    orderBy="startTime"
).execute()

for event in events.get("items", []):
    print(event.get("summary"))