import logging
import queue
import threading
from typing import Callable, Optional

import requests

import google_client
import slack_client

logging.basicConfig(format='{asctime} {name} {levelname}: {message}', style='{')
logging.getLogger('googleapiclient').setLevel(logging.ERROR)  # It's real noisy.
log = logging.getLogger('placebo')
log.setLevel(logging.INFO)


class Placebo:
    def __init__(self) -> None:
        self.google = google_client.Google()
        self.slack = slack_client.Slack()
        self.queue: queue.Queue[Callable[[], None]] = queue.Queue()
        # If set, it's the round in which the most recent puzzle was unlocked. It's used as the
        # default round for the unlock dialog, to make repeated unlocks easier.
        self.last_round: Optional[str] = None
        threading.Thread(target=self._worker_thread, daemon=True).start()

    # The public methods don't do any work -- they just enqueue a call to the corresponding private
    # method, which the worker thread picks up. That accomplishes two things:
    # - Ensures we always return a 200 for the incoming HTTP request promptly, without waiting for
    #   our API backends.
    # - Ensures we're never handling more than one request at a time.

    def new_round(self, round_name: str, round_url: str) -> None:
        self.queue.put(lambda: self._new_round(round_name, round_url))

    def new_puzzle(self, round_name: str, puzzle_name: str, puzzle_url: str,
                   response_url: Optional[str] = None) -> None:
        self.queue.put(lambda: self._new_puzzle(round_name, puzzle_name, puzzle_url, response_url))

    def solved_puzzle(
            self, puzzle_name: str, solution: str, response_url: Optional[str] = None) -> None:
        self.queue.put(lambda: self._solved_puzzle(puzzle_name, solution, response_url))

    def _worker_thread(self) -> None:
        while True:
            func = self.queue.get()
            try:
                func()
            except BaseException as e:
                # TODO: Reply to the original command if we can.
                log.exception(e)

    def _new_round(self, round_name: str, round_url: str) -> None:
        meta_name = round_name + " Meta"
        if self.google.lookup(meta_name) is not None:
            raise KeyError(f'Puzzle "{meta_name}" is already in the tracker.')
        doc_url = self.google.create_puzzle_spreadsheet(meta_name)
        channel_name, channel_id = self.slack.create_channel(round_url, doc_url, prefix='meta')
        self.google.add_row(round_name, meta_name, 'L', round_url, doc_url, channel_name)
        self.slack.announce_round(round_name, round_url)

    def _new_puzzle(self, round_name: str, puzzle_name: str, puzzle_url: str,
                    response_url: Optional[str]) -> None:
        _ephemeral_ack(f'Adding *{puzzle_name}*...', response_url)
        if self.google.exists(puzzle_name):
            raise KeyError(f'Puzzle "{puzzle_name}" is already in the tracker.')
        doc_url = self.google.create_puzzle_spreadsheet(puzzle_name)
        channel_name, channel_id = self.slack.create_channel(puzzle_url, doc_url)
        round_color = self.google.add_row(round_name, puzzle_name, 'M', puzzle_url, doc_url,
                                          channel_name)
        self.slack.announce_unlock(round_name, puzzle_name, puzzle_url, channel_name, channel_id,
                                   round_color)
        self.last_round = round_name

    def _solved_puzzle(self, puzzle_name: str, solution: str, response_url: Optional[str]) -> None:
        _ephemeral_ack(f'Marking *{puzzle_name}* correct...', response_url)
        lookup = self.google.lookup(puzzle_name)
        if lookup is None:
            raise KeyError(f'Puzzle "{puzzle_name}" not found.')
        row_index, doc_url, channel_name = lookup
        if doc_url:
            self.google.mark_doc_solved(doc_url)
        self.google.mark_row_solved(row_index, solution)
        if channel_name:
            self.slack.solved(channel_name, solution)


def _ephemeral_ack(message, response_url) -> None:
    if not response_url:
        return
    log.info('Logging ephemeral acknowledgment...')
    response = requests.post(response_url, json={
        'text': message,
        'response_type': 'ephemeral'
    })
    if response.status_code != 200:
        log.error(f"Couldn't log ephemeral acknowledgment: {response.status_code} {response.text}")
