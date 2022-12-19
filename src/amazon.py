"""Module for Amazon SP-API code."""

import csv
from datetime import datetime, timedelta
from functools import cache
from io import StringIO
import logging
from typing import Callable, Iterator, NamedTuple, TypeVar
from time import sleep

from sp_api.base import Marketplaces, ReportType, FeedType
from sp_api.api import Feeds, Reports

import storage

_CREDENTIALS = {
    'lwa_app_id': 'amzn1.application-oa2-client.dd4c6fbf89d54f0a969959e7f68f5db8',
    'lwa_client_secret': 'lwa_client_secret',
    'aws_access_key': 'awsaccesskey',
    'aws_secret_key': 'awssecret/key',
    'refresh_token': 'refreshtoken',
    'role_arn': 'arn:aws:iam::037365653055:role/discountsportsrings-inven-sync',
}
_MARKETPLACE = Marketplaces.US
_MAX_RETRIES = 5
_RETRY_INTERVAL = 10
_SELLER_ID = 'AXXDB5RWJYYHI'
_DOCUMENT_STORE_FILE = 'amazon_document.json'
_DOCUMENT_EXPIRATION_INTERVAL = timedelta(hours=1)
_XML_TEMPLATE = """
<?xml version="1.0" encoding="iso-8859-1"?>
<AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">
  <Header>
    <DocumentVersion>1.01</DocumentVersion>
    <MerchantIdentifier>{merchant_identifier}</MerchantIdentifier>
  </Header>
  <MessageType>Inventory</MessageType>
  <PurgeAndReplace>false</PurgeAndReplace>
  <Message>
    <MessageID>1</MessageID>
    <OperationType>Update</OperationType>
    <Inventory>
      <SKU>{sku}</SKU>
      <Quantity>{quantity}</Quantity>
    </Inventory>
  </Message>
</AmazonEnvelope>
"""


@cache
def _feeds_client() -> Feeds:
    return Feeds(credentials=_CREDENTIALS, marketplace=_MARKETPLACE)


@cache
def _reports_client() -> Reports:
    return Reports(credentials=_CREDENTIALS, marketplace=_MARKETPLACE)


def _create_merchant_listings_report() -> str:
    logging.info('creating merchant listings report')
    return _reports_client().create_report(
        reportType=ReportType.GET_MERCHANT_LISTINGS_ALL_DATA,
    ).payload['reportId']


def _get_report_document_id(id: str) -> str | None:
    logging.info(f'retrieving report document ID: {id}')
    r = _reports_client().get_report(id)
    if r.payload['processingStatus'] == 'DONE':
        return r.payload['reportDocumentId']


def _get_report_document(id: str) -> StringIO | None:
    logging.info(f'retrieving report document: {id}')
    f = StringIO()
    r = _reports_client().get_report_document(id, download=True, file=f)
    if 'url' in r.payload:
        return f


T = TypeVar('T')


def _retry(f: Callable[[], T | None]) -> T:
    for i in range(_MAX_RETRIES):
        match f():
            case None: pass
            case v: return v
        logging.info('request returned None; '
                     f'waiting {_RETRY_INTERVAL} seconds')
        sleep(_RETRY_INTERVAL)
    raise Exception('max retries reached')


class Item(NamedTuple):
    name: str
    sku: str
    stock_quantity: int


class DocumentStorage(NamedTuple):
    url: str
    created: str

    def created_datetime(self) -> datetime:
        return datetime.fromisoformat(self.created)

    def expired(self) -> bool:
        return datetime.now() - self.created_datetime() \
            > _DOCUMENT_EXPIRATION_INTERVAL


async def get_inventory() -> list[Item]:
    doc_store = storage.load(_DOCUMENT_STORE_FILE, DocumentStorage)
    if doc_store is None or doc_store.expired():
        logging.info('stored document URL expired; creating new report')
        report_id = _create_merchant_listings_report()
        document_id = _retry(lambda: _get_report_document_id(report_id))
        new_store = DocumentStorage(document_id, datetime.now().isoformat())
        storage.save(new_store._asdict(), _DOCUMENT_STORE_FILE)
    else:
        logging.info('using stored document URL')
        document_id = doc_store.url
    with _retry(lambda: _get_report_document(document_id)) as document:
        return _parse_merchant_listings_report(document)


def _parse_merchant_listings_report(document: Iterator[str]) -> list[Item]:
    rows = [row for row in csv.reader(document, delimiter='\t')]
    keys = ['item-name', 'seller-sku', 'quantity']
    indices = {k: rows[0].index(k) for k in keys}

    def parse_item(row: list[str]) -> Item:
        return Item(
            name=row[indices['item-name']],
            sku=row[indices['seller-sku']],
            stock_quantity=int(row[indices['quantity']]),
        )
    return [parse_item(row) for row in rows[1:]]


# XXX: not tested!
async def put_inventory(changed_items: list[Item]) -> None:
    logging.info('updating amazon inventory')
    xml = _XML_TEMPLATE.format(
        merchant_identifier=_SELLER_ID,
        sku=changed_items[0].sku,
        quantity=changed_items[0].stock_quantity,
    )
    r = _feeds_client().submit_feed(FeedType.POST_INVENTORY_AVAILABILITY_DATA,
                                    xml, 'test/xml')
    print(r.json())
