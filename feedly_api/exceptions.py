import json
from datetime import datetime as dt


from requests.exceptions import HTTPError


class FeedlyAPIException(HTTPError):
    def __init__(self, http_error: HTTPError, reason: str = None):
        self.request = http_error.request
        self.response = http_error.response
        self.reason = reason
        super().__init__(self.get_reason(),
                         request=self.request,
                         response=self.response)

    def get_reason(self) -> str:
        if self.reason:
            return self.reason
        base_reason = f"{self.response.status_code}: {self.response.reason}"
        try:
            response_data = self.response.json()
            error_id = response_data.get('errorId')
            error_message = response_data.get('errorMessage')
            if error_id and error_message:
                return base_reason + f' Error {error_id}: {error_message}'
            else:
                return base_reason
        except (AttributeError, json.JSONDecodeError):
            return base_reason


class UnauthorizedError(FeedlyAPIException):
    """Raise for status code 401"""
    pass


class BadRequestError(FeedlyAPIException):
    """Raise for status code 400"""
    pass


class NotFoundError(FeedlyAPIException):
    """Raise for status code 404"""
    pass


class RateLimitError(FeedlyAPIException):
    """Raise for status code 429"""
    def get_reason(self) -> str:
        base_reason = super().get_reason()
        refresh_time = self.response.headers.get('Retry-After')
        try:
            refresh_time = int(refresh_time)
            refresh_time = dt.fromtimestamp(refresh_time).strftime(
                '%H:%M:%S %d %b %Y')
            return base_reason + f"Rate limit resets on {refresh_time}"
        except ValueError:
            return base_reason


class APIServerError(FeedlyAPIException):
    """Raise for status codes >= 500"""
    pass

