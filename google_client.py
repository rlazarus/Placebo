import json
import logging
import os
import pprint
import re
import string
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeVar, Union

import httplib2
import psycopg2
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import Flow
from googleapiclient import discovery, http
from googleapiclient.http import DEFAULT_HTTP_TIMEOUT_SEC
from psycopg2 import extensions

import util

log = logging.getLogger('placebo.google_client')

# Full drive access for dev.
SCOPE = 'https://www.googleapis.com/auth/drive'
USER = 'controlgroup.mh@gmail.com'

NAME_CHARACTERS = string.ascii_lowercase + string.digits + '_'

CHANNEL_PATTERNS = [
    re.compile('controlgroup.slack.com/messages/([a-z0-9_-]+)'),
    re.compile('#([a-z0-9_-]+)'),
]
FILE_ID_PATTERN = re.compile('/d/([a-zA-Z0-9-_]+)')

# The light-gray background color used for metas on the tracking spreadsheet.
META_BACKGROUND = util.Color(red=0.85, green=0.85, blue=0.85)
# The white background color used for everything else.
PLAIN_BACKGROUND = util.Color(red=1.0, green=1.0, blue=1.0)

# Some presets to use for round colors if QMs don't pick specific ones. (These are pulled from the
# Sheets UI, and shuffled to put relatively high-contrast pairs next to each other.)
ROUND_COLORS = [
    util.Color(red=0.87, green=0.49, blue=0.42),  # light red berry 2
    util.Color(red=0.81, green=0.89, blue=0.95),  # light blue 3
    util.Color(red=0.71, green=0.84, blue=0.66),  # light green 2
    util.Color(red=0.71, green=0.65, blue=0.84),  # light purple 2
    util.Color(red=0.98, green=0.8, blue=0.61),  # light orange 2
    util.Color(red=0.84, green=0.65, blue=0.74),  # light magenta 2
    util.Color(red=0.92, green=0.6, blue=0.6),  # light red 2
    util.Color(red=1.0, green=0.9, blue=0.6),  # light yellow 2
    util.Color(red=0.85, green=0.92, blue=0.83),  # light green 3
    util.Color(red=0.64, green=0.76, blue=0.96),  # light cornflower blue 2
]

T = TypeVar('T')

# This is a little disappointing, but we only have two other options: a recursive definition, like
#   Response = Dict[str, Union[str, int, Response, List[Response]]]
# which isn't yet supported by mypy and generates spurious type errors, or a TypedDict, which would
# have to be spelled out exhaustively and isn't worth the bulk.
Response = Dict[str, Any]


class LoggedOutClient:
    def __init__(self):
        self.flow = Flow.from_client_config(
            json.loads(os.environ['PLACEBO_GOOGLE_CLIENT_SECRETS']),
            scopes=[SCOPE], redirect_uri='https://control-group.herokuapp.com/google_oauth')

    @property
    def sheets(self):
        raise TypeError('Not logged in.')

    @property
    def files(self):
        raise TypeError('Not logged in.')

    def save_credentials(self) -> None:
        raise TypeError('Not logged in.')

    def log_and_send(self, desc: str, request: http.HttpRequest) -> Response:
        raise TypeError('Not logged in.')


class LoggedInClient:
    def __init__(self, credentials: Credentials, conn: extensions.connection):
        self.credentials = credentials
        self.conn = conn
        # This is roughly googleapiclient.http.build_http(), but with a cache.
        http = httplib2.Http(cache='.cache', timeout=DEFAULT_HTTP_TIMEOUT_SEC)
        http.redirect_codes -= {308}
        # And this is roughly what discovery.build(... credentials=credentials) does, but with our
        # cache-enabled http.
        auth_http = AuthorizedHttp(credentials=credentials, http=http)
        self.sheets = discovery.build('sheets', 'v4', http=auth_http).spreadsheets()
        self.files = discovery.build('drive', 'v3', http=auth_http).files()

    @classmethod
    def from_loading_credentials(cls, conn: extensions.connection) -> Optional['LoggedInClient']:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM credentials WHERE name = 'google_credentials';")
        row = cursor.fetchone()
        if not row:
            return None
        creds_json = row[0]
        credentials = Credentials(**json.loads(creds_json))
        return LoggedInClient(credentials, conn)

    def save_credentials(self) -> None:
        creds_json = json.dumps(
            {name: getattr(self.credentials, name) for name in
             ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']})
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO credentials (name, value) VALUES ('google_credentials', %s) "
            "ON CONFLICT (name) DO UPDATE SET value = %s;", (creds_json, creds_json))
        self.conn.commit()

    def log_and_send(self, desc: str, request: http.HttpRequest) -> Response:
        log.info(desc)
        log.debug(pprint.pformat(request))
        response = request.execute()
        log.debug(pprint.pformat(response))
        self.save_credentials()  # They may have been refreshed in the process.
        return response

    @property
    def flow(self) -> Flow:
        raise TypeError('Already logged in.')


Row = Tuple[str, str, str, str, str, str, str]


class Google:
    def __init__(self):
        self.client: Union[LoggedInClient, LoggedOutClient] = LoggedOutClient()
        self.conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')

        # Here and throughout, a "spreadsheet" is the entire sharable unit, and a "sheet" is the
        # page (tabs at the bottom). This is kind of unfortunate but matches the names used in
        # Google Sheets and its API.
        if os.environ.get('PLACEBO_TESTING') == '1':
            self.puzzle_list_spreadsheet_id = os.environ[
                'PLACEBO_PUZZLE_LIST_SPREADSHEET_ID_TESTING']
            self.puzzle_list_sheet_id = os.environ['PLACEBO_PUZZLE_LIST_SHEET_ID_TESTING']
            self.puzzles_folder_id = os.environ['PLACEBO_PUZZLES_FOLDER_ID_TESTING']
            self.solved_folder_id = os.environ['PLACEBO_SOLVED_FOLDER_ID_TESTING']
        else:
            self.puzzle_list_spreadsheet_id = os.environ['PLACEBO_PUZZLE_LIST_SPREADSHEET_ID']
            self.puzzle_list_sheet_id = os.environ['PLACEBO_PUZZLE_LIST_SHEET_ID']
            self.puzzles_folder_id = os.environ['PLACEBO_PUZZLES_FOLDER_ID']
            self.solved_folder_id = os.environ['PLACEBO_SOLVED_FOLDER_ID']
        self.puzzle_template_id = os.environ['PLACEBO_PUZZLE_TEMPLATE_ID']

    @property
    def sheets(self):
        return self.client.sheets

    @property
    def files(self):
        return self.client.files

    def start_oauth_if_necessary(self) -> Optional[str]:
        maybe_client = LoggedInClient.from_loading_credentials(self.conn)
        if maybe_client:
            self.client = maybe_client
            log.info('Google OAuth creds already present.')
            return None
        log.info('Starting the Google OAuth flow...')
        authorization_url, _ = self.client.flow.authorization_url(
            access_type='offline', include_granted_scopes='true', login_hint=USER)
        return authorization_url

    def finish_oauth(self, callback_url: str) -> None:
        self.client.flow.fetch_token(authorization_response=callback_url)
        self.client = LoggedInClient(self.client.flow.credentials, self.conn)
        self.client.save_credentials()

    def create_puzzle_spreadsheet(self, puzzle_name: str) -> str:
        request = self.client.files.copy(fileId=self.puzzle_template_id, body={
            'name': puzzle_name,
            'parents': [self.puzzles_folder_id],
        })
        response = self.client.log_and_send('Creating spreadsheet', request)
        doc_id = response['id']
        url = f'https://docs.google.com/spreadsheets/d/{doc_id}/edit'
        return url

    def add_row(self, round_name: str, puzzle_name: str, priority: str, puzzle_url: str,
                channel: str, round_color: Optional[util.Color]) -> util.Color:
        assert priority in {'-', 'L', 'M', 'H'}
        assert not channel.startswith('#')
        slack_link = channel_to_link(channel)
        cell_values = (round_name, puzzle_name, priority, puzzle_url, '🤖 One sec...', slack_link,
                       'Not started')
        round_color = self._add_row(cell_values, round_color)
        return round_color

    def add_empty_row(self, round_name: str, round_color: Optional[util.Color]) -> util.Color:
        cell_values = (round_name, '', '', '', '', '', '')
        round_color = self._add_row(cell_values, round_color)
        return round_color

    def _add_row(self, cell_values: Row, round_color: util.Color) -> util.Color:
        # Find the last row that matches this round; we'll insert below it.
        request = self.sheets.get(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                  ranges='Puzzle List!A:A', includeGridData=True)
        response = self.client.log_and_send('Looking up the Round column', request)
        rows = response['sheets'][0]['data'][0]['rowData']
        round_names = [(row['values'][0].get('formattedValue', '') if 'values' in row else '')
                       for row in rows]
        canon_rounds = [canonicalize(r) for r in round_names]
        round_name = cell_values[0]
        if canonicalize(round_name) in canon_rounds:
            row_index = last_index(canon_rounds, canonicalize(round_name)) + 1
            if not round_color:
                # No color ought to be given for a round we've already seen... but if one *is*
                # given, we won't overwrite it.
                cell = rows[row_index - 1]['values'][0]
                round_color = util.Color.from_dict(cell['effectiveFormat']['backgroundColor'])
            new_round = False
        else:
            # If we've never seen this round before, insert at the bottom of the table. That is,
            # before the first blank cell not in the header.
            try:
                row_index = round_names.index('', 2)
            except ValueError:
                # There are no blank round cells after the header? Insert it right above the Event
                # puzzles.
                try:
                    row_index = round_names.index('Event')
                except ValueError:
                    # No blank round cells *and* no Event puzzles? Okay... just add it at the end.
                    row_index = len(round_names)
            # If it's a new round, and no color was given, pick a preset color for the unlock.
            if not round_color:
                round_color = ROUND_COLORS[len(set(canon_rounds)) % len(ROUND_COLORS)]
            new_round = True

        # First insert a new row at that location...
        requests = [{
            'insertDimension': {
                'range': {
                    'sheetId': self.puzzle_list_sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': row_index,
                    'endIndex': row_index + 1,
                },
                'inheritFromBefore': True,
            }
        }]
        # ... then update the values.
        requests.append({
            'updateCells': {
                'rows': [row_data(cell_values)],
                'fields': 'userEnteredValue',
                'start': {
                    'sheetId': self.puzzle_list_sheet_id,
                    'rowIndex': row_index,
                    'columnIndex': 0,
                },
            },
        })

        if new_round:
            # We're adding a new round; draw a line over it and overwrite the round and meta color.
            requests.extend([
                {
                    'updateBorders': {
                        'range': {
                            'sheetId': self.puzzle_list_sheet_id,
                            'startRowIndex': row_index,
                            'endRowIndex': row_index + 1,
                        },
                        'top': {
                            'style': 'SOLID_THICK',
                            'color': {'red': 0.0, 'green': 0.0, 'blue': 0.0},
                        }
                    }
                },
                {
                    'updateCells': {
                        'rows': [{
                            'values': [{'userEnteredFormat': {'backgroundColor':
                                                                  round_color.to_dict()}},
                                       {'userEnteredFormat': {'backgroundColor':
                                                                  META_BACKGROUND.to_dict()}}]
                        }],
                        'fields': 'userEnteredFormat.backgroundColor',
                        'range': {
                            'sheetId': self.puzzle_list_sheet_id,
                            'startRowIndex': row_index,
                            'endRowIndex': row_index + 1,
                            'startColumnIndex': 0,
                            'endColumnIndex': 2,
                        },
                    }
                }
            ])
        else:
            # Otherwise, remove the line and set the color to white, since we don't want to inherit
            # them from a meta above.
            requests.extend([
                {
                    'updateBorders': {
                        'range': {
                            'sheetId': self.puzzle_list_sheet_id,
                            'startRowIndex': row_index,
                            'endRowIndex': row_index + 1,
                        },
                        'top': {
                            'style': 'NONE',
                        }
                    }
                },
                {
                    'updateCells': {
                        'rows': [{
                            'values': [{'userEnteredFormat': {'backgroundColor':
                                                                  PLAIN_BACKGROUND.to_dict()}}]
                        }],
                        'fields': 'userEnteredFormat.backgroundColor',
                        'range': {
                            'sheetId': self.puzzle_list_sheet_id,
                            'startRowIndex': row_index,
                            'endRowIndex': row_index + 1,
                            'startColumnIndex': 1,
                            'endColumnIndex': 2,
                        },
                    }
                }
            ])

        batch_request = self.sheets.batchUpdate(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                                body={'requests': requests})
        self.client.log_and_send('Adding row to tracker', batch_request)

        return round_color

    def set_doc_url(self, puzzle_name: str, doc_url: str) -> None:
        lookup = self.lookup(puzzle_name)
        if lookup is None:
            raise KeyError(f'Puzzle "{puzzle_name}" not found.')
        row_index, doc_url_was, _ = lookup
        if 'http' in doc_url_was:
            raise UrlConflictError(found_url=doc_url_was, discarded_url=doc_url)

        requests = [{
            'updateCells': {
                'rows': [row_data([doc_url])],
                'fields': 'userEnteredValue',
                'start': {
                    'sheetId': self.puzzle_list_sheet_id,
                    'rowIndex': row_index,
                    'columnIndex': 4
                }
            }
        }]
        batch_request = self.sheets.batchUpdate(
            spreadsheetId=self.puzzle_list_spreadsheet_id,
            body={'requests': requests})
        self.client.log_and_send('Updating tracker row', batch_request)

    def exists(self, puzzle_name: str) -> bool:
        request = self.sheets.values().get(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                           range='Puzzle List!B:B', majorDimension='COLUMNS')
        response = self.client.log_and_send('Checking tracking sheet for puzzle', request)
        puzzle_name = canonicalize(puzzle_name)
        column = response['values'][0]
        for cell in column:
            if puzzle_name in canonicalize(cell):
                return True
        return False

    def lookup(self, puzzle_name: str) -> Optional[Tuple[int, str, Optional[str]]]:
        request = self.sheets.values().get(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                           range='Puzzle List!A:G')
        response = self.client.log_and_send('Fetching tracking sheet', request)
        puzzle_name = canonicalize(puzzle_name)
        matching_rows = []
        for row_index, row in enumerate(response['values']):
            if len(row) > 5 and puzzle_name in canonicalize(row[1]):
                matching_rows.append((row_index, row[4], link_to_channel(row[5])))
        if not matching_rows:
            return None
        elif len(matching_rows) == 1:
            return matching_rows[0]
        else:
            raise KeyError(f'{len(matching_rows)} rows matching {puzzle_name}')

    def all_rounds(self) -> List[str]:
        request = self.sheets.values().get(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                           range='Puzzle List!A3:A', majorDimension='COLUMNS')
        response = self.client.log_and_send('Fetching round names', request)
        column = response['values'][0]
        result = []
        suppress = {'', 'Hunt', 'Meta'}
        for cell in column:
            if cell not in suppress and cell not in result:
                result.append(cell)
        return result

    def unsolved_puzzles_by_round(
            self, channel_name: str) -> Tuple[Dict[str, List[str]], Optional[str]]:
        request = self.sheets.values().get(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                           range='Puzzle List!A3:G')
        response = self.client.log_and_send('Fetching puzzle names', request)
        result: Dict[str, List[str]] = {}
        default_puzzle: Optional[str] = None
        for row in response['values']:
            if len(row) < 7:
                continue
            round, name, _, _, _, channel_link, status = row
            if status not in {'Solved', 'Backsolved'} and name:
                result.setdefault(round, []).append(name)
            if channel_name and link_to_channel(channel_link) == channel_name:
                default_puzzle = name
        return result, default_puzzle

    def mark_doc_solved(self, doc_url: str) -> None:
        # Find the file ID from its URL.
        match = FILE_ID_PATTERN.search(doc_url)
        if not match:
            raise ValueError(f"Can't find a file ID in {doc_url}")
        file_id = match.group(1)

        # Get the current title.
        request = self.files.get(fileId=file_id)
        response = self.client.log_and_send('Getting puzzle doc title', request)
        name = response['name']
        if name.startswith('[SOLVED]'):
            # We must have done this already. No need to do it twice.
            return

        # Update the title.
        name = f'[SOLVED] {name}'
        request = self.files.update(fileId=file_id, body={'name': name})
        self.client.log_and_send('Updating puzzle doc title', request)

        # Move it to the Solved folder. (Why do we mark it two ways? Changing the title gets the
        # attention of solvers looking at the doc who may not realize the puzzle is solved. Moving
        # to a separate folder keeps the Puzzles folder uncluttered, especially since all the
        # "[SOLVED]" prefixes sort to the top.)
        request = self.files.update(fileId=file_id, addParents=self.solved_folder_id,
                                    removeParents=self.puzzles_folder_id)
        self.client.log_and_send('Moving puzzle doc to Solved folder', request)

    def mark_row_solved(self, row_index: int, solution: str) -> None:
        requests = [{
            'updateCells': {
                'rows': [row_data(['-'])],
                'fields': 'userEnteredValue',
                'start': {
                    'sheetId': self.puzzle_list_sheet_id,
                    'rowIndex': row_index,
                    'columnIndex': 2,  # priority
                }
            }
        }, {
            'updateCells': {
                'rows': [row_data(['Solved', solution])],
                'fields': 'userEnteredValue',
                'start': {
                    'sheetId': self.puzzle_list_sheet_id,
                    'rowIndex': row_index,
                    'columnIndex': 6,  # status, solution
                }
            }
        }]
        batch_request = self.sheets.batchUpdate(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                                body={'requests': requests})
        self.client.log_and_send('Updating tracker row', batch_request)


class UrlConflictError(BaseException):
    def __init__(self, found_url: str, discarded_url: str):
        super().__init__(f'Found "{found_url}", not replacing with "{discarded_url}"')
        self.found_url = found_url
        self.discarded_url = discarded_url


def last_index(l: List[T], value: T) -> int:
    for i in range(len(l) - 1, -1, -1):
        if l[i] == value:
            return i
    raise ValueError


def row_data(cell_values: Iterable[str]):
    values = []
    for value in cell_values:
        if value.startswith('='):
            values.append({'userEnteredValue': {'formulaValue': value}})
        else:
            values.append({'userEnteredValue': {'stringValue': value}})
    return {'values': values}


def canonicalize(name: str) -> str:
    return ''.join(filter(lambda c: c in NAME_CHARACTERS,
                          name.lower().replace('-', '_').replace(' ', '_')))


def channel_to_link(channel: str) -> str:
    return (f'=HYPERLINK("https://controlgroup.slack.com/app_redirect?channel={channel}",'
            f'"#{channel}")')


def link_to_channel(link: str) -> Optional[str]:
    for pattern in CHANNEL_PATTERNS:
        match = pattern.search(link)
        if match:
            return match.group(1)
    return None
