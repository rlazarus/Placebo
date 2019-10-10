import logging
import queue
import threading
from typing import Callable

import google_client
import slack_client

logging.basicConfig()
logging.getLogger('googleapiclient').setLevel(logging.ERROR)  # It's real noisy.
log = logging.getLogger('placebo')
log.setLevel(logging.INFO)


class Placebo:
    def __init__(self) -> None:
        self.google = google_client.Google()
        self.slack = slack_client.Slack()
        self.queue: queue.Queue[Callable[[], None]] = queue.Queue()
        threading.Thread(target=self._worker_thread, daemon=True).start()

    # The public methods don't do any work -- they just enqueue a call to the
    # corresponding private method, which the worker thread picks up. That
    # accomplishes two things:
    # - Ensures we always return a 200 for the incoming HTTP request promptly,
    #   without waiting for our API backends.
    # - Ensures we're never handling more than one request at a time.

    def new_round(self, round_name: str, round_url: str) -> None:
        self.queue.put(lambda: self._new_round(round_name, round_url))

    def new_puzzle(self, round_name: str, puzzle_name: str,
                   puzzle_url: str) -> None:
        self.queue.put(
            lambda: self._new_puzzle(round_name, puzzle_name, puzzle_url))

    def solved_puzzle(self, puzzle_name: str, solution: str) -> None:
        self.queue.put(lambda: self._solved_puzzle(puzzle_name, solution))

    def _worker_thread(self) -> None:
        while True:
            func = self.queue.get()
            try:
                func()
            except BaseException as e:
                # TODO: Reply to the original command if we can.
                log.exception(e)

    def _new_round(self, round_name: str, round_url: str) -> None:
        self.google.add_row(round_name, '', '-', '', '', None)
        self.slack.announce_round(round_name, round_url)

    def _new_puzzle(self, round_name: str, puzzle_name: str,
                    puzzle_url: str) -> None:
        if self.google.exists(puzzle_name):
            raise KeyError(f'Puzzle "{puzzle_name}" is already in the tracker.')
        doc_url = self.google.create_puzzle_spreadsheet(puzzle_name)
        channel_name, channel_id = self.slack.create_channel(puzzle_url,
                                                             doc_url)
        round_color = self.google.add_row(round_name, puzzle_name, 'M',
                                          puzzle_url, doc_url, channel_name)
        self.slack.announce_unlock(round_name, puzzle_name, puzzle_url,
                                   channel_name, channel_id, round_color)

    def _solved_puzzle(self, puzzle_name: str, solution: str) -> None:
        lookup = self.google.lookup(puzzle_name)
        if lookup is None:
            raise KeyError(f'Puzzle "{puzzle_name}" not found.')
        row_index, doc_url, channel_name = lookup
        if doc_url:
            self.google.mark_doc_solved(doc_url)
        self.google.mark_row_solved(row_index, solution)
        if channel_name:
            self.slack.solved(channel_name, solution)
