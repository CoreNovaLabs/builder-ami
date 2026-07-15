#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from productlib import ROOT, load_config, product_by_key
from submit_changeset import assert_allowed_change_set


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = utc_now()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def aws_json(args: list[str], *, region: str) -> dict[str, Any]:
    cmd = ["aws", *args, "--region", region, "--output", "json"]
    try:
        output = subprocess.check_output(
            cmd,
            cwd=str(ROOT),
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.output, file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
    return json.loads(output)


def list_products(*, region: str, catalog: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        args = [
            "marketplace-catalog",
            "list-entities",
            "--catalog",
            catalog,
            "--entity-type",
            "AmiProduct",
            "--ownership-type",
            "SELF",
            "--max-results",
            "50",
        ]
        if next_token:
            args.extend(["--next-token", next_token])
        response = aws_json(args, region=region)
        entities.extend(response.get("EntitySummaryList") or [])
        next_token = response.get("NextToken")
        if not next_token:
            return entities


def product_visibility(product_key: str, *, region: str, catalog: str) -> str:
    product = product_by_key(product_key)
    for entity in list_products(region=region, catalog=catalog):
        if entity.get("EntityId") == product["entity_id"]:
            summary = entity.get("AmiProductSummary") or {}
            return entity.get("Visibility") or summary.get("Visibility") or "UNKNOWN"
    return "NOT_FOUND"


def load_or_init_state(path: Path, queue: list[str]) -> dict[str, Any]:
    for key in queue:
        product_by_key(key)

    state = read_json(path)
    if state is None:
        return {
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "queue": queue,
            "current": None,
            "completed": [],
            "failed": [],
            "history": [],
        }

    known = set(state.get("queue") or [])
    for key in queue:
        if key not in known:
            state.setdefault("queue", []).append(key)
    return state


def keys_from(entries: list[dict[str, Any]]) -> set[str]:
    return {entry["key"] for entry in entries if entry.get("key")}


def record_history(state: dict[str, Any], event: dict[str, Any]) -> None:
    event.setdefault("time", utc_now())
    state.setdefault("history", []).append(event)


def describe_change_set(change_set_id: str, *, region: str, catalog: str) -> dict[str, Any]:
    return aws_json(
        [
            "marketplace-catalog",
            "describe-change-set",
            "--catalog",
            catalog,
            "--change-set-id",
            change_set_id,
        ],
        region=region,
    )


def submit_visibility_change(product_key: str, *, target: str, region: str) -> str:
    render_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "render_visibility_changeset.py"),
        product_key,
        "--target",
        target,
    ]
    rendered = subprocess.check_output(render_cmd, cwd=str(ROOT), text=True).strip()
    plan_path = Path(rendered.splitlines()[-1])
    data = assert_allowed_change_set(plan_path)

    response = aws_json(
        [
            "marketplace-catalog",
            "start-change-set",
            "--catalog",
            data["Catalog"],
            "--change-set",
            json.dumps(data["ChangeSet"]),
            "--intent",
            "APPLY",
        ],
        region=region,
    )
    return response["ChangeSetId"]


def current_done(state: dict[str, Any], *, region: str, catalog: str) -> bool:
    current = state.get("current")
    if not current:
        return True

    key = current["key"]
    change_set_id = current["change_set_id"]
    change_set = describe_change_set(change_set_id, region=region, catalog=catalog)
    status = change_set.get("Status", "UNKNOWN")

    current["last_status"] = status
    current["last_checked_at"] = utc_now()

    if status not in TERMINAL_STATUSES:
        print(f"{key}: change set {change_set_id} is {status}")
        return False

    if status == "SUCCEEDED":
        visibility = product_visibility(key, region=region, catalog=catalog)
        if visibility != "Public":
            current["awaiting_public_visibility_since"] = current.get(
                "awaiting_public_visibility_since", utc_now()
            )
            print(
                f"{key}: change set {change_set_id} succeeded; "
                f"current visibility is {visibility}, waiting for Public"
            )
            return False

        state.setdefault("completed", []).append(
            {
                "key": key,
                "change_set_id": change_set_id,
                "completed_at": utc_now(),
                "visibility": visibility,
            }
        )
        record_history(
            state,
            {
                "event": "completed",
                "key": key,
                "change_set_id": change_set_id,
                "visibility": visibility,
            },
        )
        state["current"] = None
        print(f"{key}: Public confirmed")
        return True

    failure = {
        "key": key,
        "change_set_id": change_set_id,
        "failed_at": utc_now(),
        "status": status,
        "failure_code": change_set.get("FailureCode"),
        "failure_description": change_set.get("FailureDescription"),
        "change_set": change_set.get("ChangeSet"),
    }
    state.setdefault("failed", []).append(failure)
    record_history(state, {"event": "failed", **failure})
    state["current"] = None
    print(f"{key}: change set {change_set_id} ended as {status}")
    return True


def submit_next(state: dict[str, Any], *, region: str, catalog: str, target: str) -> None:
    done = keys_from(state.get("completed") or [])
    failed = keys_from(state.get("failed") or [])

    for key in state.get("queue") or []:
        if key in done or key in failed:
            continue

        visibility = product_visibility(key, region=region, catalog=catalog)
        if visibility == target:
            entry = {
                "key": key,
                "change_set_id": None,
                "completed_at": utc_now(),
                "visibility": visibility,
                "note": "already public",
            }
            state.setdefault("completed", []).append(entry)
            record_history(state, {"event": "already_public", **entry})
            print(f"{key}: already {target}, skipping")
            continue

        if visibility != "Limited":
            failure = {
                "key": key,
                "change_set_id": None,
                "failed_at": utc_now(),
                "status": "UNEXPECTED_VISIBILITY",
                "visibility": visibility,
            }
            state.setdefault("failed", []).append(failure)
            record_history(state, {"event": "unexpected_visibility", **failure})
            print(f"{key}: unexpected visibility {visibility}, skipping")
            continue

        change_set_id = submit_visibility_change(key, target=target, region=region)
        state["current"] = {
            "key": key,
            "change_set_id": change_set_id,
            "submitted_at": utc_now(),
            "target": target,
        }
        record_history(
            state,
            {
                "event": "submitted",
                "key": key,
                "change_set_id": change_set_id,
                "target": target,
            },
        )
        print(f"{key}: submitted UpdateVisibility -> {target}: {change_set_id}")
        return

    print("rollout complete: no remaining queue items")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=str(ROOT / "artifacts" / "public_visibility_rollout.json"))
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--target", choices=["Public"], default="Public")
    parser.add_argument("--queue", nargs="+", required=True)
    args = parser.parse_args()

    config = load_config()
    catalog = config["aws"]["marketplace_catalog"]
    state_path = Path(args.state)
    state = load_or_init_state(state_path, args.queue)

    should_continue = current_done(state, region=args.region, catalog=catalog)
    if should_continue and not state.get("current"):
        submit_next(state, region=args.region, catalog=catalog, target=args.target)

    write_json(state_path, state)
    print(f"state: {state_path}")


if __name__ == "__main__":
    main()
