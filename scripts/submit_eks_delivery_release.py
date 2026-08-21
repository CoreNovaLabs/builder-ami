#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from productlib import PRODUCTS_FILE_ENV, fail, load_config
from submit_changeset import assert_allowed_change_set, assert_eks_delivery_plan


PUBLISHER_ROLE_NAME = "CoreNovaMarketplaceDeliveryPublisherRole"
PRODUCT_IDS = {"prod-hapxotc2y7jmi", "prod-nspz2g6ki6qvo"}
CHANGE_SET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_caller(account_id: str) -> None:
    identity = json.loads(
        subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--output", "json"], text=True
        )
    )
    arn = str(identity.get("Arn") or "")
    if identity.get("Account") != account_id:
        fail("unexpected AWS account")
    if f":assumed-role/{PUBLISHER_ROLE_NAME}/" not in arn:
        fail(f"APPLY requires an assumed {PUBLISHER_ROLE_NAME} session")


def assert_release(plan_path: Path, evidence_path: Path, expected_sha: str) -> dict:
    data = assert_allowed_change_set(plan_path)
    assert_eks_delivery_plan(data)
    changes = data.get("ChangeSet") or []
    if len(changes) != 2 or {item.get("ChangeType") for item in changes} != {
        "AddDeliveryOptions"
    }:
        fail("release plan must contain exactly two AddDeliveryOptions changes")
    identifiers = {
        str((item.get("Entity") or {}).get("Identifier") or "").split("@", 1)[0]
        for item in changes
    }
    if identifiers != PRODUCT_IDS:
        fail("release plan must target both guarded EKS products")
    titles = {
        str(((item.get("DetailsDocument") or {}).get("Version") or {}).get("VersionTitle") or "")
        for item in changes
    }
    if len(titles) != 1:
        fail("both products must use one version title")

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    expected = {
        "status": "SUCCEEDED",
        "commit": expected_sha,
        "plan_sha256": sha256(plan_path),
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            fail(f"validation evidence {key} does not match the release plan")
    change_set_id = str(evidence.get("change_set_id") or "")
    if not CHANGE_SET_ID_PATTERN.fullmatch(change_set_id):
        fail("validation evidence is missing the Catalog change-set ID")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--validation-evidence", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--products-file", default="products.candidates.yaml")
    parser.add_argument("--confirm-apply", action="store_true")
    args = parser.parse_args()
    if not args.confirm_apply:
        fail("APPLY requires --confirm-apply")
    if len(args.expected_sha) != 40 or any(c not in "0123456789abcdef" for c in args.expected_sha):
        fail("expected SHA must be a 40-character lowercase commit hash")
    if os.environ.get("GITHUB_SHA") != args.expected_sha:
        fail("GITHUB_SHA does not match the approved release commit")

    os.environ[PRODUCTS_FILE_ENV] = args.products_file
    config = load_config()
    plan_path = Path(args.plan)
    data = assert_release(
        plan_path, Path(args.validation_evidence), args.expected_sha
    )
    assert_caller(str(config["aws"]["seller_account_id"]))
    result = subprocess.check_output(
        [
            "aws",
            "marketplace-catalog",
            "start-change-set",
            "--catalog",
            data["Catalog"],
            "--change-set",
            json.dumps(data["ChangeSet"]),
            "--intent",
            "APPLY",
            "--output",
            "json",
        ],
        text=True,
    )
    print(result, end="")


if __name__ == "__main__":
    main()
