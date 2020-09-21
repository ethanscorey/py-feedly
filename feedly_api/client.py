import logging
from typing import Dict, Any
import re


from requests import Session
from requests.models import Response
from requests.exceptions import HTTPError


class BaseAPIClient:
    """A generic API client"""
    timeout = 10
    retries = 3

    def __init__(self,
                 auth: Any = None,
                 service_host: str = 'localhost',
                 timeout: int = None,
                 retries: int = None,
                 data_encoding: str = 'application/json'):
        self.auth = auth
        if service_host[-1] == '/':
            service_host = service_host[:-1]
        self.service_host = service_host
        if timeout:
            self.timeout = timeout
        if retries:
            self.retries = retries
        self.data_encoding = data_encoding
        self.session = Session()

    def __repr__(self):
        return f'<BaseAPIClient on {self.service_host}'

    def close(self):
        self.session.close()
        self.session = None

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()

    def _get_url(self, endpoint: str) -> str:
        if not endpoint.startswith('/'):
            return f"https://{self.service_host}/{endpoint}"
        else:
            return f"https://{self.service_host}{endpoint}"

    def handle(self, response: Response, *args, **kwargs) -> Response:
        response.raise_for_status()
        return response

    def api_request(self,
                    method: str,
                    endpoint: str,
                    data: Dict = None,
                    params: Dict = None,
                    tries: int = 0,
                    timeout: int = None,
                    retries: int = None,
                    **kwargs) -> Response:
        method = method.upper()

        if timeout is None:
            timeout = self.timeout

        if retries is None:
            retries = self.retries

        if method not in ('GET', 'POST', 'PUT', 'DELETE'):
            raise ValueError(f'Invalid method: {method} '
                             'Please use GET, POST, PUT, or DELETE.')

        response = None
        try:
            if data:
                headers = {'Content-Type': self.data_encoding}
                response = self.session.request(method,
                                                self._get_url(endpoint),
                                                params=params,
                                                headers=headers,
                                                data=data,
                                                timeout=timeout,
                                                **kwargs)
            else:
                response = self.session.request(method,
                                                self._get_url(endpoint),
                                                params=params,
                                                timeout=timeout,
                                                **kwargs)
        except OSError as e:
            conn_error: Exception = e
        else:
            return self.handle(response,
                               method,
                               endpoint,
                               data,
                               params,
                               tries,
                               timeout,
                               retries,
                               **kwargs)
        if tries >= retries:
            raise conn_error
        else:
            try:
                response.raise_for_status()
            except HTTPError:
                return self.handle(response,
                                   method,
                                   endpoint,
                                   data,
                                   params,
                                   tries,
                                   timeout,
                                   retries,
                                   **kwargs)
            except AttributeError:  # means response is None
                logging.warning(f'No response received for {endpoint}')
            finally:
                logging.warning(f'Error for {endpoint}: {conn_error}')
                return self.api_request(method,
                                        endpoint,
                                        data,
                                        params,
                                        tries=tries + 1,
                                        timeout=timeout,
                                        retries=retries,
                                        **kwargs)

    def get(self,
            endpoint: str,
            params: Dict = None,
            timeout: int = timeout,
            retries: int = retries,
            **kwargs) -> Response:
        return self.api_request('GET',
                                endpoint=endpoint,
                                params=params,
                                timeout=timeout,
                                retries=retries,
                                **kwargs)

    def post(self,
             endpoint: str,
             data: Dict = None,
             params: Dict = None,
             timeout: int = timeout,
             retries: int = retries,
             **kwargs) -> Response:
        return self.api_request('POST',
                                endpoint=endpoint,
                                data=data,
                                params=params,
                                timeout=timeout,
                                retries=retries,
                                **kwargs)

    def put(self,
            endpoint: str,
            data: Dict = None,
            params: Dict = None,
            timeout: int = timeout,
            retries: int = retries,
            **kwargs) -> Response:
        return self.api_request('PUT',
                                endpoint=endpoint,
                                data=data,
                                params=params,
                                timeout=timeout,
                                retries=retries,
                                **kwargs)

    def delete(self,
               endpoint: str,
               data: Dict = None,
               params: Dict = None,
               timeout: int = timeout,
               retries: int = retries,
               **kwargs) -> Response:
        return self.api_request('DELETE',
                                endpoint=endpoint,
                                data=data,
                                params=params,
                                timeout=timeout,
                                retries=retries,
                                **kwargs)



