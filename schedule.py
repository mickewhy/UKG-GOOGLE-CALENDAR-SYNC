import json
import time
import os
import zoneinfo
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

UKG_EMAIL = os.getenv("UKG_EMAIL")
UKG_PASSWORD = os.getenv("UKG_PASSWORD")
UKG_LOGIN_URL = os.getenv("UKG_LOGIN_URL")
UKG_API_URL = os.getenv("UKG_API_URL")

GOOGLE_WORK_CALENDAR_ID = os.getenv("GOOGLE_WORK_CALENDAR_ID")

CALENDAR_TAG = "UKG_WORK_SHIFT"  # Used in description to identify events
TIMEZONE = "America/Los_Angeles"
TIMEOUT = int(os.getenv("TIMEOUT", 60000))  # milliseconds

# TEXT_FILE_PATH = "schedule_output.txt"
# CALENDAR_COLOR_ID = '10' # Basil


def login_to_ukg(page):
    """Logs into UKG SSO."""
    print(f"🌐 Navigating to {UKG_LOGIN_URL}...")
    page.goto(UKG_LOGIN_URL)

    # --- EMAIL ---
    email_field = page.get_by_label("Email Address")
    email_field.click()
    print("📧 Typing email...")
    email_field.press_sequentially(UKG_EMAIL, delay=50)
    page.keyboard.press("Tab")

    next_button = page.get_by_role("button", name="Next")
    next_button.wait_for(state="visible", timeout=TIMEOUT)
    time.sleep(1)
    next_button.click()

    # --- PASSWORD ---
    print("⏳ Waiting for password field...")
    password_field = page.locator('input[name="password"]')
    password_field.wait_for(state="visible", timeout=TIMEOUT)

    print("⌨️ Entering password...")
    password_field.fill(UKG_PASSWORD)
    page.keyboard.press("Enter")

def handle_security_prompts(page):
    """Waits for Duo 2FA and handles 'Trust this device' prompt."""
    print("📱 Waiting for DUO 2FA...")
    time.sleep(5)

    try:
        # trust_button = page.locator("#trust-browser-button")
        # print("🔍 Scanning for 'Trust this device' prompt...")
        # trust_button.wait_for(state="visible", timeout=TIMEOUT)

        page.get_by_role("heading", name="Is this your device?").wait_for(state="visible", timeout=TIMEOUT)
        trust_button = page.get_by_role("button", name="Yes, this is my device")

        trust_button.click(force=True)
        print("🖱️ Clicked 'Yes, this is my device'.")
    except Exception:
        print("⏩ No 'Trust' prompt detected. Continuing...")

    try:
        print("🏠 Waiting for dashboard to load...")
        page.wait_for_url("**/wfd/home**", timeout=TIMEOUT)
        print("✅ Login Successful!")
        return True
    except Exception:
        print(f"❌ Timed out. Current URL is: {page.url}")
        return False

def fetch_schedule_data(context, page):
    """Extracts data from the 1st of the current month to 2 weeks ahead of today."""
    print("📥 Requesting schedule data...")

    now = datetime.now()
    start_date = now.replace(day=1).strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    print(f"📅 Fetching range: {start_date} to {end_date}")

    cookies = context.cookies()
    xsrf_token = next((c["value"] for c in cookies if c["name"] == "XSRF-TOKEN"), None)

    payload = {
        "data": {
            "calendarConfigId": 3000002,
            "includedEntities": [
                "entity.paycodeedit",
                "entity.transfershift",
                "entity.regularshift",
                "entity.timeoffrequest",
            ],
            "dateSpan": {"start": start_date, "end": end_date},
        }
    }

    response = page.request.post(
        UKG_API_URL,
        data=payload,
        headers={
            "x-xsrf-token": xsrf_token,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )

    if response.status == 200:
        print(f"📥 API Request successful!")
        return response.json()
    else:
        print(f"❌ API Request failed: {response.status}")
        print(response.text())
        return None

def run_sync():
    """Main function, calls all the steps in sequence."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # Set to False for debugging, True for GitHub Actions
        context = browser.new_context()
        page = context.new_page()

        login_to_ukg(page)

        schedule_json = None
        if handle_security_prompts(page):
            schedule_json = fetch_schedule_data(context, page)

        print("\n💻 Closing browser...")
        # time.sleep(5)
        browser.close()
        return schedule_json

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json", ["https://www.googleapis.com/auth/calendar"]
        )
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing Google Token...")
            creds.refresh(Request())
        else:
            if os.getenv("GITHUB_ACTIONS"):
                raise Exception("❌ Google Token expired and cannot be refreshed in GitHub Actions. Run the script locally once and update the TOKEN_JSON secret.")
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", ["https://www.googleapis.com/auth/calendar"]
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

def sanitize_ukg_data(raw_json):
    """Extracts label, start, and end from regular and transfer shifts."""
    clean_shifts = []

    regular = raw_json.get("regularShifts", [])
    transfer = raw_json.get("transferShifts", [])
    all_shifts = regular + transfer

    for shift in all_shifts:
        start = shift.get("startDateTime")
        end = shift.get("endDateTime")
        label = shift.get("label", "Work Shift")

        if start and end:
            clean_shifts.append({"summary": label, "start": start, "end": end})

    return clean_shifts

def sync_to_google_calendar(shifts):
    service = get_calendar_service()

    if not shifts:
        print("❌ No shifts found to sync.")
        return

    # pst = timezone(timedelta(hours=-8))

    now = datetime.now()
    first_of_this_month = now.replace(day=1)
    last_day_of_last_month = first_of_this_month - timedelta(days=1)
    start_of_last_month = last_day_of_last_month.replace(day=1, hour=0, minute=0, second=0)

    all_starts = sorted([s["start"] for s in shifts])
    all_ends = sorted([s["end"] for s in shifts])

    # time_min = all_starts[0] + "Z"
    # time_max = all_ends[-1] + "Z"

    # time_min = datetime.fromisoformat(all_starts[0]).replace(tzinfo=pst).isoformat()
    # time_min = start_of_last_month.replace(tzinfo=pst).isoformat()
    # time_max = datetime.fromisoformat(all_ends[-1]).replace(tzinfo=pst).isoformat()

    # Calculate timezone to account for Feb 28th and daylight savings
    tz = zoneinfo.ZoneInfo(TIMEZONE)
    current_offset = tz.utcoffset(datetime.now()).total_seconds() / 3600
    local_tz = timezone(timedelta(hours=current_offset))
    
    time_min = start_of_last_month.replace(tzinfo=local_tz).isoformat()
    time_max = datetime.fromisoformat(all_ends[-1]).replace(tzinfo=local_tz).isoformat()

    print(f"🔍 Checking calendar from {time_min} to {time_max}...")

    existing_events = (
        service.events()
        .list(
            calendarId=GOOGLE_WORK_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            q=CALENDAR_TAG
        )
        .execute()
    ).get("items", [])

    shifts_to_add = shifts.copy()

    for event in existing_events:
        if CALENDAR_TAG not in event.get("description", ""):
            continue

        g_summary = event.get("summary")
        g_start = event.get("start").get("dateTime")
        g_end = event.get("end").get("dateTime")

        match_found = False
        for shift in shifts_to_add:
            if (g_summary == shift["summary"] and 
                g_start.startswith(shift["start"]) and 
                g_end.startswith(shift["end"])):
                
                print(f"✅ Already Synced: {shift['summary']} | {shift['start']}")
                shifts_to_add.remove(shift)
                match_found = True
                break
        
        if not match_found:
            print(f"🗑️ {g_summary} | {g_start}")
            service.events().delete(
                calendarId=GOOGLE_WORK_CALENDAR_ID, eventId=event["id"]
            ).execute()

    if not shifts_to_add:
        print("✅ No new shifts to add.")
        return

    for shift in shifts_to_add:
        print(f"➕ {shift['summary']} | {shift['start']}")
        event_body = {
            "summary": shift["summary"],
            "location": "California Academy of Sciences, 55 Music Concourse Dr, San Francisco, CA 94118",
            "description": f"Automated Sync | {CALENDAR_TAG}",
            "start": {"dateTime": shift["start"], "timeZone": TIMEZONE},
            "end": {"dateTime": shift["end"], "timeZone": TIMEZONE},
        }
        service.events().insert(
            calendarId=GOOGLE_WORK_CALENDAR_ID, body=event_body
        ).execute()
    
def main(json_data):
    # Pass JSON to this function later
    # For now, read from text file

    # if not os.path.exists(TEXT_FILE_PATH):
    #     print(f"❌ Error: {TEXT_FILE_PATH} not found.")
    #     return

    # print(f"📖 Reading {TEXT_FILE_PATH}...")
    # with open(TEXT_FILE_PATH, "r") as f:
    #     try:
    #         raw_data = json.load(f)
    #     except json.JSONDecodeError:
    #         print("❌ Error: Failed to parse JSON. Check the file content.")
    #         return

    # Sanitize
    processed_shifts = sanitize_ukg_data(json_data)
    print(f"✅ Found {len(processed_shifts)} shifts to sync.")

    # Push to Calendar
    sync_to_google_calendar(processed_shifts)
    print("\n📆 Calendar sync complete!")


if __name__ == "__main__":
    json_data = run_sync()
    if json_data:
        main(json_data)
