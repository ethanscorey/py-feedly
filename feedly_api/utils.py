from urllib.parse import quote as qt
from typing import Dict, Union, Iterable


def quote(string: str, **kwargs):
    return qt(string, safe='', **kwargs)


def add_kwargs(kwargs: Dict, data: Dict):
    for key in kwargs:
        data[key] = kwargs[key]
    return data


def to_camel(string: str):
    """Converts lower-case underscore string to camel-case"""
    pieces = string.split('_')
    if len(pieces) == 1:
        return string
    capitalized = [i[0].upper() + i[1:] for i in pieces[1:]]
    return ''.join(pieces[:1]+capitalized)


def not_none(data: Dict):
    return dict((k, v) for k, v in data.items() if v is not None)


class NoEmpty(dict):
    def __init__(self, val: Union[Iterable, Dict] = None, **kwargs):
        super().__init__(self)
        try:
            for k, v in val:
                if v is not None:
                    self[k] = v
        except (ValueError, TypeError):
            pass
        finally:
            for k, v in kwargs.items():
                if v is not None:
                    self[k] = v
