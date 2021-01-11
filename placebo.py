import logging
import os
import queue
import threading
from typing import Callable, Optional

import requests

import google_client
import slack_client
import util

logging.basicConfig(format='{asctime} {name} {levelname}: {message}', style='{')
logging.getLogger('googleapiclient').setLevel(logging.ERROR)  # It's real noisy.
log = logging.getLogger('placebo')
log.setLevel(logging.DEBUG if os.getenv('PLACEBO_DEBUG_LOGS') == '1' else logging.INFO)


class Placebo:
    def __init__(self) -> None:
        self.create_metas = os.getenv('PLACEBO_CREATE_METAS', '1') == '1'
        self.google = google_client.Google()
        self.slack = slack_client.Slack()
        log.addHandler(slack_client.SlackLogHandler(self.slack, level=logging.ERROR))
        self.queue: queue.Queue[Callable[[], None]] = queue.Queue()
        # If set, it's the round in which the most recent puzzle was unlocked. It's used as the
        # default round for the unlock dialog, to make repeated unlocks easier.
        self.last_round: Optional[str] = None
        threading.Thread(target=self._worker_thread, daemon=True).start()

        auth_url = self.google.start_oauth_if_necessary()
        if auth_url:
            self.slack.dm_admin(f'While logged in as the bot user, please visit {auth_url}')

    # The public methods don't do any work -- they just enqueue a call to the corresponding private
    # method, which the worker thread picks up. That accomplishes two things:
    # - Ensures we always return a 200 for the incoming HTTP request promptly, without waiting for
    #   our API backends.
    # - Ensures we're never handling more than one request at a time.

    def new_round(self, round_name: str, round_url: str, round_color: Optional[util.Color]) -> None:
        self.queue.put(lambda: self._new_round(round_name, round_url, round_color))

    def new_puzzle(self, round_name: str, puzzle_name: str, puzzle_url: str,
                   response_url: Optional[str] = None) -> None:
        self.queue.put(lambda: self._new_puzzle(round_name, puzzle_name, puzzle_url, response_url,
                                                meta=False, round_color=None))

    def solved_puzzle(
            self, puzzle_name: str, answer: str, response_url: Optional[str] = None) -> None:
        self.queue.put(lambda: self._solved_puzzle(puzzle_name, answer, response_url))

    def view_closed(self, view_id: str) -> None:
        self.queue.put(lambda: self._view_closed(view_id))

    def _worker_thread(self) -> None:
        while True:
            func = self.queue.get()
            try:
                func()
            except BaseException:
                # TODO: Reply to the original command if we can.
                log.exception('Error in worker thread.')

    def _new_round(
            self, round_name: str, round_url: str, round_color: Optional[util.Color]) -> None:
        if self.create_metas:
            meta_name = round_name + " Meta"
            self._new_puzzle(round_name, meta_name, round_url, response_url=None, meta=True,
                             round_color=round_color)
        else:
            self.last_round = round_name
            round_color = self.google.add_empty_row(round_name, round_color)
            self.slack.announce_round(round_name, round_url, round_color)

    def _new_puzzle(self, round_name: str, puzzle_name: str, puzzle_url: str,
                    response_url: Optional[str], meta: bool,
                    round_color: Optional[util.Color]) -> None:
        _ephemeral_ack(f'Adding *{puzzle_name}*...', response_url)
        if self.google.exists(puzzle_name):
            raise KeyError(f'Puzzle "{puzzle_name}" is already in the tracker.')

        # Creating the spreadsheet is super slow, so do it in parallel.
        doc_url_future = util.future(self.google.create_puzzle_spreadsheet, [puzzle_name])

        # Meanwhile, set up everything else...
        self.last_round = round_name
        prefix = 'meta' if meta else None
        channel_name, channel_id = self.slack.create_channel(puzzle_url, prefix=prefix)
        priority = 'L' if meta else 'M'
        round_color = self.google.add_row(round_name, puzzle_name, priority, puzzle_url,
                                          channel_name, round_color)
        if meta:
            self.slack.announce_round(round_name, puzzle_url, round_color)
        else:
            self.slack.announce_unlock(round_name, puzzle_name, puzzle_url, channel_name,
                                       channel_id, round_color)

        # ... then wait for the doc URL, and go back and fill it in. But don't hold up the worker
        # thread in the meantime.
        def await_and_finish():
            doc_url = doc_url_future.wait()
            self.queue.put(
                lambda: self._finish_new_puzzle(puzzle_name, puzzle_url, channel_id, doc_url))
        threading.Thread(target=await_and_finish).start()

    def _finish_new_puzzle(
            self, puzzle_name: str, puzzle_url: str, channel_id: str, doc_url: str) -> None:
        try:
            self.google.set_doc_url(puzzle_name, doc_url)
        except KeyError:
            log.exception('Tracker row went missing before we got to it -- puzzle name changed?')
        except google_client.UrlConflictError as e:
            log.exception('Doc URL was set before we got to it')
            doc_url = e.found_url
        self.slack.set_topic(channel_id, puzzle_url, doc_url)

    def _solved_puzzle(self, puzzle_name: str, answer: str, response_url: Optional[str]) -> None:
        # It'll already be in caps if it was typed as a command arg, but it might not if it came
        # from the modal.
        answer = answer.upper()
        _ephemeral_ack(f'Marking *{puzzle_name}* correct...', response_url)
        lookup = self.google.lookup(puzzle_name)
        if lookup is None:
            raise KeyError(f'Puzzle "{puzzle_name}" not found.')
        row_index, doc_url, channel_name = lookup
        if doc_url:
            self.google.mark_doc_solved(doc_url)
        self.google.mark_row_solved(row_index, answer)
        if channel_name:
            self.slack.solved(channel_name, answer)

    def _view_closed(self, view_id: str) -> None:
        self.slack.delete_in_progress_message(view_id)


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
