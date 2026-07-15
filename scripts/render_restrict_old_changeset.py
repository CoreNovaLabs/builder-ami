#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from productlib import ROOT, assert_marketplace_product, latest_version, product_by_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("--output-dir", default=str(ROOT / "plans"))
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    details = assert_marketplace_product(product)["details"]
    old_id = product.get("legacy", {}).get("delivery_option_id")
    public_ids = []
    for version in details.get("Versions", []):
        for delivery in version.get("DeliveryOptions", []):
            if delivery.get("Visibility") == "Public":
                public_ids.append(delivery["Id"])
    if old_id not in public_ids:
        raise SystemExit(f"legacy delivery option {old_id} is not public/currently restrictable")
    if len(public_ids) <= 1:
        raise SystemExit("refusing to restrict the last public delivery option; add a new version first")

    change_set = {
        "Catalog": product["_aws"]["marketplace_catalog"],
        "ChangeSet": [
            {
                "ChangeType": "RestrictDeliveryOptions",
                "Entity": {"Type": "AmiProduct@1.0", "Identifier": product["entity_id"]},
                "DetailsDocument": {"DeliveryOptionIds": [old_id]},
            }
        ],
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-restrict-old.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
