import datetime
import logging
import os
import pprint
import random
from typing import Dict, Optional, Tuple, List, Union

from slackclient import SlackClient

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
            self.unlocks_channel_id = os.environ['PLACEBO_UNLOCKS_CHANNEL_ID_TESTING']
        else:
            self.unlocks_channel_id = os.environ['PLACEBO_UNLOCKS_CHANNEL_ID']
        self.admin_user = os.environ['PLACEBO_ADMIN_SLACK_USER']

    def dm_admin(self, message: str):
        self.log_and_send('DMing admin user', 'chat.postMessage', channel=self.admin_user,
                          text=message)

    def unlock_dialog(self, trigger_id: str, rounds: List[str], last_round: Optional[str]) -> None:
        if last_round not in rounds:
            last_round = None
        dialog = {
            'title': 'Unlock new puzzle',
            'callback_id': 'unlock',
            'elements': [
                {
                    'label': 'Name',
                    'name': 'puzzle_name',
                    'type': 'text',
                    'placeholder': 'Lorem Ipsum',
                },
                {
                    'label': 'URL',
                    'name': 'puzzle_url',
                    'type': 'text',
                    'subtype': 'url',
                    'placeholder': 'https://example.com/puzzle/lorem_ipsum',
                },
                {
                    'label': 'Round',
                    'name': 'round_name',
                    'type': 'select',
                    'value': last_round,
                    'options': [{'label': round, 'value': round} for round in rounds],
                    'placeholder': 'Choose a round',
                }
            ],
        }
        self.log_and_send('Creating /unlock dialog', 'dialog.open', trigger_id=trigger_id,
                          dialog=dialog)

    def correct_dialog(self, trigger_id: str, puzzle_names: List[str]) -> None:
        dialog = {
            'title': 'Mark an answer correct',
            'callback_id': 'correct',
            'elements': [
                {
                    'label': 'Puzzle',
                    'name': 'puzzle_name',
                    'type': 'select',
                    'options': [{'label': p, 'value': p} for p in puzzle_names],
                    'placeholder': 'Choose a puzzle',
                },
                {
                    'label': 'Answer',
                    'name': 'answer',
                    'type': 'text',
                    'placeholder': 'LOREM IPSUM',
                }
            ]
        }
        self.log_and_send('Creating /correct dialog', 'dialog.open', trigger_id=trigger_id,
                          dialog=dialog)

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
                        channel_name: str, channel_id: str, round_color: str) -> None:
        lines = []
        if round_name:
            lines.append(f'Round: {round_name}')
        lines.append(f'<#{channel_id}|{channel_name}>')
        attach = {
            'color': round_color,
            'title': puzzle_name,
            'title_link': puzzle_url,
            'text': '\n'.join(lines),
        }
        self.log_and_send('Announcing unlock', 'chat.postMessage', channel=self.unlocks_channel_id,
                          as_user=False, username='Control Group', icon_emoji=':robot_face:',
                          attachments=[attach])

    def announce_round(self, round_name, round_url):
        attach = {
            'color': '#ccc',
            'title': round_name,
            'title_link': round_url,
            'text': '*New round unlocked!*',
            'mrkdwn_in': 'text',
        }
        self.log_and_send('Announcing round unlock', 'chat.postMessage',
                          channel=self.unlocks_channel_id, as_user=False, username='Control Group',
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
