from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "marketplace" / "eks-admin-bastion" / "client" / "corenova_eks_connect.py"
SPEC = importlib.util.spec_from_file_location("corenova_eks_connect", CLIENT_PATH)
assert SPEC and SPEC.loader
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


class EndpointTests(unittest.TestCase):
    def test_accepts_normal_eks_https_endpoint(self) -> None:
        self.assertEqual(
            client.endpoint_hostname("https://example.eks.amazonaws.com"),
            "example.eks.amazonaws.com",
        )

    def test_rejects_credentials_query_and_non_https(self) -> None:
        bad_values = (
            "http://example.eks.amazonaws.com",
            "https://user@example.eks.amazonaws.com",
            "https://example.eks.amazonaws.com?skip=true",
            "https://example.eks.amazonaws.com:8443",
            "https://example.eks.amazonaws.com/unexpected-path",
        )
        for value in bad_values:
            with self.subTest(value=value), self.assertRaises(client.ConnectError):
                client.endpoint_hostname(value)

    def test_validates_ca_data(self) -> None:
        client.validate_certificate_data(base64.b64encode(b"certificate").decode())
        with self.assertRaises(client.ConnectError):
            client.validate_certificate_data("not-base64")


class KubeconfigTests(unittest.TestCase):
    def test_uses_local_relay_but_verifies_original_hostname(self) -> None:
        payload = client.kubeconfig_payload(
            cluster_name="production",
            region="us-east-1",
            profile="platform",
            role_arn="arn:aws:iam::123456789012:role/Operator",
            endpoint="https://cluster.example.eks.amazonaws.com",
            certificate_data="Y2VydA==",
            local_port=18443,
        )
        cluster = payload["clusters"][0]["cluster"]
        self.assertEqual(cluster["server"], "https://127.0.0.1:18443")
        self.assertEqual(cluster["tls-server-name"], "cluster.example.eks.amazonaws.com")
        self.assertNotIn("insecure-skip-tls-verify", cluster)
        exec_config = payload["users"][0]["user"]["exec"]
        self.assertEqual(exec_config["command"], "aws")
        self.assertIn("--role-arn", exec_config["args"])
        self.assertEqual(exec_config["env"], [{"name": "AWS_PROFILE", "value": "platform"}])

    def test_private_kubeconfig_permissions(self) -> None:
        path = client.write_private_json({"kind": "Config"})
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)
        finally:
            path.unlink(missing_ok=True)


class ResolutionTests(unittest.TestCase):
    @mock.patch.object(client, "run_json")
    def test_stack_outputs(self, run_json: mock.Mock) -> None:
        run_json.return_value = {
            "Stacks": [
                {
                    "Outputs": [
                        {"OutputKey": "InstanceId", "OutputValue": "i-123"},
                        {"OutputKey": "ClusterName", "OutputValue": "demo"},
                    ]
                }
            ]
        }
        self.assertEqual(
            client.stack_outputs("stack", "us-east-1", None),
            {"InstanceId": "i-123", "ClusterName": "demo"},
        )

    def test_detects_busy_ipv4_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            with self.assertRaises(client.ConnectError):
                client.ensure_port_available(port)

    @mock.patch.object(client.os, "killpg")
    def test_stops_entire_posix_tunnel_process_group(self, killpg: mock.Mock) -> None:
        process = mock.Mock()
        process.pid = 123
        process.poll.return_value = None
        process.wait.return_value = 0
        with mock.patch.object(client.os, "name", "posix"):
            client.stop_tunnel(process)
        killpg.assert_called_once_with(123, client.signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
