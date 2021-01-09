import datetime
import itertools
import logging
import os
import pprint
import random
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from slackclient import SlackClient

import util

log = logging.getLogger('placebo.slack_client')

SUCCESS_EMOJI = ['sunglasses', 'hugging_face', 'dancer', 'muscle', 'thumbsup', 'clap',
                 'raised_hands', 'brain', 'boom', 'fireworks', 'sparkler', 'sparkles', 'balloon',
                 'tada', 'confetti_ball', 'medal', 'trophy', 'first_place_medal', 'dart', 'star',
                 'stars', 'rainbow', 'fire', 'musical_note', 'notes', 'ballot_box_with_check',
                 '100', 'checkered_flag', 'awesome', 'bananadance', 'bb8', 'parrot', 'woo']


class Slack:
    def __init__(self):
        self.client = SlackClient(os.environ['PLACEBO_SLACK_TOKEN'])
        if os.environ.get('PLACEBO_TESTING') == '1':
            self.qm_channel_id = os.environ['PLACEBO_QM_CHANNEL_ID_TESTING']
            self.unlocks_channel_id = os.environ['PLACEBO_UNLOCKS_CHANNEL_ID_TESTING']
        else:
            self.qm_channel_id = os.environ['PLACEBO_QM_CHANNEL_ID']
            self.unlocks_channel_id = os.environ['PLACEBO_UNLOCKS_CHANNEL_ID']
        self.admin_user = os.environ['PLACEBO_ADMIN_SLACK_USER']
        self.in_progress_messages: Dict[str, str] = {}

    def dm_admin(self, message: str):
        self.log_and_send('DMing admin user', 'chat.postMessage', channel=self.admin_user,
                          text=message)

    def newround_modal(self, trigger_id: str, user_id: str) -> None:
        view = {
            'type': 'modal',
            'callback_id': 'newround',
            'title': plain_text('Unlock new round'),
            'blocks': [
                {
                    'type': 'input',
                    'label': plain_text('Name'),
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'round_name',
                        'placeholder': plain_text('Lorem Ipsum'),
                    },
                },
                {
                    'type': 'input',
                    'label': plain_text('URL'),
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'round_url',
                        'placeholder': plain_text('https://example.com/round/lorem_ipsum'),
                    },
                },
                {
                    'type': 'input',
                    'label': plain_text('Color'),
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'round_color',
                        'placeholder': plain_text('#6789ab'),
                    },
                    'hint': plain_text("You can leave this blank, and I'll just rotate through "
                                       "some reasonable presets."),
                    'optional': True,
                }
            ],
            'close': plain_text('Cancel'),
            'submit': plain_text('Submit'),
            'notify_on_close': True,
        }
        response = self.log_and_send('Opening /newround modal', 'views.open', trigger_id=trigger_id,
                                     view=view)
        self.post_in_progress_message(response['view']['id'], user_id, 'is adding a round...')

    def unlock_modal(self, trigger_id: str, user_id: str, rounds: List[str],
                     last_round: Optional[str]) -> None:
        view = {
            'type': 'modal',
            'callback_id': 'unlock',
            'title': plain_text('Unlock new puzzle'),
            'blocks': [
                {
                    'type': 'input',
                    'label': plain_text('Name'),
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'puzzle_name',
                        'placeholder': plain_text('Lorem Ipsum'),
                    },
                },
                {
                    'type': 'input',
                    'label': plain_text('URL'),
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'puzzle_url',
                        'placeholder': plain_text('https://example.com/puzzle/lorem_ipsum'),
                    },
                },
                {
                    'type': 'input',
                    'label': plain_text('Round'),
                    'element': {
                        'type': 'static_select',
                        'action_id': 'round_name',
                        'options': [{'text': plain_text(r), 'value': r} for r in rounds],
                        'placeholder': plain_text('Choose a round'),
                    }
                }
            ],
            'close': plain_text('Cancel'),
            'submit': plain_text('Submit'),
            'notify_on_close': True,
        }
        if last_round in rounds:
            view['blocks'][2]['element']['initial_option'] = {
                'text': plain_text(last_round),
                'value': last_round
            }
        response = self.log_and_send('Opening /unlock modal', 'views.open', trigger_id=trigger_id,
                                     view=view)
        self.post_in_progress_message(response['view']['id'], user_id, 'is adding an unlock...')

    def correct_modal(self, trigger_id: str, user_id: str, puzzles_by_round: Dict[str, List[str]],
                      default_puzzle: Optional[str]) -> None:
        view = {
            'type': 'modal',
            'callback_id': 'correct',
            'title': plain_text('Mark an answer correct'),
            'blocks': [
                {
                    'type': 'input',
                    'label': plain_text('Puzzle'),
                    'element': {
                        'type': 'static_select',
                        'action_id': 'puzzle_name',
                        'option_groups': [
                            {
                                'label': plain_text(round),
                                'options': [{'text': plain_text(p), 'value': p} for p in puzzles]
                            }
                            for round, puzzles in puzzles_by_round.items()],
                        'placeholder': plain_text('Choose a puzzle')
                    }
                },
                {
                    'type': 'input',
                    'label': plain_text('Answer'),
                    'element': {
                        'type': 'plain_text_input',
                        'action_id': 'answer',
                        'placeholder': plain_text('LOREM IPSUM'),
                    },
                }
            ],
            'close': plain_text('Cancel'),
            'submit': plain_text('Submit'),
            'notify_on_close': True,
        }
        if default_puzzle in itertools.chain.from_iterable(puzzles_by_round.values()):
            view['blocks'][0]['element']['initial_option'] = {
                'text': plain_text(default_puzzle),
                'value': default_puzzle,
            }
        response = self.log_and_send('Opening /correct modal', 'views.open', trigger_id=trigger_id,
                                     view=view)
        self.post_in_progress_message(response['view']['id'], user_id,
                                      'is marking a puzzle solved...')

    def post_in_progress_message(self, view_id: str, user_id: str, message: str) -> None:
        response = self.log_and_send('Looking up username', 'users.info', user=user_id)
        user_name = response['user']['name']
        response = self.log_and_send(
            'Mentioning in #qm', 'chat.postMessage', channel=self.qm_channel_id,
            username='Control Group', icon_emoji=':robot_face:',
            text=f'*{user_name}* {message}')
        message_ts = response['ts']
        self.in_progress_messages[view_id] = message_ts
        log.info('Storing: %s : %s', view_id, message_ts)

    def delete_in_progress_message(self, view_id: str) -> None:
        try:
            ts = self.in_progress_messages.pop(view_id)
        except KeyError:
            log.info(f'No in-progress message timestamp stored for view id {view_id}')
            return
        self.log_and_send('Removing in-progress message', 'chat.delete', channel=self.qm_channel_id,
                          ts=ts)

    def create_channel(self, puzzle_url: str, prefix: Optional[str] = None) -> Tuple[str, str]:
        puzzle_slug = puzzle_url.rstrip('/').split('/')[-1]
        name = f'{prefix}_{puzzle_slug}' if prefix else puzzle_slug
        response = self.log_and_send('Creating channel', 'conversations.create', name=name)
        assert response['ok']
        name = response['channel']['name']
        id = response['channel']['id']
        self.log_and_send('Setting topic (URL only)', 'conversations.setTopic', channel=id,
                          topic=puzzle_url)
        return name, id

    def set_topic(self, channel_id: str, puzzle_url: str, doc_url: str) -> None:
        self.log_and_send('Setting topic', 'conversations.setTopic', channel=channel_id,
                          topic=f'{puzzle_url} | {doc_url}')

    def announce_unlock(self, round_name: Optional[str], puzzle_name: str, puzzle_url: str,
                        channel_name: str, channel_id: str, round_color: util.Color) -> None:
        lines = []
        if round_name:
            lines.append(f'Round: {round_name}')
        lines.append(f'<#{channel_id}|{channel_name}>')
        attach = {
            'color': round_color.to_hex(),
            'title': puzzle_name,
            'title_link': puzzle_url,
            'text': '\n'.join(lines),
        }
        self.log_and_send('Announcing unlock', 'chat.postMessage', channel=self.unlocks_channel_id,
                          username='Control Group', icon_emoji=':robot_face:', attachments=[attach])

    def announce_round(self, round_name: str, round_url: str, round_color: util.Color):
        attach = {
            'color': round_color.to_hex(),
            'title': round_name,
            'title_link': round_url,
            'text': '*New round unlocked!*',
            'mrkdwn_in': 'text',
        }
        self.log_and_send('Announcing round unlock', 'chat.postMessage',
                          channel=self.unlocks_channel_id, username='Control Group',
                          icon_emoji=':robot_face:', attachments=[attach])

    def solved(self, channel_name: str, answer: str) -> None:
        channel_id = self.get_channel_id_by_name(channel_name)
        archive = not self.is_channel_active(channel_id)

        num_emoji = random.choice([3, 4, 4, 5, 5, 6])
        emoji = ''.join(f':{i}:' for i in random.sample(SUCCESS_EMOJI, num_emoji))
        text = f'This puzzle is solved! "{answer}" is correct. Congratulations! {emoji}'
        if archive:
            text += ('\n\nThis channel will be archived, but feel free to un-archive it if you '
                     'want to keep talking.')
            blocks = [{
                'type': 'section',
                'text': plain_text(text, emoji=True)
            }]
        else:
            blocks = [
                {
                    'type': 'section',
                    'text': plain_text(text, emoji=True)
                },
                {
                    'type': 'section',
                    'text': plain_text("If you're done using this channel, would you like to clean "
                                       "it up?"),
                    'accessory': {
                        'type': 'button',
                        'text': plain_text(f'Archive #{channel_name}'),
                        'value': channel_id,
                        'action_id': 'archive',
                        'confirm': {
                            'title': plain_text(f'Archive #{channel_name}?'),
                            'text': plain_text(
                                "You won't be able to send messages to it anymore, but you'll "
                                "still be able to read it, and you can always un-archive it if you "
                                "like."),
                            'confirm': plain_text('Yes, archive it'),
                            'deny': plain_text('No, leave it open')
                        }
                    }
                }
            ]
        self.log_and_send('Posting to puzzle channel', 'chat.postMessage', channel=channel_id,
                          username='Control Group', icon_emoji=':robot_face:', text=text,
                          blocks=blocks)

        if archive:
            self.archive(channel_id)
        else:
            log.info('Not archiving puzzle channel.')

    def remove_archive_offer(self, response_url: str, message: Dict[str, Any],
                             replacement_text: str) -> None:
        # Remove the archive button from the original message (but keep the first block, which says
        # the answer was correct).
        message['blocks'][1] = {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': replacement_text
            }
        }
        message['replace_original'] = True
        try:
            log.debug(message)
            response = requests.post(response_url, json=message)
            response.raise_for_status()
        except requests.RequestException:
            # Log it but swallow it; we'll go ahead and archive the channel anyway.
            log.exception('HTTP error while updating the archive offer')

    def archive(self, channel_id):
        self.log_and_send('Archiving puzzle channel', 'conversations.archive', channel=channel_id)

    def get_channel_id_by_name(self, channel_name: str) -> str:
        cursor = None
        while True:
            response = self.log_and_send('Getting channel list', 'conversations.list',
                                         cursor=cursor, exclude_archived=True, limit=100,
                                         types='public_channel')
            assert response['ok']
            for channel in response['channels']:
                if channel['name'] == channel_name:
                    return channel['id']
            next_cursor = response['response_metadata'].get('next_cursor')
            if not next_cursor:
                break
            cursor = next_cursor
        raise KeyError(f'Channel #{channel_name} not found.')

    def is_channel_active(self, channel_id: str) -> bool:
        oldest = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
        response = self.log_and_send('Getting latest messages', 'conversations.history',
                                     channel=channel_id, oldest=oldest.timestamp(), limit=1)
        if not response['ok']:
            # Just play it safe.
            return True
        return bool(response['messages'])

    def log_and_send(self, desc: str, request: str, **kwargs) -> dict:
        log.info(desc)
        response = self.client.api_call(request, **kwargs)
        level = logging.DEBUG if response['ok'] else logging.ERROR
        log.log(level, '%s\n%s', request, pprint.pformat(kwargs))
        log.log(level, pprint.pformat(response))
        assert response['ok']
        return response


def plain_text(text: str, emoji: bool = False) -> Dict[str, Union[str, bool]]:
    return {
        'type': 'plain_text',
        'text': text,
        'emoji': emoji
    }
