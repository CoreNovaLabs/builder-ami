#!/usr/bin/env python3
import argparse

from productlib import assert_marketplace_product, is_placeholder_entity, load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List configured products and optionally verify them against AWS Marketplace."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Validate and list the local product configuration without calling AWS.",
    )
    args = parser.parse_args()

    config = load_config()
    for product in config["products"]:
        product = dict(product)
        product["_aws"] = config["aws"]
        if not args.offline and not is_placeholder_entity(product.get("entity_id")):
            assert_marketplace_product(product)
        print(f"{product['key']}\t{product['entity_id']}\t{product['title']}")


if __name__ == "__main__":
    main()
