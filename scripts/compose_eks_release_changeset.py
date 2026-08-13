#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


PRODUCT_IDS = {"prod-hapxotc2y7jmi", "prod-nspz2g6ki6qvo"}


def compose(paths: list[Path]) -> dict:
    if len(paths) != 2:
        raise ValueError("exactly two architecture plans are required")
    changes: list[dict] = []
    catalogs: set[str] = set()
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        catalogs.add(str(data.get("Catalog") or ""))
        plan_changes = data.get("ChangeSet") or []
        if len(plan_changes) != 1:
            raise ValueError(f"{path}: expected one change")
        change = plan_changes[0]
        if change.get("ChangeType") != "AddDeliveryOptions":
            raise ValueError(f"{path}: expected AddDeliveryOptions")
        if len((change.get("DetailsDocument") or {}).get("DeliveryOptions") or []) != 3:
            raise ValueError(f"{path}: expected three delivery options")
        changes.append(change)
    if catalogs != {"AWSMarketplace"}:
        raise ValueError("plans must use AWSMarketplace")
    identifiers = {
        str((change.get("Entity") or {}).get("Identifier") or "").split("@", 1)[0]
        for change in changes
    }
    if identifiers != PRODUCT_IDS:
        raise ValueError("plans must target exactly the x86_64 and ARM64 EKS products")
    versions = {
        str(((change.get("DetailsDocument") or {}).get("Version") or {}).get("VersionTitle") or "")
        for change in changes
    }
    if len(versions) != 1 or not next(iter(versions)).startswith("v"):
        raise ValueError("both products must use one fixed version title")
    changes.sort(key=lambda item: item["Entity"]["Identifier"])
    return {"Catalog": "AWSMarketplace", "ChangeSet": changes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plans", nargs=2)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(compose([Path(item) for item in args.plans]), indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
