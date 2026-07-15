#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from productlib import ROOT, is_placeholder_entity, product_by_key
from render_create_ami_product_changeset import product_descriptions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("--entity-id")
    parser.add_argument("--products-file", default=str(ROOT / "products.candidates.yaml"))
    parser.add_argument("--output-dir", default=str(ROOT / "plans" / "metadata-updates"))
    args = parser.parse_args()

    os.environ["CORENOVA_PRODUCTS_FILE"] = args.products_file
    product = product_by_key(args.product_key)
    entity_id = args.entity_id or product.get("entity_id")
    if is_placeholder_entity(entity_id):
        raise SystemExit(f"entity id required for {args.product_key}")

    change_set = {
        "Catalog": product["_aws"]["marketplace_catalog"],
        "ChangeSet": [
            {
                "ChangeType": "UpdateInformation",
                "Entity": {"Type": "AmiProduct@1.0", "Identifier": entity_id},
                "DetailsDocument": product_descriptions(product),
            }
        ],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-metadata-update.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
