#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from productlib import PRODUCTS_FILE_ENV, ROOT, assert_marketplace_product, product_by_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("--target", choices=["Limited", "Public"], default="Public")
    parser.add_argument("--products-file", default=str(ROOT / "products.yaml"))
    parser.add_argument("--output-dir", default=str(ROOT / "plans"))
    args = parser.parse_args()

    os.environ[PRODUCTS_FILE_ENV] = args.products_file
    product = product_by_key(args.product_key)
    assert_marketplace_product(product)

    change_set = {
        "Catalog": product["_aws"]["marketplace_catalog"],
        "ChangeSet": [
            {
                "ChangeType": "UpdateVisibility",
                "Entity": {
                    "Type": "AmiProduct@1.0",
                    "Identifier": product["entity_id"],
                },
                "DetailsDocument": {"TargetVisibility": args.target},
            }
        ],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-visibility-{args.target.lower()}.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
