import asyncio
import logging
from typing import Tuple, TypeVar

import amazon
import woocom
import storage
from util import groupby_single

_AMAZON_INVENTORY_FILE = "amazon_inventory.json"
_WOOCOM_INVENTORY_FILE = "woocom_inventory.json"

Item = TypeVar('Item', amazon.Item, woocom.Item)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await bidirectional_sync()


async def bidirectional_sync() -> None:
    # get stored inventory levels
    old_amazon_inv = storage.load_list(_AMAZON_INVENTORY_FILE, amazon.Item)
    old_woocom_inv = storage.load_list(_WOOCOM_INVENTORY_FILE, woocom.Item)

    # get current reported levels
    amazon_inv = await amazon.get_inventory()
    woocom_inv = await woocom.list_products_with_non_null_stock()

    # figure out which items are present on both platforms
    amazon_by_sku, woocom_by_sku, common_skus = \
        arrange_by_sku(amazon_inv, woocom_inv)

    # figure out how much stock levels have changed by
    amazon_deltas = get_deltas(old_amazon_inv, amazon_by_sku, common_skus)
    woocom_deltas = get_deltas(old_woocom_inv, woocom_by_sku, common_skus)
    logging.info(f'amazon deltas: {amazon_deltas}')
    logging.info(f'woocom deltas: {woocom_deltas}')

    # apply deltas from each marketplace to the other
    new_amazon_inv, amazon_changes = apply_deltas(woocom_deltas, amazon_inv)
    new_woocom_inv, woocom_changes = apply_deltas(amazon_deltas, woocom_inv)

    # push changes to marketplaces and save new levels
    # TODO: woocommerce items with None inventories should get the amazon level
    # TODO: woocommerce items with manage_stock off should have it turned on
    if woocom_deltas:
        await amazon.put_inventory(amazon_changes)
        save_inventory(new_amazon_inv, _AMAZON_INVENTORY_FILE)
    if amazon_deltas:
        await woocom.batch_update_stock({
            item.id: item.stock_quantity
            for item in woocom_changes
        })
        save_inventory(new_woocom_inv, _WOOCOM_INVENTORY_FILE)


def arrange_by_sku(amazon_inv: list[amazon.Item], woocom_inv: list[woocom.Item]) \
        -> Tuple[dict[str, amazon.Item], dict[str, woocom.Item], set[str]]:
    amazon_by_sku = groupby_single(lambda x: x.sku, amazon_inv)
    woocom_by_sku = groupby_single(lambda x: x.sku, woocom_inv)
    common_skus = set(amazon_by_sku.keys()) & set(woocom_by_sku.keys())
    return amazon_by_sku, woocom_by_sku, common_skus


def get_deltas(old_inv: list[Item], inv_by_sku: dict[str, Item], common_skus: set[str]) \
        -> dict[str, int]:
    """Returns a map of SKUs to stock deltas."""
    return {
        item.sku: inv_by_sku[item.sku].stock_quantity - item.stock_quantity
        for item in old_inv
        if item.sku in common_skus
    }


def apply_deltas(deltas: dict[str, int], inv: list[Item]) -> Tuple[list[Item], list[Item]]:
    """
    Given a list of items and a map of SKUs to stock deltas, returns a
    list of all items with adjusted quantities, and a list of only
    items that changed.
    """
    all = [item._replace(stock_quantity=item.stock_quantity
                         + deltas.get(item.sku, 0))
           for item in inv]
    changes = [item._replace(stock_quantity=item.stock_quantity
                             + deltas[item.sku])
               for item in inv
               if deltas.get(item.sku, 0) != 0]
    return all, changes


def save_inventory(inv: list[amazon.Item] | list[woocom.Item], path: str) \
        -> None:
    data = [x._asdict() for x in inv]
    storage.save(data, path)


if __name__ == '__main__':
    asyncio.new_event_loop().run_until_complete(main())
