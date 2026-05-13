"""Diagnostics collector.

Runs a battery of kubectl/helm/env probes against a Kubernetes cluster and
writes the (optionally redacted) output into a tarball. The tarball is the
artifact a user attaches to a GitHub issue when install.sh exits with code
>= 3, and it's also the context payload the Phase 1 Diagnoser will hand to
an LLM Provider.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = 30  # seconds per subprocess call
DESCRIBE_NODE_LINE_LIMIT = 500
POD_LOG_TAIL_LINES = 200

# Regex patterns we treat as secret-bearing. Applied to both env-style key=val
# output and Kubernetes Secret manifest `data:` blocks.
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|password|passwd|secret|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|auth)"
)
_KV_LINE = re.compile(
    r"^(\s*[\"']?(?P<key>[A-Za-z0-9_.-]+)[\"']?\s*[:=]\s*)(?P<val>.+?)\s*$"
)
_YAML_DATA_LINE = re.compile(
    r"^(?P<indent>\s+)(?P<key>[A-Za-z0-9_.-]+):\s*(?P<val>\S.*)$"
)

_REDACTED = "***REDACTED***"


# ---------------------------------------------------------------------------
# REPO_ROOT discovery: walk up from this file until we find a Chart.yaml.
# Fall back to $REPO_ROOT env var. This mirrors the bash wrapper's logic so
# the Python package can be invoked standalone (e.g. by tests).
# ---------------------------------------------------------------------------
def _discover_repo_root() -> Path:
    env_root = os.environ.get("REPO_ROOT")
    if env_root:
        return Path(env_root).resolve()

    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "Chart.yaml").is_file():
            return candidate
    # No Chart.yaml found — fall back to the parent of tools/, which is the
    # likeliest layout. Better to return something than crash here.
    return here.parent.parent


class Collector:
    """Gathers kubectl/helm/env diagnostics into a tarball."""

    def __init__(
        self,
        namespace: str = "observibelity",
        release: str = "observibelity",
        redact_secrets: bool = True,
    ) -> None:
        self.namespace = namespace
        self.release = release
        self.redact_secrets = redact_secrets
        self.repo_root = _discover_repo_root()

    # ------------------------------------------------------------------
    # Subprocess helper
    # ------------------------------------------------------------------
    def _run(self, cmd: list[str], timeout: int = DEFAULT_TIMEOUT) -> str:
        """Run a command and return combined stdout+stderr. Never raises."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            out = result.stdout or ""
            err = result.stderr or ""
            chunks = [f"$ {' '.join(cmd)}", out]
            if err.strip():
                chunks.append(f"--- stderr ---\n{err}")
            chunks.append(f"--- exit: {result.returncode} ---")
            return "\n".join(chunks)
        except FileNotFoundError as exc:
            return f"$ {' '.join(cmd)}\n--- error: {exc} ---"
        except subprocess.TimeoutExpired:
            return f"$ {' '.join(cmd)}\n--- error: timed out after {timeout}s ---"
        except Exception as exc:  # pragma: no cover - defensive
            return f"$ {' '.join(cmd)}\n--- error: {exc} ---"

    # ------------------------------------------------------------------
    # Redaction
    # ------------------------------------------------------------------
    def _redact(self, text: str) -> str:
        """Redact secret-bearing lines. Used by every collector output."""
        if not self.redact_secrets:
            return text

        out_lines: list[str] = []
        for line in text.splitlines():
            # Try env/key=value style first (handles `FOO=bar`, `FOO: bar`).
            m = _KV_LINE.match(line)
            if m and _SECRET_KEY_PATTERN.search(m.group("key")):
                prefix = line[: m.start("val")]
                out_lines.append(f"{prefix}{_REDACTED}")
                continue
            # YAML-indented `data:` block style (Secret manifests).
            m = _YAML_DATA_LINE.match(line)
            if m and _SECRET_KEY_PATTERN.search(m.group("key")):
                out_lines.append(f"{m.group('indent')}{m.group('key')}: {_REDACTED}")
                continue
            out_lines.append(line)
        return "\n".join(out_lines)

    # ------------------------------------------------------------------
    # Individual collectors. Each returns a string (or dict) suitable for
    # writing into a single file in the bundle.
    # ------------------------------------------------------------------
    def collect_kubectl_events(self) -> str:
        ns_events = self._run([
            "kubectl", "get", "events",
            "-n", self.namespace,
            "--sort-by=.lastTimestamp",
            "-o", "yaml",
        ])
        all_events = self._run([
            "kubectl", "get", "events",
            "-A",
            "--sort-by=.lastTimestamp",
        ])
        return self._redact(
            f"=== events in namespace {self.namespace} ===\n{ns_events}\n\n"
            f"=== events cluster-wide ===\n{all_events}"
        )

    def collect_helm_status(self) -> str:
        status = self._run([
            "helm", "status", self.release,
            "-n", self.namespace,
            "--show-resources",
        ])
        history = self._run([
            "helm", "history", self.release,
            "-n", self.namespace,
        ])
        return self._redact(
            f"=== helm status ===\n{status}\n\n=== helm history ===\n{history}"
        )

    def collect_pod_state(self) -> str:
        return self._redact(self._run([
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-o", "wide",
        ]))

    def collect_pod_logs(self, failing_only: bool = True) -> str:
        """Logs for each not-Ready pod (and its init containers)."""
        # We use jsonpath so we don't depend on YAML parsing here. Each line is
        # `<pod-name>\t<ready>`, where ready is "True" only when every
        # container reports Ready=True.
        listing = self._run([
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-o", "jsonpath={range .items[*]}{.metadata.name}{\"\\t\"}"
            "{.status.containerStatuses[*].ready}{\"\\n\"}{end}",
        ])

        sections: list[str] = []
        for raw_line in listing.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("$") or line.startswith("---"):
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            pod, ready_states = parts
            is_ready = ready_states and all(
                token == "true" for token in ready_states.split()
            )
            if failing_only and is_ready:
                continue
            log_output = self._run([
                "kubectl", "logs",
                "-n", self.namespace,
                pod,
                "--all-containers",
                f"--tail={POD_LOG_TAIL_LINES}",
            ])
            sections.append(f"=== logs: {pod} ===\n{log_output}")

            # Init containers separately so we surface CrashLoopBackOff
            # on initContainers (a common neoncart/loader failure mode).
            init_log = self._run([
                "kubectl", "logs",
                "-n", self.namespace,
                pod,
                "--all-containers",
                "--previous",
                f"--tail={POD_LOG_TAIL_LINES}",
            ])
            sections.append(f"=== logs (previous): {pod} ===\n{init_log}")

        if not sections:
            sections.append("(no failing pods detected — nothing to dump)")
        return self._redact("\n\n".join(sections))

    def collect_node_state(self) -> str:
        nodes = self._run(["kubectl", "get", "nodes", "-o", "wide"])
        describe = self._run(["kubectl", "describe", "nodes"], timeout=60)
        # Truncate describe output to keep the bundle tractable.
        describe_lines = describe.splitlines()
        if len(describe_lines) > DESCRIBE_NODE_LINE_LIMIT:
            describe = "\n".join(describe_lines[:DESCRIBE_NODE_LINE_LIMIT])
            describe += (
                f"\n--- truncated to first {DESCRIBE_NODE_LINE_LIMIT} lines "
                f"(of {len(describe_lines)}) ---"
            )
        return self._redact(
            f"=== nodes ===\n{nodes}\n\n=== describe nodes ===\n{describe}"
        )

    def collect_pvc_state(self) -> str:
        listing = self._run([
            "kubectl", "get", "pvc",
            "-n", self.namespace,
            "-o", "yaml",
        ])
        # Quick scan for Pending PVCs — call them out at the top so the LLM
        # (and human readers) notice without parsing all the YAML.
        flags: list[str] = []
        for line in listing.splitlines():
            if "phase:" in line.lower() and "pending" in line.lower():
                flags.append(line.strip())
        flag_block = (
            "PENDING PVCs DETECTED:\n" + "\n".join(flags) if flags else
            "(no Pending PVCs detected)"
        )
        return self._redact(f"=== pvc summary ===\n{flag_block}\n\n=== pvc yaml ===\n{listing}")

    def collect_otel_collector_logs(self) -> str:
        """Logs from any otel-collector pod in the namespace, if present."""
        listing = self._run([
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-l", "app.kubernetes.io/name=otel-collector",
            "-o", "jsonpath={.items[*].metadata.name}",
        ])
        # listing now has a header line ($ kubectl ...) plus the actual
        # jsonpath output. Strip our scaffolding.
        names: list[str] = []
        for line in listing.splitlines():
            if line.startswith("$") or line.startswith("---"):
                continue
            names.extend(name for name in line.split() if name)

        if not names:
            return "(no otel-collector pod found in this namespace)"

        sections: list[str] = []
        for pod in names:
            log_output = self._run([
                "kubectl", "logs",
                "-n", self.namespace,
                pod,
                "--all-containers",
                f"--tail={POD_LOG_TAIL_LINES}",
            ])
            sections.append(f"=== otel-collector: {pod} ===\n{log_output}")
        return self._redact("\n\n".join(sections))

    def collect_state_file(self) -> str:
        """Read .observibelity-state and redact any secret-y input keys."""
        state_path = self.repo_root / ".observibelity-state"
        if not state_path.is_file():
            return f"(no state file at {state_path})"
        try:
            raw = state_path.read_text()
        except Exception as exc:
            return f"(could not read state file: {exc})"
        return self._redact(raw)

    def collect_values_rendered(self) -> str:
        """Render the chart with the user's .env to surface bad values."""
        env_file = self.repo_root / ".env"
        cmd = [
            "helm", "template", self.release, str(self.repo_root),
            "--namespace", self.namespace,
        ]
        if env_file.is_file():
            cmd.extend(["-f", str(env_file)])
        return self._redact(self._run(cmd, timeout=60))

    def collect_env_dump(self) -> str:
        kver = self._run(["kubectl", "version", "--output=yaml"])
        hver = self._run(["helm", "version"])
        pver = self._run(["python", "--version"])
        uname = self._run(["uname", "-a"])
        # No secrets in any of these, but run through redact for consistency.
        return self._redact(
            "=== kubectl version ===\n" + kver +
            "\n\n=== helm version ===\n" + hver +
            "\n\n=== python version ===\n" + pver +
            "\n\n=== uname ===\n" + uname
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def collect_all_as_dict(self) -> dict[str, Any]:
        """Run every collector and return a dict keyed by collector name.

        Used by the Phase 1 Diagnoser to build the LLM context payload.
        """
        return {
            "kubectl_events": self.collect_kubectl_events(),
            "helm_status": self.collect_helm_status(),
            "pod_state": self.collect_pod_state(),
            "pod_logs": self.collect_pod_logs(failing_only=True),
            "node_state": self.collect_node_state(),
            "pvc_state": self.collect_pvc_state(),
            "otel_collector_logs": self.collect_otel_collector_logs(),
            "state_file": self.collect_state_file(),
            "values_rendered": self.collect_values_rendered(),
            "env_dump": self.collect_env_dump(),
        }

    def bundle(self, output_path: str | None) -> str:
        """Run every collector, write outputs to a temp dir, tar it up."""
        if not output_path:
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            output_path = str(self.repo_root / f"observibelity-failure-{stamp}.tar.gz")

        data = self.collect_all_as_dict()
        bundle_basename = f"observibelity-failure-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp) / bundle_basename
            tmp_root.mkdir(parents=True, exist_ok=True)
            for name, content in data.items():
                target = tmp_root / f"{name}.txt"
                target.write_text(content if isinstance(content, str) else str(content))

            # Manifest summarising what was collected and the redaction setting.
            manifest = [
                f"namespace: {self.namespace}",
                f"release: {self.release}",
                f"redacted: {self.redact_secrets}",
                f"collected_at: {_dt.datetime.now().isoformat()}",
                "files:",
                *[f"  - {name}.txt" for name in data],
            ]
            (tmp_root / "MANIFEST.txt").write_text("\n".join(manifest))

            with tarfile.open(output_path, "w:gz") as tar:
                tar.add(tmp_root, arcname=bundle_basename)

        return output_path
