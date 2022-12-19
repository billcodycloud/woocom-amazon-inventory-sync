"""Module for WooCommerce API code."""

from functools import cache
import logging
from typing import NamedTuple

from requests import Response
from woocommerce import API as WCAPI

WOOCOMMERCE_URL = 'https://sportsrings.link/'
WOOCOMMERCE_CONSUMER_KEY = 'ck_768a2449b1dc7133899c4f31ccbe158de34ec78a'
WOOCOMMERCE_CONSUMER_SECRET = 'cs_76b87cfdf44361c56ec7cb957b8f03c31ad3aec3'


@cache
def _client() -> WCAPI:
    """Returns a new API client."""
    return WCAPI(
        url=WOOCOMMERCE_URL,
        consumer_key=WOOCOMMERCE_CONSUMER_KEY,
        consumer_secret=WOOCOMMERCE_CONSUMER_SECRET,
    )


class Item(NamedTuple):
    """Contains data from a get_products response."""
    id: int
    name: str
    sku: str
    stock_quantity: int  # can technically be None
    manage_stock: bool


def _namedtuple_from_dict(d: dict, t):
    """Constructs a NamedTuple of type `t` using mappings from `d`."""
    return t(**{k: d[k] for k in t._fields})


def _get(endpoint: str) -> Response:
    """Issues a GET request to the API."""
    logging.info(f'GET {endpoint}')
    r = _client().get(endpoint)
    logging.debug(f'GET {endpoint} -> {r.text}')
    return r


def _post(endpoint: str, data: dict) -> Response:
    """Issues a POST request to the API."""
    logging.info(f'POST {endpoint}')
    logging.debug(f'POST {endpoint} <- {data}')
    r = _client().post(endpoint, data)
    logging.debug(f'POST {endpoint} -> {r.text}')
    return r


def _put(endpoint: str, data: dict) -> Response:
    """Issues a PUT request to the API."""
    logging.info(f'PUT {endpoint}')
    logging.debug(f'PUT {endpoint} <- {data}')
    r = _client().put(endpoint, data)
    logging.debug(f'PUT {endpoint} -> {r.text}')
    return r


async def list_all_products() -> list[Item]:
    """Retrieves a list of all products."""
    r = _get('products')
    return [_namedtuple_from_dict(d, Item) for d in r.json()]


async def list_products_with_non_null_stock() -> list[Item]:
    """Retrieves a list of all products with non-null stock quantities."""
    return [p for p in await list_all_products()
            if p.stock_quantity is not None]


def _batch_update_products(data: dict) -> Response:
    """Batch create, update, and/or delete multiple products."""
    return _post('products/batch', data)


async def set_manage_stock(value: bool = True) -> Response:
    """Turns manage_stock on for all products where it is off."""
    products = await list_all_products()
    unmanaged_products = [p for p in products if p.manage_stock != value]
    return _batch_update_products({
        'update': [{'id': p.id, 'manage_stock': value}
                   for p in unmanaged_products],
    })


async def update_stock(id: int, quantity: int) -> Response:
    return _put(f'products/{id}', {'id': id, 'stock_quantity': quantity})


async def batch_update_stock(id_to_quantity: dict[int, int]) -> Response:
    return _batch_update_products({
        'update': [{'id': id, 'stock_quantity': quantity}
                   for id, quantity in id_to_quantity.items()],
    })
