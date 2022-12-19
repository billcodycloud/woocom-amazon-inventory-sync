import json
import logging
from os import path
from typing import Any, Callable, TypeVar

_DIR = "storage"
_INDENT = '  '

T = TypeVar('T')


def load_list(filename: str, fn: Callable[..., T]) -> list[T]:
    try:
        with open(path.join(_DIR, filename)) as f:
            data = [fn(**d) for d in json.load(f)]
            logging.info(f'loaded {filename}')
            return data
    except FileNotFoundError:
        logging.warning(f'{filename} not found, returning empty list')
        return []


def load(filename: str, fn: Callable[..., T]) -> T | None:
    try:
        with open(path.join(_DIR, filename)) as f:
            data = fn(**json.load(f))
            logging.info(f'loaded {filename}')
            return data
    except FileNotFoundError:
        logging.warning(f'{filename} not found, returning None')
        return None


def save(data: list | dict, filename: str) -> None:
    with open(path.join(_DIR, filename), 'w') as f:
        json.dump(data, f, indent=_INDENT)
    logging.info(f'saved {filename}')
