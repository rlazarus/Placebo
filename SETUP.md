Full setup instructions coming soon.

### Environment variables

Variable | Contents
--- | ---
DATABASE_URL | Heroku-provided `postgres://` URL.
PLACEBO_DEBUG_LOGS | If set to 1, the minimum logging level is set to "debug," which includes e.g. request and response payloads on API calls. If missing or set to any other value, the logging level is "info."
PLACEBO_GOOGLE_CLIENT_SECRETS | OAuth client secret for Google APIs, in JSON format. Download `client_secret.json` from the [Google API console], then paste the contents into this variable.
PLACEBO_PUZZLE_LIST_SPREADSHEET_ID<sup>†</sup> | Spreadsheet ID for the puzzle list. Take this from the URL: it comes after `/spreadsheets/d/` and before `/edit`.
PLACEBO_PUZZLE_LIST_SHEET_ID<sup>†</sup> | _Sheet_ ID for the puzzle list. Take this from the URL: it comes after `#gid=` and it's numeric. In Google Sheets parlance, a _spreadsheet_ is the entire sharable document, made up of one or more _sheets_, which are the tabs at the bottom.
PLACEBO_PUZZLES_FOLDER_ID<sup>†</sup> | ID for the Google Drive folder containing puzzles in progress. Take this from the URL: it comes after `/folders/`.
PLACEBO_PUZZLE_TEMPLATE_ID | Spreadsheet ID for a blank document to be copied for each new puzzle.
PLACEBO_SLACK_TOKEN | OAuth Access Token for the Slack API, from the app's OAuth & Permissions page.
PLACEBO_SOLVED_FOLDER_ID<sup>†</sup> | ID for the Google Drive folder containing solved puzzles.
PLACEBO_TESTING | For every variable marked with a dagger (†) you can set a corresponding `_TESTING` variable; for example, `PLACEBO_UNLOCKS_CHANNEL_ID` and `PLACEBO_UNLOCKS_CHANNEL_ID_TESTING`. If `PLACEBO_TESTING` is set to 1, these test variants are used and the non-test variables are ignored.
PLACEBO_UNLOCKS_CHANNEL_ID<sup>†</sup> | Channel ID for the Slack channel where newly unlocked puzzles will be announced. Find it from the URL (open Slack in your web browser, or right-click the channel in the desktop app and choose "Copy Link"): it comes after `/messages/`. It's alphanumeric and starts with a C.

<sup>†</sup> See PLACEBO_TESTING.

[Google API console]: https://console.developers.google.com/apis/credentials