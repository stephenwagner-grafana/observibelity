import os
import subprocess
import uuid
import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd, check=True, capture=True, env=None):
    """Run a subprocess; capture stdout/stderr."""
    env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, capture_output=capture, text=True, env=env)
    if check and result.returncode != 0:
        pytest.fail(f"cmd failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}")
    return result


@pytest.fixture(scope="session")
def k3d_cluster():
    """Spin up an ephemeral k3d cluster; tear down at session end."""
    name = f"obs-int-{uuid.uuid4().hex[:8]}"
    _run(["k3d", "cluster", "create", name, "--wait", "--timeout", "120s",
          "--no-lb", "--k3s-arg", "--disable=traefik@server:0"])
    kubeconfig = _run(["k3d", "kubeconfig", "write", name]).stdout.strip()
    yield {"name": name, "kubeconfig": kubeconfig}
    _run(["k3d", "cluster", "delete", name], check=False)


class HelmClient:
    def __init__(self, kubeconfig):
        self.env = {"KUBECONFIG": kubeconfig}

    def upgrade_install(self, release, chart, values=None, namespace="default", set_values=None, atomic=True, timeout="2m"):
        cmd = ["helm", "upgrade", "--install", release, str(chart),
               "--namespace", namespace, "--create-namespace",
               "--wait", "--timeout", timeout]
        if atomic:
            cmd.append("--atomic")
        if values:
            for v in values:
                cmd.extend(["-f", str(v)])
        if set_values:
            for k, v in set_values.items():
                cmd.extend(["--set", f"{k}={v}"])
        return _run(cmd, env=self.env, check=False)

    def uninstall(self, release, namespace):
        return _run(["helm", "uninstall", release, "-n", namespace, "--wait"], env=self.env, check=False)

    def status(self, release, namespace):
        return _run(["helm", "status", release, "-n", namespace, "-o", "json"], env=self.env)

    def history(self, release, namespace):
        result = _run(["helm", "history", release, "-n", namespace, "-o", "json"], env=self.env)
        return json.loads(result.stdout)

    def rollback(self, release, revision, namespace):
        return _run(["helm", "rollback", release, str(revision), "-n", namespace, "--wait"], env=self.env, check=False)

    def test(self, release, namespace):
        return _run(["helm", "test", release, "-n", namespace], env=self.env, check=False)


class KubectlClient:
    def __init__(self, kubeconfig):
        self.env = {"KUBECONFIG": kubeconfig}

    def get_pods(self, namespace):
        result = _run(["kubectl", "get", "pods", "-n", namespace, "-o", "json"], env=self.env)
        return json.loads(result.stdout).get("items", [])

    def get_pvcs(self, namespace):
        result = _run(["kubectl", "get", "pvc", "-n", namespace, "-o", "json"], env=self.env)
        return json.loads(result.stdout).get("items", [])

    def get_namespaces(self):
        result = _run(["kubectl", "get", "ns", "-o", "json"], env=self.env)
        return [n["metadata"]["name"] for n in json.loads(result.stdout)["items"]]


@pytest.fixture
def helm(k3d_cluster):
    return HelmClient(k3d_cluster["kubeconfig"])


@pytest.fixture
def kubectl(k3d_cluster):
    return KubectlClient(k3d_cluster["kubeconfig"])


@pytest.fixture
def chart_dir():
    return REPO_ROOT
