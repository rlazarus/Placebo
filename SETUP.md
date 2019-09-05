Full setup instructions coming soon.

### Environment variables

Variable | Contents
--- | ---
DATABASE_URL | Heroku-provided `postgres://` URL.
PLACEBO_GOOGLE_CLIENT_ID | OAuth client ID for Google APIs, from the [Google API console].
PLACEBO_GOOGLE_CLIENT_SECRET | OAuth client secret for Google APIs.
PLACEBO_SLACK_TOKEN | OAuth Access Token for the Slack API, from the app's OAuth & Permissions page.
PLACEBO_PUZZLE_LIST_SPREADSHEET_ID | Spreadsheet ID for the puzzle list. Take this from the URL: it comes after `/spreadsheets/d/` and before `/edit`.
PLACEBO_PUZZLE_LIST_SHEET_ID | _Sheet_ ID for the puzzle list. Take this from the URL: it comes after `#gid=` and it's numeric. In Google Sheets parlance, a _spreadsheet_ is the entire sharable document, made up of one or more _sheets_, which are the tabs at the bottom.
PLACEBO_PUZZLES_FOLDER_ID | ID for the Google Drive folder containing puzzles in progress. Take this from the URL: it comes after `/folders/`.
PLACEBO_SOLVED_FOLDER_ID | ID for the Google Drive folder containing solved puzzles. Find it the same way.
PLACEBO_UNLOCKS_CHANNEL_ID | Channel ID for the Slack channel where newly unlocked puzzles will be announced. Find it from the URL (open Slack in your web browser, or right-click the channel in the desktop app and choose "Open Link"): it comes after `/messages/`. It's alphanumeric and starts with a C.

[Google API console]: https://console.developers.google.com/apis/credentials