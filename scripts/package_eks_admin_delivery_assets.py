#!/usr/bin/env python3
"""Build deterministic, architecture-locked Marketplace delivery assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from productlib import ROOT


SOURCE = ROOT / "marketplace" / "eks-admin-bastion" / "cloudformation"
PRODUCT_SOURCE = ROOT / "marketplace" / "eks-admin-bastion"
TEMPLATES = ("identity-relay.yaml", "audited-workstation.yaml")
DIAGRAMS = (
    "identity-relay-architecture.png",
    "audited-workstation-architecture.png",
)
COMMON_ASSETS = (
    "client/corenova_eks_connect.py",
    "docs/index.html",
    "docs/choose-a-mode.md",
    "docs/quickstart.md",
    "docs/security.md",
    "docs/troubleshooting.md",
    "docs/upgrade.md",
    "docs/use-cases.md",
    "iam/audited-workstation-operator-policy.json",
    "iam/identity-relay-operator-policy.json",
)


def architecture_template(source: str, architecture: str, name: str) -> str:
    original_block = "    Default: x86_64\n    AllowedValues: [x86_64, arm64]"
    replacement_block = (
        f"    Default: {architecture}\n    AllowedValues: [{architecture}]"
    )
    if source.count(original_block) != 1:
        raise ValueError(f"{name}: expected one architecture parameter block")
    rendered = source.replace(original_block, replacement_block)
    if architecture == "arm64":
        default_instance = "t3.micro" if name == "identity-relay.yaml" else "t3.small"
        replacement_instance = "t4g.micro" if name == "identity-relay.yaml" else "t4g.small"
        marker = f"    Default: {default_instance}\n"
        if rendered.count(marker) != 1:
            raise ValueError(f"{name}: expected one default instance marker")
        rendered = rendered.replace(marker, f"    Default: {replacement_instance}\n")
    return rendered


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_package(output_dir: Path) -> Path:
    manifest: dict[str, object] = {
        "schema_version": 2,
        "architectures": {},
        "common": {},
    }
    for architecture in ("x86_64", "arm64"):
        destination = output_dir / architecture
        destination.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for name in TEMPLATES:
            source = (SOURCE / name).read_text(encoding="utf-8")
            target = destination / name
            target.write_text(
                architecture_template(source, architecture, name), encoding="utf-8"
            )
            files[name] = sha256(target)
        for name in DIAGRAMS:
            target = destination / name
            shutil.copyfile(SOURCE / name, target)
            files[name] = sha256(target)
        manifest["architectures"][architecture] = files  # type: ignore[index]
    common: dict[str, str] = {}
    for relative in COMMON_ASSETS:
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PRODUCT_SOURCE / relative, target)
        common[relative] = sha256(target)
    manifest["common"] = common
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def package(output_dir: Path) -> Path:
    """Build in a clean sibling directory and replace the output as one unit."""
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    backup = output_dir.parent / f".{output_dir.name}.backup-{uuid4().hex}"
    moved_existing = False
    try:
        build_package(staging)
        if output_dir.exists():
            if output_dir.is_symlink() or not output_dir.is_dir():
                raise ValueError(f"output path is not a normal directory: {output_dir}")
            output_dir.rename(backup)
            moved_existing = True
        staging.rename(output_dir)
        if moved_existing:
            shutil.rmtree(backup)
        return output_dir / "manifest.json"
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if moved_existing and backup.exists() and not output_dir.exists():
            backup.rename(output_dir)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", default=str(ROOT / "dist" / "eks-admin-bastion")
    )
    args = parser.parse_args()
    print(package(Path(args.output_dir)))


if __name__ == "__main__":
    main()
