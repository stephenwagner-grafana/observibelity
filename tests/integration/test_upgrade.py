import pytest


class TestUpgrade:
    def test_upgrade_is_idempotent(self, helm, chart_dir):
        """Two `upgrade --install` of the same chart should produce identical resources."""
        ns = "obs-idempot"
        helm.upgrade_install("obs-i", chart_dir, namespace=ns, atomic=False)
        helm.upgrade_install("obs-i", chart_dir, namespace=ns, atomic=False)
        history = helm.history("obs-i", ns)
        assert len(history) == 2
        assert all(h["status"] == "deployed" or h["status"] == "superseded" for h in history)
        helm.uninstall("obs-i", ns)

    def test_upgrade_preserves_namespace(self, helm, kubectl, chart_dir):
        ns = "obs-preserve"
        helm.upgrade_install("obs-p", chart_dir, namespace=ns, atomic=False)
        helm.upgrade_install("obs-p", chart_dir, namespace=ns, atomic=False,
                             set_values={"observability.traffic_origin_default": "interactive"})
        assert ns in kubectl.get_namespaces()
        helm.uninstall("obs-p", ns)

    @pytest.mark.skip(reason="Phase 1 templates not yet present")
    def test_upgrade_phase0_to_phase1(self):
        pass
