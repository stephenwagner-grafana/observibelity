import pytest


class TestFreshInstall:
    def test_creates_namespace(self, helm, kubectl, chart_dir):
        ns = "obs-fresh"
        result = helm.upgrade_install("obs-fresh", chart_dir, namespace=ns, atomic=False)
        assert result.returncode == 0, f"upgrade_install failed: {result.stderr}"
        assert ns in kubectl.get_namespaces()
        helm.uninstall("obs-fresh", ns)

    def test_phase0_has_no_pods(self, helm, kubectl, chart_dir):
        """Phase 0 deploys just the Namespace — no pods."""
        ns = "obs-phase0"
        helm.upgrade_install("obs-phase0", chart_dir, namespace=ns, atomic=False)
        pods = kubectl.get_pods(ns)
        assert len(pods) == 0, f"Phase 0 should have 0 pods but found {len(pods)}"
        helm.uninstall("obs-phase0", ns)

    def test_install_history_records_revision(self, helm, chart_dir):
        ns = "obs-history"
        helm.upgrade_install("obs-history", chart_dir, namespace=ns, atomic=False)
        history = helm.history("obs-history", ns)
        assert len(history) == 1
        assert history[0]["status"] == "deployed"
        helm.uninstall("obs-history", ns)
