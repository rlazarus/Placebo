import logging
import threading

import google_client
import slack_client

logging.basicConfig()
logging.getLogger('googleapiclient').setLevel(logging.ERROR)  # It's real noisy.
log = logging.getLogger('placebo')
log.setLevel(logging.INFO)


class Placebo:
    def __init__(self):
        self.google = google_client.Google()
        self.slack = slack_client.Slack()
        self.lock = threading.Lock()  # TODO: Use a work queue instead.

    def new_round(self, round_name: str, round_url: str) -> None:
        with self.lock:
            self.google.add_row(round_name, '', '-', '', '', None)
        self.slack.announce_round(round_name, round_url)

    def new_puzzle(self, round_name: str, puzzle_name: str,
                   puzzle_url: str) -> None:
        with self.lock:
            if self.google.lookup(puzzle_name) is not None:
                raise KeyError(
                    f'Puzzle "{puzzle_name}" is already in the tracker.')
            doc_url = self.google.create_puzzle_spreadsheet(puzzle_name)
            channel_name, channel_id = self.slack.create_channel(puzzle_url,
                                                                 doc_url)
            round_color = self.google.add_row(round_name, puzzle_name, 'M',
                                              puzzle_url, doc_url, channel_name)
        self.slack.announce_unlock(round_name, puzzle_name, puzzle_url,
                                   channel_name, channel_id, round_color)

    def solved_puzzle(self, puzzle_name: str, solution: str):
        with self.lock:
            lookup = self.google.lookup(puzzle_name)
            if lookup is None:
                raise KeyError(f'Puzzle "{puzzle_name}" not found.')
            row_index, doc_url, channel_name = lookup
            if doc_url:
                self.google.mark_doc_solved(doc_url)
            self.google.mark_row_solved(row_index, solution)
            if channel_name:
                self.slack.solved(channel_name, solution)
