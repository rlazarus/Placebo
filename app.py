import threading
from typing import Tuple

from flask import Flask, request, jsonify

import placebo

app = Flask(__name__)
placebo_app = placebo.Placebo()


@app.route('/unlock', methods=['POST'])
def unlock():
    try:
        puzzle_name, puzzle_url, round_name = split_unlock(request.form['text'])
    except ValueError:
        return ephemeral(
            'Try it like this: '
            '`/unlock Puzzle Name https://example.com/puzzle Round Name`')
    threading.Thread(target=placebo_app.new_puzzle,
                     args=(round_name, puzzle_name, puzzle_url)).start()
    return ephemeral(f'Adding {puzzle_name}...')


@app.route('/correct', methods=['POST'])
def correct():
    try:
        puzzle_name, solution = split_correct(request.form['text'])
    except ValueError:
        return ephemeral(
            'Try it like this: `/correct Puzzle Name PUZZLE SOLUTION`')
    threading.Thread(target=placebo_app.solved_puzzle,
                     args=(puzzle_name, solution)).start()
    return ephemeral(f'Marking {puzzle_name} solved...')


def ephemeral(text):
    return jsonify({'response_type': 'ephemeral', 'text': text})


@app.route('/newround', methods=['POST'])
def newround():
    words = request.form['text'].split()
    if len(words) < 2 or not is_url(words[-1]):
        return ephemeral(
            'Try it like this: /newround Round Name https://example.com/round')
    name = ' '.join(words[:-1])
    url = words[-1]
    threading.Thread(target=placebo_app.new_round, args=(name, url)).start()
    return ephemeral(f'Adding {name}...')


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
