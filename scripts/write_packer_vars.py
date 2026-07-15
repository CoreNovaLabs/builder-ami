#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from productlib import product_by_key


def hcl_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("source_ami_id")
    parser.add_argument("version_title")
    parser.add_argument("output")
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    values = {
        "region": product["_aws"]["region"],
        "product_key": product["key"],
        "product_title": product["title"],
        "product_profile": product.get("profile", "hardened-linux"),
        "source_ami_id": args.source_ami_id,
        "ssh_username": product["ssh_username"],
        "architecture": product["architecture"],
        "layout": product["layout"],
        "filesystem": product["filesystem"],
        "version_title": args.version_title,
        "build_instance_type": product["build_instance_type"],
        "root_device_name": product["root_device_name"],
        "root_volume_size": int(product["root_volume_size"]),
        "build_subnet_id": product["_aws"]["build_subnet_id"],
    }

    lines = []
    for key, value in values.items():
        if isinstance(value, int):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f"{key} = {hcl_string(str(value))}")
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
