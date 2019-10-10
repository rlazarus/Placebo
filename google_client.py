import logging
import os
import re
import string
import pprint
from typing import List, TypeVar, Tuple, Dict, Union, Optional

import httplib2
import psycopg2
from googleapiclient import discovery, http
from oauth2client import client, tools

log = logging.getLogger('placebo.google_client')

# Full drive access for dev.
SCOPE = 'https://www.googleapis.com/auth/drive'

NAME_CHARACTERS = string.ascii_lowercase + string.digits + '_'

CHANNEL_PATTERNS = [
    re.compile('controlgroup.slack.com/messages/([a-z0-9_-]+)'),
    re.compile('#([a-z0-9_-]+)'),
]
FILE_ID_PATTERN = re.compile('/d/([a-zA-Z0-9-_]+)')

T = TypeVar('T')

# This is an incomplete list of value types -- others are possible but these are
# all we've used.
Response = Dict[str, Union[str, int, 'Response', List['Response']]]


class Google:
    def __init__(self):
        store = PostgresStorage()
        creds = store.get()
        if not creds or creds.invalid:
            flow = client.OAuth2WebServerFlow(
                client_id=os.environ['PLACEBO_GOOGLE_CLIENT_ID'],
                client_secret=os.environ['PLACEBO_GOOGLE_CLIENT_SECRET'],
                scope=SCOPE,
                auth_uri='https://accounts.google.com/o/oauth2/auth',
                token_uri='https://www.googleapis.com/oauth2/v3/token')
            creds = tools.run_flow(flow, store)
        http = creds.authorize(httplib2.Http(cache='.cache'))
        self.sheets = discovery.build('sheets', 'v4', http=http).spreadsheets()
        self.files = discovery.build('drive', 'v3', http=http).files()

        # Here and throughout, a "spreadsheet" is the entire sharable unit, and
        # a "sheet" is the page (tabs at the bottom). This is kind of
        # unfortunate but matches the names used in Google Sheets and its API.
        self.puzzle_list_spreadsheet_id = (
            os.environ['PLACEBO_PUZZLE_LIST_SPREADSHEET_ID'])
        self.puzzle_list_sheet_id = os.environ['PLACEBO_PUZZLE_LIST_SHEET_ID']
        self.puzzles_folder_id = os.environ['PLACEBO_PUZZLES_FOLDER_ID']
        self.solved_folder_id = os.environ['PLACEBO_SOLVED_FOLDER_ID']
        self.puzzle_template_id = os.environ['PLACEBO_PUZZLE_TEMPLATE_ID']

    def create_puzzle_spreadsheet(self, puzzle_name: str) -> str:
        request = self.files.copy(fileId=self.puzzle_template_id, body={
            'name': puzzle_name,
            'parents': [self.puzzles_folder_id],
        })
        response = log_and_send('Creating spreadsheet', request)
        doc_id = response['id']
        url = f'https://docs.google.com/spreadsheets/d/{doc_id}/edit'
        return url

    def add_row(self, round_name: str, puzzle_name: str, priority: str,
                puzzle_url: str, doc_url: str, channel: Optional[str]) -> str:
        assert priority in {'-', 'L', 'M', 'H'}
        assert channel is None or not channel.startswith('#')

        # Find the last row that matches this round; we'll insert below it.
        request = self.sheets.get(spreadsheetId=self.puzzle_list_spreadsheet_id,
                                  ranges='Puzzle List!A:A',
                                  includeGridData=True)
        response = log_and_send('Looking up the Round column', request)
        rows = response['sheets'][0]['data'][0]['rowData']
        round_names = [(row['values'][0].get('formattedValue', '')
                        if 'values' in row else '')
                       for row in rows]
        canon_rounds = [canonicalize(r) for r in round_names]
        if canonicalize(round_name) in canon_rounds:
            row_index = last_index(canon_rounds, canonicalize(round_name)) + 1
            cell = rows[row_index - 1]['values'][0]
            round_color = hex_color(cell['effectiveFormat']['backgroundColor'])
        else:
            # If we've never seen this round before, insert at the bottom of the
            # table. That is, before the first blank cell not in the header.
            try:
                row_index = round_names.index('', 2)
            except ValueError:
                # There are no blank round cells after the header? Sounds fake,
                # but okay -- insert at the very end of the sheet.
                row_index = len(round_names)
            # If it's a new round, pick a boring default color for the unlock.
            round_color = "#ccc"

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
        slack_link = channel_to_link(channel)
        cell_values = [round_name, puzzle_name, priority, puzzle_url, doc_url,
                       slack_link, 'Not started']
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
        batch_request = self.sheets.batchUpdate(
            spreadsheetId=self.puzzle_list_spreadsheet_id,
            body={'requests': requests})
        log_and_send('Adding row to tracker', batch_request)

        return round_color

    def exists(self, puzzle_name: str) -> bool:
        request = self.sheets.values().get(
            spreadsheetId=self.puzzle_list_spreadsheet_id,
            range='Puzzle List!B:B',
            majorDimension='COLUMNS')
        response = log_and_send('Checking tracking sheet for puzzle', request)
        puzzle_name = canonicalize(puzzle_name)
        column = response['values'][0]
        for cell in column:
            if puzzle_name in canonicalize(cell):
                return True
        return False

    def lookup(self, puzzle_name: str) -> Optional[
                                              Tuple[int, str, Optional[str]]]:
        request = self.sheets.values().get(
            spreadsheetId=self.puzzle_list_spreadsheet_id,
            range='Puzzle List!A:G')
        response = log_and_send('Fetching tracking sheet', request)
        puzzle_name = canonicalize(puzzle_name)
        matching_rows = []
        for row_index, row in enumerate(response['values']):
            if len(row) > 5 and puzzle_name in canonicalize(row[1]):
                matching_rows.append(
                    (row_index, row[4], link_to_channel(row[5])))
        if not matching_rows:
            return None
        elif len(matching_rows) == 1:
            return matching_rows[0]
        else:
            raise KeyError(f'{len(matching_rows)} rows matching {puzzle_name}')

    def all_rounds(self) -> List[str]:
        request = self.sheets.values().get(
            spreadsheetId=self.puzzle_list_spreadsheet_id,
            range='Puzzle List!A3:A',
            majorDimension='COLUMNS')
        response = log_and_send('Fetching round names', request)
        column = response['values'][0]
        result = []
        suppress = {'', 'Hunt', 'Meta'}
        for cell in column:
            if cell not in suppress and cell not in result:
                result.append(cell)
        return result

    def mark_doc_solved(self, doc_url: str) -> None:
        # Find the file ID from its URL.
        match = FILE_ID_PATTERN.search(doc_url)
        if not match:
            raise ValueError(f"Can't find a file ID in {doc_url}")
        file_id = match.group(1)

        # Get the current title.
        request = self.files.get(fileId=file_id)
        response = log_and_send('Getting puzzle doc title', request)
        name = response['name']
        if name.startswith('[SOLVED]'):
            # We must have done this already. No need to do it twice.
            return

        # Update the title.
        name = f'[SOLVED] {name}'
        request = self.files.update(fileId=file_id, body={'name': name})
        log_and_send('Updating puzzle doc title', request)

        # Move it to the Solved folder. (Why do we mark it two ways? Changing
        # the title gets the attention of solvers looking at the doc who may not
        # realize the puzzle is solved. Moving to a separate folder keeps the
        # Puzzles folder uncluttered, especially since all the "[SOLVED]"
        # prefixes sort to the top.)
        request = self.files.update(fileId=file_id,
                                    addParents=self.solved_folder_id,
                                    removeParents=self.puzzles_folder_id)
        log_and_send('Moving puzzle doc to Solved folder', request)

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
        batch_request = self.sheets.batchUpdate(
            spreadsheetId=self.puzzle_list_spreadsheet_id,
            body={'requests': requests})
        log_and_send('Updating tracker row', batch_request)


def last_index(l: List[T], value: T) -> int:
    for i in range(len(l) - 1, -1, -1):
        if l[i] == value:
            return i
    raise ValueError


def row_data(cell_values: List[str]):
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


def channel_to_link(channel: Optional[str]) -> str:
    if channel is None:
        return ''
    return (f'=HYPERLINK('
            f'"https://controlgroup.slack.com/app_redirect?channel={channel}",'
            f'"#{channel}")')


def link_to_channel(link: str) -> Optional[str]:
    for pattern in CHANNEL_PATTERNS:
        match = pattern.search(link)
        if match:
            return match.group(1)
    return None


def hex_color(rgb: Dict[str, float]) -> str:
    return '#' + ''.join(format(int(rgb.get(i, 0) * 255), '02x')
                         for i in ['red', 'green', 'blue'])


def log_and_send(desc: str, request: http.HttpRequest) -> Response:
    log.info(desc)
    log.debug(pprint.pformat(request))
    response = request.execute()
    log.debug(pprint.pformat(response))
    return response


class PostgresStorage(client.Storage):
    def __init__(self, lock=None):
        super().__init__(lock)
        self.conn = psycopg2.connect(os.environ['DATABASE_URL'],
                                     sslmode='require')

    def locked_get(self) -> client.Credentials:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT value FROM credentials WHERE name = 'google_token';")
        assert cursor.rowcount == 1
        [(creds_json,)] = cursor.fetchall()
        return client.GoogleCredentials.from_json(creds_json)

    def locked_put(self, credentials: client.Credentials) -> None:
        cursor = self.conn.cursor()
        json = credentials.to_json()
        cursor.execute("INSERT INTO credentials (name, value) "
                       "VALUES ('google_token', %s) "
                       "ON CONFLICT (name) DO UPDATE SET value = %s "
                       "WHERE credentials.name = 'google_token';",
                       (json, json))
        self.conn.commit()

    def locked_delete(self):
        raise NotImplementedError
