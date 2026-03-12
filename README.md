# UKG to Google Calendar Sync

An automated Python script that fetches work schedules from **Kronos/UKG** and syncs them directly to **Google Calendar**.

## ⚙️ Features
* Runs daily via GitHub Actions.
* Handles Duo 2FA.
* Manages daylight savings automatically
* Automatically removes cancelled shifts or shifts from the previous month.
* Fetches from the 1st of the current month to 2 weeks into the future.
* Uses Playwright to navigate the UKG SSO login portal.

## 🛠️ Setup & Installation

### 1. Google Calendar API
1. Enable the Google Calendar API in the [Google Cloud Console](https://console.cloud.google.com/).
2. Create **OAuth 2.0 Credentials** and download the `credentials.json`.
3. Run the script locally once to generate a `token.json` file.

### 2. GitHub Secrets
To run this via GitHub Actions, add the following **Repository Secrets** in your GitHub settings (`Settings > Secrets and variables > Actions`):

| Secret | Description |
| :--- | :--- |
| `UKG_EMAIL` | Your UKG login email. |
| `UKG_PASSWORD` | Your UKG login password. |
| `UKG_LOGIN_URL` | The SSO login portal URL for your company. |
| `UKG_API_URL` | The specific UKG internal API endpoint for schedule data. |
| `GOOGLE_WORK_CALENDAR_ID` | The ID of the specific Google Calendar (e.g., `example@group.calendar.google.com`). |
| `CREDENTIALS_JSON` | The full text content of your `credentials.json`. |
| `TOKEN_JSON` | The full text content of your `token.json`. |

### 3. YML File
The script is configured to run daily at **3:00 PM PDT (22:00 UTC)**. This can be changed in `/.github/workflows/daily_sync.yml`.

***
> **Note:** Because UKG uses Duo 2FA, you'll have to approve the push notification manually.
> This project is for personal use only. It is not affiliated with, maintained by, or supported by UKG or Google.
