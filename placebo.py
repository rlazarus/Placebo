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
            meta_name = round_name + " Meta"
            if self.google.lookup(meta_name) is not None:
                raise KeyError(
                    f'Puzzle "{meta_name}" is already in the tracker.')
            doc_url = self.google.create_puzzle_sheet(meta_name)
            channel_name = self.slack.create_channel(round_url, doc_url,
                                                     prefix='meta')
            self.google.add_row(round_name, meta_name, 'L', round_url, doc_url,
                                channel_name)

    def new_puzzle(self, round_name: str, puzzle_name: str,
                   puzzle_url: str) -> None:
        with self.lock:
            if self.google.lookup(puzzle_name) is not None:
                raise KeyError(
                    f'Puzzle "{puzzle_name}" is already in the tracker.')
            doc_url = self.google.create_puzzle_sheet(puzzle_name)
            channel_name = self.slack.create_channel(puzzle_url, doc_url)
            self.google.add_row(round_name, puzzle_name, 'M', puzzle_url,
                                doc_url,
                                channel_name)

    def solved_puzzle(self, puzzle_name: str, solution: str):
        with self.lock:
            lookup = self.google.lookup(puzzle_name)
            if lookup is None:
                raise KeyError(f'Puzzle "{puzzle_name}" not found.')
            row_index, doc_url, channel_name = lookup
            self.google.mark_doc_solved(doc_url)
            self.google.mark_row_solved(row_index, solution)
            self.slack.solved(channel_name, solution)
