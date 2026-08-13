#!/usr/bin/env python3
"""Open an SSM identity relay and run kubectl with the caller's AWS identity."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence
from urllib.parse import urlparse


REMOTE_HOST_DOCUMENT = "AWS-StartPortForwardingSessionToRemoteHost"


class ConnectError(RuntimeError):
    """A buyer-actionable connection error."""


def aws_base_args(region: str | None, profile: str | None) -> list[str]:
    args = ["aws"]
    if region:
        args.extend(["--region", region])
    if profile:
        args.extend(["--profile", profile])
    return args


def run_json(command: Sequence[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ConnectError(f"required executable not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown AWS CLI error").strip()
        raise ConnectError(f"command failed: {' '.join(command)}\n{detail}") from exc
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ConnectError(f"command did not return valid JSON: {' '.join(command)}") from exc
    if not isinstance(value, dict):
        raise ConnectError(f"command returned an unexpected JSON value: {' '.join(command)}")
    return value


def stack_outputs(
    stack_name: str, region: str | None, profile: str | None
) -> dict[str, str]:
    command = aws_base_args(region, profile) + [
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        stack_name,
        "--output",
        "json",
    ]
    payload = run_json(command)
    stacks = payload.get("Stacks", [])
    if len(stacks) != 1:
        raise ConnectError(f"expected one CloudFormation stack named {stack_name!r}")
    return {
        item["OutputKey"]: item.get("OutputValue", "")
        for item in stacks[0].get("Outputs", [])
        if item.get("OutputKey")
    }


def cluster_details(
    cluster_name: str, region: str | None, profile: str | None
) -> tuple[str, str]:
    command = aws_base_args(region, profile) + [
        "eks",
        "describe-cluster",
        "--name",
        cluster_name,
        "--output",
        "json",
    ]
    cluster = run_json(command).get("cluster", {})
    endpoint = str(cluster.get("endpoint", ""))
    certificate = str(cluster.get("certificateAuthority", {}).get("data", ""))
    if not endpoint or not certificate:
        raise ConnectError("EKS describe-cluster response is missing endpoint or certificate data")
    return endpoint, certificate


def endpoint_hostname(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        raise ConnectError("cluster endpoint must be an HTTPS URL on port 443")
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ConnectError("cluster endpoint contains unsupported URL components")
    return parsed.hostname


def validate_certificate_data(value: str) -> None:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ConnectError("cluster certificateAuthority.data is not valid base64") from exc
    if not decoded:
        raise ConnectError("cluster certificateAuthority.data is empty")


def require_executables(names: Sequence[str]) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise ConnectError(f"missing required local executable(s): {', '.join(missing)}")


def ensure_port_available(port: int) -> None:
    for family, address in (
        (socket.AF_INET, ("127.0.0.1", port)),
        (socket.AF_INET6, ("::1", port)),
    ):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.bind(address)
        except OSError as exc:
            if family == socket.AF_INET6 and exc.errno in {47, 97}:
                continue
            raise ConnectError(f"local port {port} is already in use") from exc


def wait_for_port(port: int, process: subprocess.Popen[Any], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ConnectError(
                f"SSM port-forwarding session exited early with status {process.returncode}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.25)
    raise ConnectError(f"SSM tunnel did not listen on port {port} within {timeout:g} seconds")


def kubeconfig_payload(
    *,
    cluster_name: str,
    region: str | None,
    profile: str | None,
    role_arn: str | None,
    endpoint: str,
    certificate_data: str,
    local_port: int,
) -> dict[str, Any]:
    host = endpoint_hostname(endpoint)
    token_args = ["eks", "get-token", "--cluster-name", cluster_name]
    if region:
        token_args.extend(["--region", region])
    if role_arn:
        token_args.extend(["--role-arn", role_arn])
    exec_config: dict[str, Any] = {
        "apiVersion": "client.authentication.k8s.io/v1beta1",
        "command": "aws",
        "args": token_args,
        "interactiveMode": "Never",
        "provideClusterInfo": False,
    }
    if profile:
        exec_config["env"] = [{"name": "AWS_PROFILE", "value": profile}]
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": "corenova-relay",
                "cluster": {
                    "server": f"https://127.0.0.1:{local_port}",
                    "tls-server-name": host,
                    "certificate-authority-data": certificate_data,
                },
            }
        ],
        "contexts": [
            {
                "name": "corenova-relay",
                "context": {"cluster": "corenova-relay", "user": "caller"},
            }
        ],
        "current-context": "corenova-relay",
        "users": [{"name": "caller", "user": {"exec": exec_config}}],
    }


def write_private_json(payload: dict[str, Any]) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix="corenova-eks-", suffix=".kubeconfig")
    path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def stop_tunnel(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Connect kubectl to a private EKS endpoint through an SSM relay while "
            "retaining the caller's AWS identity."
        )
    )
    parser.add_argument("--stack-name", help="Identity Relay CloudFormation stack")
    parser.add_argument("--instance-id", help="override the stack InstanceId output")
    parser.add_argument("--cluster", help="override the stack ClusterName output")
    parser.add_argument("--cluster-endpoint", help="override EKS endpoint discovery")
    parser.add_argument(
        "--certificate-authority-data", help="override EKS certificate discovery"
    )
    parser.add_argument("--region", help="AWS region (otherwise use normal AWS CLI resolution)")
    parser.add_argument("--profile", help="AWS CLI profile")
    parser.add_argument("--role-arn", help="role passed to aws eks get-token")
    parser.add_argument("--namespace", default="default", help="default verification namespace")
    parser.add_argument("--local-port", type=int, default=18443)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the tunnel and kubectl commands without starting a session",
    )
    parser.add_argument(
        "kubectl_args",
        nargs=argparse.REMAINDER,
        help="kubectl arguments after --; defaults to a read-only authorization check",
    )
    return parser


def resolve_connection(args: argparse.Namespace) -> tuple[str, str, str, str]:
    outputs: dict[str, str] = {}
    if args.stack_name:
        outputs = stack_outputs(args.stack_name, args.region, args.profile)
    instance_id = args.instance_id or outputs.get("InstanceId", "")
    cluster_name = args.cluster or outputs.get("ClusterName", "")
    if not instance_id or not cluster_name:
        raise ConnectError("provide --stack-name, or both --instance-id and --cluster")

    endpoint = args.cluster_endpoint
    certificate_data = args.certificate_authority_data
    if bool(endpoint) != bool(certificate_data):
        raise ConnectError(
            "--cluster-endpoint and --certificate-authority-data must be supplied together"
        )
    if not endpoint:
        endpoint, certificate_data = cluster_details(cluster_name, args.region, args.profile)
    assert certificate_data is not None
    endpoint_hostname(endpoint)
    validate_certificate_data(certificate_data)
    return instance_id, cluster_name, endpoint, certificate_data


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (1 <= args.local_port <= 65535):
        raise ConnectError("--local-port must be between 1 and 65535")
    if args.connect_timeout <= 0:
        raise ConnectError("--connect-timeout must be greater than zero")

    require_executables(["aws", "kubectl"] + ([] if args.dry_run else ["session-manager-plugin"]))
    instance_id, cluster_name, endpoint, certificate_data = resolve_connection(args)
    host = endpoint_hostname(endpoint)
    parameters = json.dumps(
        {"host": [host], "portNumber": ["443"], "localPortNumber": [str(args.local_port)]},
        separators=(",", ":"),
    )
    tunnel_command = aws_base_args(args.region, args.profile) + [
        "ssm",
        "start-session",
        "--target",
        instance_id,
        "--document-name",
        REMOTE_HOST_DOCUMENT,
        "--parameters",
        parameters,
    ]
    kubectl_args = list(args.kubectl_args)
    if kubectl_args[:1] == ["--"]:
        kubectl_args = kubectl_args[1:]
    if not kubectl_args:
        kubectl_args = ["auth", "can-i", "get", "pods", "--namespace", args.namespace]

    kubeconfig = kubeconfig_payload(
        cluster_name=cluster_name,
        region=args.region,
        profile=args.profile,
        role_arn=args.role_arn,
        endpoint=endpoint,
        certificate_data=certificate_data,
        local_port=args.local_port,
    )
    if args.dry_run:
        print("Tunnel command:")
        print(json.dumps(tunnel_command))
        print("Kubectl command:")
        print(json.dumps(["kubectl", "--kubeconfig", "<temporary-file>"] + kubectl_args))
        return 0

    ensure_port_available(args.local_port)
    kubeconfig_path = write_private_json(kubeconfig)
    tunnel: subprocess.Popen[Any] | None = None
    try:
        print(f"Opening SSM identity relay to {host}:443...", file=sys.stderr)
        tunnel = subprocess.Popen(
            tunnel_command,
            start_new_session=(os.name == "posix"),
        )
        wait_for_port(args.local_port, tunnel, args.connect_timeout)
        print("Relay ready; kubectl is using your local AWS identity.", file=sys.stderr)
        completed = subprocess.run(
            ["kubectl", "--kubeconfig", str(kubeconfig_path)] + kubectl_args,
            check=False,
        )
        return completed.returncode
    finally:
        if tunnel is not None:
            stop_tunnel(tunnel)
        kubeconfig_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted; relay closed.", file=sys.stderr)
        raise SystemExit(130)
    except ConnectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
