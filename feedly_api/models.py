from typing import Dict, Union, Sequence, Callable, List
import time
import logging
import json


from requests.models import Response


from feedly_api.client import BaseAPIClient
from feedly_api.exceptions import (UnauthorizedError,
                                   BadRequestError,
                                   NotFoundError,
                                   RateLimitError,
                                   APIServerError,
                                   HTTPError)
from feedly_api.utils import add_kwargs, quote, NoEmpty
from feedly_api.streams import (Stream, StreamOptions, StreamID,
                                UserStreamID, EnterpriseStreamID)


class Auth:
    """Container for authorization metadata"""
    def __init__(self,
                 client_id: str = 'feedlydev',
                 client_secret: str = 'feedlydev',
                 access_token: str = None,
                 refresh_token: str = None,
                 expires: float = None,
                 mode: str = 'developer'):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = access_token
        self.refresh_token = refresh_token
        self.expires = expires
        self.mode = mode
        if self.access_token:
            self.last_token_refresh_attempt = time.time()
        else:
            self.last_token_refresh_attempt = 0

    def refresh_data(self):
        if not self.refresh_token:
            raise AttributeError('Missing refresh token')
        return dict(refresh_token=self.refresh_token,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    grant_type='refresh_token')

    def revoke_data(self) -> Dict:
        return dict(refresh_token=self.refresh_token,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    grant_type='revoke_token')

    def clear_tokens(self):
        self.refresh_token = None
        self._access_token = None

    @property
    def access_token(self):
        return self._access_token

    @access_token.setter
    def access_token(self, new_token: str = None):
        if new_token:
            self._access_token = new_token
        self.last_token_refresh_attempt = time.time()

    def __repr__(self):
        return f'<Auth {self.client_id}>'


class FeedlyClient(BaseAPIClient):
    def __init__(self,
                 auth: Auth,
                 service_host: str,
                 user_id: str = None,
                 timeout: int = None,
                 retries: int = None):
        super().__init__(auth, service_host, timeout, retries)
        if self.auth.access_token:
            self.session.headers['Authorization'] = ' '.join(
                ['Bearer', self.auth.access_token]
            )
        self._user = User(user_id)

    @property
    def user(self):
        return self._user

    @user.setter
    def user(self, user_id: str = None):
        self._user = User(user_id)

    def __repr__(self):
        return f'<FeedlyClient {self.user} on {self.service_host}>'

    def handle(self,
               response: Response,
               method: str,
               endpoint: str,
               data: Dict,
               params: Dict,
               tries: int,
               timeout: int,
               retries: int) -> Response:
        try:
            return super().handle(response)
        except HTTPError as e:
            code = response.status_code
            if code == 400:
                error = BadRequestError(e)
            elif code == 401:
                if ('/v3/auth' not in response.url
                    and self.auth.refresh_token
                    and time.time()
                        - self.auth.last_token_refresh_attempt > 86400):
                    try:
                        self.refresh_token()
                    except HTTPError as e2:
                        logging.info('error refreshing access token',
                                     exc_info=e2)
                    else:
                        return self.api_request(method,
                                                endpoint,
                                                data=data,
                                                params=params,
                                                tries=tries+1,
                                                timeout=timeout,
                                                retries=retries)
                error = UnauthorizedError(e)
            elif code == 404:
                error = NotFoundError(e)
            elif code == 429:
                error = RateLimitError(e)
            elif code >= 500:
                error = APIServerError(e)
            else:
                error = e
        raise error

    def api_request(self,
                    method: str,
                    endpoint: str,
                    data: Dict = None,
                    params: Dict = None,
                    tries: int = 0,
                    timeout: int = None,
                    retries: int = None,
                    enterprise: bool = False,
                    **kwargs) -> Response:

        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint

        if not endpoint.startswith('/v3/'):
            raise ValueError(
                (f'Invalid endpoint: {endpoint} --'
                 ' See https://developers.feedly.com'))

        if enterprise:
            endpoint = endpoint[:4] + "enterprise/" + endpoint[4:]
        return super().api_request(method,
                                   endpoint,
                                   data,
                                   params,
                                   tries,
                                   timeout,
                                   retries,
                                   **kwargs)

    def get_auth_code(self, redirect_uri: str, **kwargs) -> Response:
        auth_data = dict(response_type='code',
                         client_id=self.auth.client_id,
                         redirect_uri=redirect_uri,
                         scope='https://cloud.feedly.com/subscriptions')
        auth_data = add_kwargs(kwargs, auth_data)
        auth_resp = self.get('/v3/auth/auth', params=auth_data)
        return auth_resp  # returns Feedly login page

    def get_auth_token(self, auth_code: str, redirect_uri: str):
        auth_data = dict(code=auth_code,
                         client_id=self.auth.client_id,
                         client_secret=self.auth.client_secret,
                         redirect_uri=redirect_uri,
                         grant_type='authorization_code')
        auth_response = self.post('/v3/auth/token',
                                  data=json.dumps(auth_data)).json()
        self.auth.access_token = auth_response['access_token']
        self.auth.refresh_token = auth_response['refresh_token']
        self.auth.expires = time.time() + float(auth_response['expires_in'])

    def refresh_token(self):
        refresh_response = self.post('/v3/auth/token',
                                     data=json.dumps(self.auth.refresh_data()))
        self.auth.access_token = refresh_response.json()['access_token']

    def revoke_refresh_token(self):
        self.post('/v3/auth/token',
                  data=self.auth.revoke_data())
        self.auth.clear_tokens()

    def log_out(self):
        self.post('/v3/auth/logout')
        self.auth.clear_tokens()

    def get_collections(self, *, enterprise: bool = False):
        response = self.get('/v3/collections', enterprise=enterprise)
        return [FeedlyCollection.from_json(data, self, enterprise)
                for data in response.json()]

    def get_personal_collections(self):
        return self.get_collections(enterprise=False)

    def get_enterprise_collections(self):
        return self.get_collections(enterprise=True)

    def get_collection(self, collection_id: str, *, enterprise: bool = False):
        response = self.get(f'/v3/collections/{quote(collection_id)}',
                            enterprise=enterprise)
        return FeedlyCollection.from_json(response.json(), self, enterprise)

    def get_personal_collection(self, collection_id: str):
        return self.get_collection(collection_id, enterprise=False)

    def get_enterprise_collection(self, collection_id: str):
        return self.get_collection(collection_id, enterprise=True)

    def create_or_update_collection(self,
                                    label: str = None,
                                    collection_id: str = None,
                                    description: str = None,
                                    feeds: List = None,
                                    delete_cover: bool = None,
                                    enterprise: bool = False):
        """Creates or updates a Feedly collection. To create a new
        collection, :label: (the name of the collection must be
        supplied. To update an existing collection, :collection_id: (the
        unique id for the collection -- use :self.get_collections: to
        find) is required; :label: is only necessary if you wish to
        change the existing label."""
        if (label is None) and (collection_id is None):
            raise ValueError("Must supply :label: or :collection_id:")
        collection_data = NoEmpty(label=label,
                                  id=collection_id,
                                  description=description,
                                  feeds=feeds,
                                  deleteCover=delete_cover)
        return self.post('/v3/collections',
                         data=json.dumps(collection_data),
                         enterprise=enterprise)

    def create_or_update_personal_collection(self,
                                             label: str = None,
                                             collection_id: str = None,
                                             description: str = None,
                                             feeds: List = None,
                                             delete_cover: bool = None):
        return self.create_or_update_collection(label,
                                                collection_id,
                                                description,
                                                feeds,
                                                delete_cover,
                                                enterprise=False)

    def create_or_update_enterprise_collection(self,
                                               label: str = None,
                                               collection_id: str = None,
                                               description: str = None,
                                               feeds: List = None,
                                               delete_cover: bool = None):
        return self.create_or_update_collection(label,
                                                collection_id,
                                                description,
                                                feeds,
                                                delete_cover,
                                                enterprise=True)

    def add_feed_collection(self,
                            collection_id: str,
                            feed_id: str,
                            title: str = None,
                            enterprise: bool = False):
        data = NoEmpty(id=feed_id, title=title)
        return self.put(f'/v3/collections/{quote(collection_id)}/feeds',
                        data=json.dumps(data),
                        enterprise=enterprise)

    def add_feed_personal_collection(self,
                                     collection_id: str,
                                     feed_id: str,
                                     title: str):
        return self.add_feed_collection(collection_id,
                                        feed_id,
                                        title,
                                        enterprise=False)

    def add_feed_enterprise_collection(self,
                                       collection_id: str,
                                       feed_id: str,
                                       title: str):
        return self.add_feed_collection(collection_id,
                                        feed_id,
                                        title,
                                        enterprise=True)

    def add_feeds_collection(self,
                             collection_id: str,
                             feeds: List[Dict],
                             enterprise: bool = False):
        return self.put(f'/v3/collections/{quote(collection_id)}/feeds/.mput',
                        data=json.dumps(feeds),
                        enterprise=enterprise)

    def add_feeds_personal_collection(self,
                                      collection_id: str,
                                      feeds: List[Dict]):
        return self.add_feeds_collection(collection_id,
                                         feeds,
                                         enterprise=False)

    def add_feeds_enterprise_collection(self,
                                        collection_id: str,
                                        feeds: List[Dict]):
        return self.add_feeds_collection(collection_id,
                                         feeds,
                                         enterprise=True)

    def remove_feed_collection(self,
                               collection_id: str,
                               feed_id: str,
                               keep_orphans: bool = None,
                               enterprise: bool = False):
        orphan_data = NoEmpty(keepOrphanFeeds=keep_orphans)
        self.delete(f'/v3/collections/{quote(collection_id)}/feeds/{feed_id}',
                    params=orphan_data,
                    enterprise=enterprise)

    def remove_feed_personal_collection(self,
                                        collection_id: str,
                                        feed_id: str,
                                        keep_orphans: bool = None):
        return self.remove_feed_collection(collection_id,
                                           feed_id,
                                           keep_orphans,
                                           enterprise=False)

    def remove_feed_enterprise_collection(self,
                                          collection_id: str,
                                          feed_id: str,
                                          keep_orphans: bool = None):
        return self.remove_feed_collection(collection_id,
                                           feed_id,
                                           keep_orphans,
                                           enterprise=True)

    def remove_feeds_collection(self,
                                collection_id: str,
                                feeds: List[Dict],
                                keep_orphans: bool = False,
                                enterprise: bool = False):
        orphan_data = NoEmpty(keepOrphanFeeds=keep_orphans)
        return self.delete(f'/v3/collections/{quote(collection_id)}/feeds/.mdelete',
                           data=json.dumps(feeds),
                           params=orphan_data,
                           enterprise=enterprise)

    def remove_feeds_personal_collection(self,
                                         collection_id: str,
                                         feeds: List[Dict],
                                         keep_orphans: bool = False):
        return self.remove_feeds_collection(collection_id,
                                            feeds,
                                            keep_orphans,
                                            enterprise=False)

    def remove_feeds_enterprise_collection(self,
                                           collection_id: str,
                                           feeds: List[Dict],
                                           keep_orphans: bool = False):
        return self.remove_feeds_collection(collection_id,
                                            feeds,
                                            keep_orphans,
                                            enterprise=True)

    def get_entry(self, entry_id: str):
        return Entry(self.get(f'/v3/entries/{entry_id}').json(), self)

    def get_entries(self, entry_ids: List[str]):
        return [Entry(entry) for entry
                in self.post('/v3/entries/.mget', data=json.dumps(entry_ids))]

    def create_and_tag_entry(self,
                             tags: List[Dict[str, str]],
                             title: str,
                             content: str,
                             origin: Dict[str, str],
                             alternate: List[Dict],
                             published: str,
                             crawled: str = None,
                             updated: str = None):
        entry_data = NoEmpty(tags=tags,
                             title=title,
                             content=content,
                             origin=origin,
                             alternate=alternate,
                             published=published,
                             crawled=crawled,
                             updated=updated)
        return self.post('/v3/entries', data=entry_data)

    def get_stream_contents(self,
                            stream_id: str,
                            stream_type: str,
                            options: StreamOptions):
        response = self.get(f'/v3/streams/{quote(stream_id)}/{stream_type}',
                            params=options.get_options())
        return response


class FeedlyData:
    def __init__(self,
                 json_data: Union[Dict, Sequence],
                 client: FeedlyClient):
        self._json = json_data
        self._client = client

    def _onchange(self):
        # sub classes should clear any cached items here
        pass

    @property
    def json(self):
        return self._json

    @json.setter
    def json(self, json_data):
        self._json = json_data
        self._onchange()

    def __getitem__(self, name):
        return self.json.get(name)
    '''
    def __getattribute__(self, item):
        try:
            super().__getattribute__(item)
        except AttributeError:
            return self[item]
    '''
    def __setitem__(self, key, value):
        self.json[key] = value

    def __repr__(self):
        return f'FeedlyData: {repr(self.json)}\n\n{repr(self._client)}'


class ContentStream(Stream):
    def __init__(self,
                 client: BaseAPIClient,
                 stream_id: Union[StreamID, str],
                 options: StreamOptions):
        super().__init__(client,
                         stream_id,
                         options,
                         'contents',
                         'items',
                         lambda x: x)


class IDStream(Stream):
    def __init__(self,
                 client: BaseAPIClient,
                 stream_id: Union[StreamID, str],
                 options: StreamOptions):
        super().__init__(client,
                         stream_id,
                         options,
                         'ids',
                         'ids',
                         lambda x: x)


class Streamable(FeedlyData):
    def stream(self,
               stream_type: Callable[
                   [BaseAPIClient,
                    Union[StreamID, str],
                    StreamOptions], Stream],
               options: StreamOptions = None):
        if not options:
            options = StreamOptions()
        return stream_type(self._client,
                           self.id,
                           options)

    def stream_ids(self, options: StreamOptions = None):
        return self.stream(IDStream, options)

    def stream_contents(self, options: StreamOptions = None):
        return self.stream(ContentStream, options)


class FeedlyCollection(Streamable):
    enterprise = False

    @classmethod
    def from_json(cls,
                  json_data: Union[Sequence, Dict],
                  client: FeedlyClient,
                  enterprise: bool = False):
        if enterprise:
            return EnterpriseFeedlyCollection(json_data, client)
        else:
            return PersonalFeedlyCollection(json_data, client)

    @property
    def label(self) -> str:
        return self['label']

    @property
    def description(self) -> str:
        return self['description']

    @property
    def cover(self) -> str:
        return self['cover']

    @property
    def created(self) -> int:
        return self['created']

    @property
    def feeds(self) -> List:
        return self['feeds']

    def update_collection(self,
                          label: str = None,
                          description: str = None,
                          feeds: List[str] = None,
                          delete_cover: bool = None):
        return self._client.create_or_update_collection(
            label,
            self._get_id(),
            description,
            feeds,
            delete_cover,
            self.enterprise,
        )

    def update_cover(self,
                     cover_file: str):
        file_data = {'file': open(cover_file, 'rb')}
        if self.enterprise:
            return self._client.post(
                f'/v3/enterprise/collections/{self._get_id()}',
                files=file_data
            )
        else:
            return self._client.post(
                f'/v3/collections/{self._get_id()}',
                files=file_data
            )

    def add_feed(self, feed_id: str, feed_title: str):
        return self._client.add_feed_collection(self._get_id(),
                                                feed_id,
                                                feed_title,
                                                enterprise=self.enterprise)

    def add_feeds(self, feeds: List[Dict]):
        return self._client.add_feeds_collection(self._get_id(),
                                                 feeds,
                                                 enterprise=self.enterprise)

    def remove_feed(self, feed_id: str, keep_orphans: bool = False):
        return self._client.remove_feed_collection(self._get_id(),
                                                   feed_id,
                                                   keep_orphans,
                                                   enterprise=self.enterprise)

    def remove_feeds(self, feeds: List[Dict], keep_orphans: bool = False):
        return self._client.remove_feeds_collection(self._get_id(),
                                                    feeds,
                                                    keep_orphans,
                                                    enterprise=self.enterprise)


class PersonalFeedlyCollection(FeedlyCollection):
    pass


class EnterpriseFeedlyCollection(FeedlyCollection):
    enterprise = True


class Entry(FeedlyData):
    def _update(self):
        self._json = self._client.get(f'/v3/entries/{self.id}')

class User:
    def __init__(self, user_id):
        self.user_id = user_id


