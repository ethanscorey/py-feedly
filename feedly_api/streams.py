import logging
from typing import Callable, Any, Union
from collections import deque

from feedly_api.client import BaseAPIClient
from feedly_api.utils import not_none


class StreamID:
    """
    Parses stream ids in format:
     '[user|enterprise]/[user_id]/[source_type]/[source_id]'
    """
    def __init__(self,
                 stream_id: str,
                 source: str,
                 user_id: str,
                 source_type: str,
                 source_id: str):
        """
        :param stream_id: full id of stream
        :param source: either 'user' or 'enterprise'
        :param user_id: user id or enterprise name
        :param source_type: either 'category' or 'tag' or
        :param source_id: user-assigned label or uuid (for enterprise)
        """
        self.stream_id = stream_id
        self.source = source
        self.user_id = user_id
        self.source_type = source_type
        self.source_id = source_id

    @classmethod
    def from_id_string(cls, stream_id: str):
        pieces = stream_id.split('/')
        if len(pieces) != 4:
            raise ValueError(('id_ must be in format:\n[user|enterprise]/'
                              '[user_id]/[source_type]/[source_id]'))
        source, user_id, source_type, source_id = pieces
        if source == 'user':
            return UserStreamID(stream_id, source, user_id,
                                source_type, source_id)
        elif source == 'enterprise':
            return EnterpriseStreamID(stream_id, source, user_id,
                                      source_type, source_id)

    def is_category(self):
        return self.source_type == 'category'

    def is_tag(self):
        return self.source_type == 'tag'

    def __repr__(self):
        return f'<StreamID self.stream_id>'


class UserStreamID(StreamID):
    pass


class EnterpriseStreamID(StreamID):
    pass


class StreamOptions:
    """
    Container class for stream options outlined at
    https://developers.feedly.com/v3/streams/
    """
    def __init__(self,
                 count: int = 20,
                 ranked: str = 'newest',
                 unread_only: bool = False,
                 newer_than: int = None,
                 max_count: int = 100,
                 continuation: str = '',
                 show_muted: bool = False,
                 important_only: bool = False,):
        self.count = count
        self.ranked = ranked
        self.unread_only = unread_only
        self.newer_than = newer_than
        self.max_count = max_count
        self.continuation = continuation
        self.show_muted = show_muted
        self.important_only = important_only

    def get_options(self):
        options = dict(count=self.count,
                       ranked=self.ranked,
                       unreadOnly=self.unread_only,
                       newerThan=self.newer_than,
                       continuation=self.continuation,
                       showMuted=self.show_muted,
                       importantOnly=self.important_only)
        return not_none(options)


class Stream:
    def __init__(self,
                 client: BaseAPIClient,
                 stream_id: Union[StreamID, str],
                 options: StreamOptions,
                 stream_type: str,
                 item_prop: str,
                 item_factory: Callable[[str], Any]):
        self._client = client
        if isinstance(stream_id, StreamID):
            self.stream_id = stream_id
        else:
            self.stream_id = StreamID.from_id_string(stream_id)
        self.options = options
        self.stream_type = stream_type
        self.item_prop = item_prop
        self.item_factory = item_factory
        self.buffer = deque()

    def reset(self):
        self.options.continuation = ''

    def __iter__(self):
        logging.debug(f'downloading at most {self.options.max_count}'
                      f' articles in chunks of {self.options.count}')

        downloaded = 0
        while (downloaded < self.options.max_count
               and (self.options.continuation is not None or self.buffer)):
            while self.buffer:
                i = self.buffer.popleft()
                yield self.item_factory(i)
                downloaded += 1
                if downloaded == self.options.max_count:
                    break

            if (self.options.continuation is not None
                    and downloaded < self.options.max_count):
                resp = self._client.get_stream_contents(str(self.stream_id),
                                                        self.stream_type,
                                                        self.options).json()
                self.options.continuation = resp.get('continuation')
                if resp and self.item_prop in resp:
                    self.buffer = deque(resp.get(self.item_prop))
                    logging.debug(f'{len(self.buffer)} items (continuation='
                                  f'{self.options.continuation})')






