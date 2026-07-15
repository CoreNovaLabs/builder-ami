#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from productlib import ROOT, assert_marketplace_product, latest_version, load_config


def main() -> None:
    config = load_config()
    output = []
    for product in config["products"]:
        product = dict(product)
        product["_aws"] = config["aws"]
        described = assert_marketplace_product(product)
        version = latest_version(described["details"])
        source = version["Sources"][0]
        delivery = version["DeliveryOptions"][0]
        output.append(
            {
                "key": product["key"],
                "title": product["title"],
                "entity_id": product["entity_id"],
                "entity_identifier": described["entity"]["EntityIdentifier"],
                "visibility": described["details"]["Description"]["Visibility"],
                "product_state": described["details"]["Description"]["ProductState"],
                "latest_version_title": version["VersionTitle"],
                "latest_ami_id": source["Image"],
                "latest_architecture": source["Architecture"],
                "latest_delivery_option_id": delivery["Id"],
                "recommended_instance_type": delivery["Recommendations"]["InstanceType"],
            }
        )
    out = ROOT / "inventory" / "marketplace-products.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
