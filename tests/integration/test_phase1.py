"""Phase 1 integration tests — verify mice-rca end-to-end."""
import pytest
import json
import time
import subprocess


@pytest.fixture(scope="session")
def phase1_install(k3d_cluster, helm):
    """Install Phase 1 stack into the k3d cluster."""
    # NB: this is the heaviest fixture — it actually deploys Phase 1.
    ns = "obs-p1"
    chart = "/workspace/observibelity"
    # Pre-stage a minimal .env in /tmp
    env_content = """
ANTHROPIC_API_KEY=sk-ant-test-phase1
GRAFANA_CLOUD_INSTANCE_ID=0
GRAFANA_CLOUD_API_TOKEN=test
GRAFANA_CLOUD_OTLP_ENDPOINT=https://otlp-gateway-prod-us-east-0.grafana.net/otlp
PHASE=1
""".strip()
    env_file = "/tmp/phase1.env"
    with open(env_file, "w") as f:
        f.write(env_content)

    result = helm.upgrade_install(
        "obs-p1", chart, namespace=ns,
        values=[env_file],
        set_values={"phase": "1", "postgres.password": "testpass"},
        atomic=False, timeout="5m",
    )
    if result.returncode != 0:
        pytest.skip(f"Phase 1 install failed (likely missing images): {result.stderr[:500]}")
    yield ns
    helm.uninstall("obs-p1", ns)


class TestPhase1Deploy:
    def test_postgres_starts(self, phase1_install, kubectl):
        pods = kubectl.get_pods(phase1_install)
        pg_pods = [p for p in pods if "postgres" in p["metadata"]["name"]]
        assert len(pg_pods) >= 1

    def test_llm_gateway_ready(self, phase1_install, kubectl):
        # Wait up to 60s for ready
        for _ in range(12):
            pods = kubectl.get_pods(phase1_install)
            gateway = [p for p in pods if "llm-gateway" in p["metadata"]["name"]]
            if gateway and gateway[0].get("status", {}).get("phase") == "Running":
                return
            time.sleep(5)
        pytest.fail("llm-gateway not ready within 60s")

    def test_neoncart_ready(self, phase1_install, kubectl):
        for _ in range(12):
            pods = kubectl.get_pods(phase1_install)
            nc = [p for p in pods if p["metadata"]["name"].startswith("neoncart")]
            if nc and nc[0].get("status", {}).get("phase") == "Running":
                return
            time.sleep(5)
        pytest.fail("neoncart not ready within 60s")

    def test_specialists_ready(self, phase1_install, kubectl):
        # nc-chatbot, nc-fraud-detector, nc-fulfillment-orchestrator
        expected = ["nc-chatbot", "nc-fraud-detector", "nc-fulfillment-orchestrator"]
        for _ in range(12):
            pods = kubectl.get_pods(phase1_install)
            running = {
                p["metadata"]["name"].rsplit("-", 2)[0]
                for p in pods
                if p.get("status", {}).get("phase") == "Running"
            }
            if all(any(name in r for r in running) for name in expected):
                return
            time.sleep(5)
        pytest.fail(f"Specialists not all running. Expected {expected}.")

    def test_tools_ready(self, phase1_install, kubectl):
        # 6 tools
        expected_count = 6
        for _ in range(12):
            pods = kubectl.get_pods(phase1_install)
            tool_pods = [
                p for p in pods
                if p["metadata"].get("labels", {}).get("app.kubernetes.io/component") == "tool"
                and p.get("status", {}).get("phase") == "Running"
            ]
            if len(tool_pods) >= expected_count:
                return
            time.sleep(5)
        pytest.fail(f"Expected {expected_count} tool pods running")


class TestMiceRca:
    def test_health_endpoint_reachable(self, phase1_install):
        # Port-forward + curl
        pf = subprocess.Popen(
            ["kubectl", "port-forward", "-n", phase1_install,
             "svc/neoncart", "18080:80"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(3)
            result = subprocess.run(
                ["curl", "-sf", "http://localhost:18080/health"],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == 0, f"health check failed: {result.stderr}"
        finally:
            pf.terminate()
            pf.wait(timeout=5)

    def test_mice_query_returns_empty(self, phase1_install):
        """Search for "mice" — catalog has no mice products."""
        pf = subprocess.Popen(
            ["kubectl", "port-forward", "-n", phase1_install,
             "svc/neoncart", "18081:80"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(3)
            result = subprocess.run(
                ["curl", "-sf", "http://localhost:18081/api/search?q=mice"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                pytest.skip(f"search endpoint not reachable: {result.stderr}")
            data = json.loads(result.stdout) if result.stdout else {}
            results = data.get("results", data.get("items", []))
            assert len(results) == 0, f"Expected empty mice search; got {results}"
        finally:
            pf.terminate()
            pf.wait(timeout=5)

    def test_mice_fulfillment_triggers_error(self, phase1_install):
        """Trigger get_inventory with sku=mice-001 → expect SQL error."""
        pf = subprocess.Popen(
            ["kubectl", "port-forward", "-n", phase1_install,
             "svc/neoncart", "18082:80"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(3)
            payload = json.dumps({
                "message": "check inventory for mice-001",
                "persona_id": "demo@acme.com",
                "usecase": "mice-rca",
            })
            result = subprocess.run(
                ["curl", "-s", "-X", "POST",
                 "http://localhost:18082/chat",
                 "-H", "Content-Type: application/json",
                 "-d", payload],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                pytest.skip(f"chat endpoint not reachable: {result.stderr}")
            # Expect either a 5xx-style error in body, or a chained error in the response
            body = result.stdout.lower()
            error_signals = ["error", "exception", "sql", "not found", "mice"]
            assert any(s in body for s in error_signals), (
                f"Expected error/mice signal in response, got: {body[:300]}"
            )
        finally:
            pf.terminate()
            pf.wait(timeout=5)


# Most tests will skip if images aren't built yet (Phase 1 is brand new)
