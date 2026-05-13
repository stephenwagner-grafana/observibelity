import pytest


class TestRollback:
    def test_rollback_to_previous_revision(self, helm, chart_dir):
        ns = "obs-rollback"
        helm.upgrade_install("obs-r", chart_dir, namespace=ns, atomic=False)
        helm.upgrade_install("obs-r", chart_dir, namespace=ns, atomic=False,
                             set_values={"observability.traffic_origin_default": "interactive"})
        rollback_result = helm.rollback("obs-r", 1, ns)
        assert rollback_result.returncode == 0
        history = helm.history("obs-r", ns)
        # rollback creates a new revision
        assert len(history) >= 3
        helm.uninstall("obs-r", ns)


class TestHelmTest:
    def test_helm_test_passes_in_phase0(self, helm, chart_dir):
        """The Phase 0 helm test pod just echoes and exits 0."""
        ns = "obs-helmtest"
        helm.upgrade_install("obs-ht", chart_dir, namespace=ns, atomic=False)
        result = helm.test("obs-ht", ns)
        assert result.returncode == 0, f"helm test failed:\n{result.stdout}\n{result.stderr}"
        helm.uninstall("obs-ht", ns)
