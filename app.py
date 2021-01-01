import json
import logging
import pprint
from typing import Tuple

import flask
from werkzeug.exceptions import BadRequest

import placebo

log = logging.getLogger('placebo.app')
app = flask.Flask(__name__)
placebo_app = placebo.Placebo()


@app.route('/unlock', methods=['POST'])
def unlock() -> flask.Response:
    text = flask.request.form['text']
    if not text:
        rounds = placebo_app.google.all_rounds()
        placebo_app.slack.unlock_dialog(flask.request.form['trigger_id'], rounds,
                                        placebo_app.last_round)
        return flask.make_response("", 200)

    try:
        puzzle_name, puzzle_url, round_name = split_unlock(flask.request.form['text'])
    except ValueError:
        return ephemeral(
            'Try it like this: `/unlock Puzzle Name https://example.com/puzzle Round Name`')
    placebo_app.new_puzzle(round_name, puzzle_name, puzzle_url)
    return ephemeral(f'Adding {puzzle_name}...')


@app.route('/correct', methods=['POST'])
def correct() -> flask.Response:
    text = flask.request.form['text']
    if not text:
        puzzle_names = placebo_app.google.unsolved_puzzles()
        placebo_app.slack.correct_dialog(flask.request.form['trigger_id'], puzzle_names)
        return flask.make_response("", 200)
    try:
        puzzle_name, solution = split_correct(text)
    except ValueError:
        return ephemeral('Try it like this: `/correct Puzzle Name PUZZLE SOLUTION`')
    placebo_app.solved_puzzle(puzzle_name, solution)
    return ephemeral(f'Marking {puzzle_name} solved...')


@app.route('/newround', methods=['POST'])
def newround() -> flask.Response:
    words = flask.request.form['text'].split()
    if len(words) < 2 or not is_url(words[-1]):
        return ephemeral('Try it like this: /newround Round Name https://example.com/round')
    name = ' '.join(words[:-1])
    url = words[-1]
    placebo_app.new_round(name, url)
    return ephemeral(f'Adding {name}...')


@app.route('/interact', methods=['POST'])
def interact() -> flask.Response:
    data = json.loads(flask.request.form['payload'])
    log.debug(pprint.pformat(data))
    try:
        type = data['type']
        if type == 'dialog_submission':
            callback_id = data['callback_id']
            if callback_id == 'unlock':
                round_name = data['submission']['round_name']
                puzzle_name = data['submission']['puzzle_name']
                puzzle_url = data['submission']['puzzle_url']
                response_url = data['response_url']
                placebo_app.new_puzzle(round_name, puzzle_name, puzzle_url, response_url)
                return flask.make_response("", 200)
            elif callback_id == 'correct':
                puzzle_name = data['submission']['puzzle_name']
                answer = data['submission']['answer']
                response_url = data['response_url']
                placebo_app.solved_puzzle(puzzle_name, answer, response_url)
                return flask.make_response("", 200)
            raise BadRequest(f'Unexpected callback_id {callback_id}')
        elif type == 'block_actions':
            actions = data['actions']
            if len(actions) != 1:
                raise BadRequest(f'Got {len(actions)} actions, expected 1')
            action_id = actions[0]['action_id']
            if action_id == 'archive':
                placebo_app.slack.archive(actions[0]['value'])
            else:
                raise BadRequest(f'Unexpected action_id {action_id}')
        raise BadRequest(f'Unexpected type {type}')
    except BadRequest:
        logging.exception(pprint.pformat(data))
        raise


@app.route('/google_oauth')
def google_oauth() -> str:
    if 'error' in flask.request.args:
        error = flask.request.args['error']
        log.error('Google OAuth error: %s', error)
        return f'Google OAuth error: {error}'
    placebo_app.google.finish_oauth(flask.request.url)
    return 'Authorized!'


def ephemeral(text: str) -> flask.Response:
    return flask.jsonify({'response_type': 'ephemeral', 'text': text})


def split_unlock(text: str) -> Tuple[str, str, str]:
    words = text.split()
    url_indexes = [i for i, word in enumerate(words) if is_url(word)]
    if len(url_indexes) != 1:
        raise ValueError(f'{len(url_indexes)} URLs, expected exactly 1')
    [url_index] = url_indexes
    puzzle_name = ' '.join(words[:url_index])
    round_name = ' '.join(words[url_index + 1:])
    if not puzzle_name or not round_name:
        raise ValueError('URL not in the middle')
    return puzzle_name, words[url_index], round_name


def split_correct(text: str) -> Tuple[str, str]:
    words = text.split()
    solution_start = len(words)
    while solution_start >= 1 and words[solution_start - 1].isupper():
        solution_start -= 1
    puzzle_name = ' '.join(words[:solution_start])
    solution = ' '.join(words[solution_start:])
    if not puzzle_name or not solution:
        raise ValueError('No caps, or all caps')
    return puzzle_name, solution


def is_url(word: str) -> bool:
    return word.startswith('http') and '/' in word
