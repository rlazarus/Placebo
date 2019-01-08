import datetime
import logging
import pprint
from typing import Optional

from slackclient import SlackClient

log = logging.getLogger('placebo.slack_client')


class Slack:
    def __init__(self):
        with open('slack_token.txt') as f:
            token = f.read()
        self.client = SlackClient(token)

    def create_channel(self, puzzle_url: str, doc_url: str,
                       prefix: Optional[str] = None) -> str:
        puzzle_slug = puzzle_url.rstrip('/').split('/')[-1]
        name = f'{prefix}_{puzzle_slug}' if prefix else puzzle_slug
        response = self.log_and_send('Creating channel', 'channels.create',
                                     name=name)
        assert response['ok']
        name = response['channel']['name']
        id = response['channel']['id']

        self.log_and_send('Setting topic', 'channels.setTopic', channel=id,
                          topic=f'{puzzle_url} | {doc_url}')
        return name

    def solved(self, channel_name: str, answer: str) -> None:
        channel_id = self.get_channel_id_by_name(channel_name)
        archive = not self.is_channel_active(channel_id)

        text = (f'This puzzle is solved! "{answer}" is correct.'
                f' Congratulations!\n\n')
        if archive:
            text += ('This channel will be archived, but feel free to '
                     'un-archive it if you want to keep talking.')
        else:
            text += ('Please archive this channel if you\'re done with it, by '
                     'clicking the gear menu and then "Additional options."')
        self.log_and_send('Posting to puzzle channel', 'chat.postMessage',
                          channel=channel_id, as_user=False, icon_emoji='',
                          attachments=[{'text': text, 'color': 'good'}])

        if archive:
            self.log_and_send('Archiving puzzle channel',
                              'conversations.archive', channel=channel_id)
        else:
            log.info('Not archiving puzzle channel.')

    def get_channel_id_by_name(self, channel_name: str) -> str:
        cursor = None
        while True:
            response = self.log_and_send('Getting channel list',
                                         'conversations.list', cursor=cursor,
                                         exclude_archived=True, limit=100,
                                         types='public_channel')
            assert response["ok"]
            for channel in response["channels"]:
                if channel["name"] == channel_name:
                    return channel["id"]
            next_cursor = response["response_metadata"].get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor
        raise KeyError(f'Channel #{channel_name} not found.')

    def is_channel_active(self, channel_id: str) -> bool:
        oldest = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
        response = self.log_and_send('Getting latest messages',
                                     'conversations.history',
                                     channel=channel_id, oldest=oldest, limit=1)
        if not response['ok']:
            # Just play it safe.
            return True
        return bool(response['messages'])

    def log_and_send(self, desc: str, request: str, **kwargs) -> dict:
        log.info(desc)
        log.debug('%s\n%s', request, pprint.pformat(kwargs))
        response = self.client.api_call(request, **kwargs)
        if response['ok']:
            log.debug(pprint.pformat(response))
        else:
            log.error(pprint.pformat(response))
            raise AssertionError
        return response
