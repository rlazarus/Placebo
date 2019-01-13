import threading
from typing import Tuple

from flask import Flask, request, jsonify

import placebo

app = Flask(__name__)

placebo_app = placebo.Placebo()
placebo_lock = threading.Lock()  # TODO: Use celery or something instead.


@app.route('/')
def hello():
    return 'Hello World!'


@app.route('/unlock', methods=['POST'])  #### next: test
def unlock():
    try:
        round_name, puzzle_name, puzzle_url = split_unlock(request.form['text'])
    except ValueError:
        return jsonify({
            'response_type': 'ephemeral',
            'text':
                'Try it like this: '
                '`/unlock Puzzle Name https://example.com/puzzle Round Name'
        })
    threading.Thread(target=do_unlock,
                     args=(round_name, puzzle_name, puzzle_url)).start()
    return jsonify({
        'response_type': 'ephemeral',
        'text': f'Adding {puzzle_name}...'
    })


def split_unlock(text: str) -> Tuple[str, str, str]:
    words = text.split()
    url_indexes = [i for i, word in enumerate(words)
                   if word.startswith('http') and '/' in word]
    if len(url_indexes) != 1:
        raise ValueError(f'{len(url_indexes)} URLs, expected exactly 1')
    [url_index] = url_indexes
    puzzle_name = ' '.join(words[:url_index])
    round_name = ' '.join(words[url_index + 1:])
    if not puzzle_name or not round_name:
        raise ValueError('URL not in the middle')
    return puzzle_name, words[url_index], round_name


def do_unlock(*args):
    with placebo_lock:
        placebo_app.new_puzzle(*args)

