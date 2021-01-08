import json
import logging
import pprint
from typing import Any, Dict, Tuple

import flask
import requests
from werkzeug.exceptions import BadRequest

import placebo
import util

log = logging.getLogger('placebo.app')
app = flask.Flask(__name__)
placebo_app = placebo.Placebo()


@app.route('/unlock', methods=['POST'])
def unlock() -> flask.Response:
    text = flask.request.form['text']
    if not text:
        trigger_id = flask.request.form['trigger_id']
        user_id = flask.request.form['user_id']
        rounds = placebo_app.google.all_rounds()
        placebo_app.slack.unlock_modal(trigger_id, user_id, rounds, placebo_app.last_round)
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
        trigger_id = flask.request.form['trigger_id']
        user_id = flask.request.form['user_id']
        puzzle_names = placebo_app.google.unsolved_puzzles()
        placebo_app.slack.correct_modal(trigger_id, user_id, puzzle_names)
        return flask.make_response("", 200)
    try:
        puzzle_name, solution = split_correct(text)
    except ValueError:
        return ephemeral('Try it like this: `/correct Puzzle Name PUZZLE SOLUTION`')
    placebo_app.solved_puzzle(puzzle_name, solution)
    return ephemeral(f'Marking {puzzle_name} solved...')


@app.route('/newround', methods=['POST'])
def newround() -> flask.Response:
    text = flask.request.form['text']
    if not text:
        trigger_id = flask.request.form['trigger_id']
        user_id = flask.request.form['user_id']
        placebo_app.slack.newround_modal(trigger_id, user_id)
        return flask.make_response("", 200)
    words = text.split()
    if len(words) < 2 or not is_url(words[-1]):
        return ephemeral('Try it like this: /newround Round Name https://example.com/round')
    name = ' '.join(words[:-1])
    url = words[-1]
    placebo_app.new_round(name, url, None)
    return ephemeral(f'Adding {name}...')


@app.route('/interact', methods=['POST'])
def interact() -> flask.Response:
    payload = json.loads(flask.request.form['payload'])
    log.debug(pprint.pformat(payload))
    try:
        type = payload['type']
        if type == 'view_submission':
            return view_submission(payload['view'])
        elif type == 'view_closed':
            placebo_app.view_closed(payload['view']['id'])
            return flask.make_response("", 200)
        elif type == 'block_actions':
            return block_actions(payload)
        raise BadRequest(f'Unexpected type {type}')
    except BadRequest:
        logging.exception(pprint.pformat(payload))
        raise


def view_submission(view: Dict[str, Any]) -> flask.Response:
    callback_id = view['callback_id']
    fields = {}
    for block in view['state']['values'].values():
        for action_id, action in block.items():
            action_type = action['type']
            if action_type == 'plain_text_input':
                fields[action_id] = action['value']
            elif action_type == 'static_select':
                fields[action_id] = action['selected_option']['value']
            else:
                raise BadRequest(f'Unexpected action type {action_type}')
    if callback_id == 'unlock':
        placebo_app.new_puzzle(**fields)
    elif callback_id == 'correct':
        placebo_app.solved_puzzle(**fields)
    elif callback_id == 'newround':
        if 'round_color' in fields:
            fields['round_color'] = util.Color.from_hex(fields['round_color'])
        placebo_app.new_round(**fields)
    else:
        raise BadRequest(f'Unexpected callback_id {callback_id}')
    placebo_app.view_closed(view['id'])
    return flask.make_response("", 200)


def block_actions(payload: Dict[str, Any]) -> flask.Response:
    actions = payload['actions']
    if len(actions) != 1:
        raise BadRequest(f'Got {len(actions)} actions, expected 1')
    action_id = actions[0]['action_id']
    if action_id == 'archive':
        # Remove the archive button from the original message (but keep the first block, which says
        # the answer was correct).
        user = payload['user']['id']
        message = payload['message']
        message['blocks'][1] = {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f"Archiving this channel at <@{user}>'s request.",
            }
        }
        message['replace_original'] = True
        try:
            response = requests.post(payload['response_url'], json=message)
            response.raise_for_status()
        except requests.RequestException:
            log.exception('HTTP error while updating the archive offer')
            return flask.make_response("", 200)

        placebo_app.slack.archive(actions[0]['value'])

        return flask.make_response("", 200)
    raise BadRequest(f'Unexpected action_id {action_id}')


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
