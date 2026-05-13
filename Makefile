SHELL := /bin/bash
.DEFAULT_GOAL := help

HELM_RELEASE ?= observibelity
NAMESPACE ?= observibelity
VALUES ?= .env
CHART_DIR := .
KUBECONFIG ?= $(HOME)/.kube/config
TIMEOUT ?= 5m

.PHONY: help dev-cluster dev-cluster-down dev dev-diff dev-down verify test test-unit test-bats test-helm smoke doctor snapshot watch images lint clean init verify-repo build-usecases test-usecases new-usecase import-usecases migrate migrate-down migrate-status seed seed-regenerate logs logs-app pf-neoncart pf-llm-gateway pf-postgres trigger-mice usecases usecases-status phase deploy-k3s-local k3s-import images-local dashboards-push dashboards-pull dashboards-diff evaluators-push evaluators-status k6-logs k6-scenarios k6-restart alerts-push alerts-status soak watch-pods quick-test disaster-recovery

help:  ## Print this help (auto-generated from target docstrings).
	@awk 'BEGIN {FS = ":.*?## "; printf "ObserVIBElity — make targets\n\n"} \
		/^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev-cluster:  ## Bootstrap a local dev cluster (k3d/kind/docker-desktop).
	./tools/bootstrap-cluster.sh

dev-cluster-down:  ## Destroy the local dev cluster.
	./tools/bootstrap-cluster.sh --destroy

dev:  ## Helm upgrade --install (Loop 1 inner loop, target <30s).
	helm upgrade --install $(HELM_RELEASE) $(CHART_DIR) -n $(NAMESPACE) --create-namespace \
		$(if $(wildcard $(VALUES)),-f $(VALUES),) --atomic --wait --timeout $(TIMEOUT)

dev-diff:  ## Show what `make dev` would change (requires helm-diff plugin).
	helm diff upgrade $(HELM_RELEASE) $(CHART_DIR) -n $(NAMESPACE) \
		$(if $(wildcard $(VALUES)),-f $(VALUES),) \
		|| helm plugin install https://github.com/databus23/helm-diff

dev-down:  ## Uninstall release + delete PVCs.
	helm uninstall $(HELM_RELEASE) -n $(NAMESPACE) --wait || true
	kubectl delete pvc -n $(NAMESPACE) --all --ignore-not-found

verify:  ## Run verify.sh against the deployed release.
	./tools/verify.sh -n $(NAMESPACE)

test: test-bats test-unit test-helm  ## Run all fast tests (bats + pytest + helm-unittest).

test-unit:  ## Run pytest tests under tests/pytest/.
	cd tools && python -m pytest ../tests/pytest/ -v

test-bats:  ## Run bats tests under tests/bats/.
	bats tests/bats/

test-helm:  ## Run helm-unittest suites under tests/helm-unittest/.
	helm unittest .

smoke:  ## Full smoke test on an ephemeral k3d cluster (Loop 3).
	bash tests/e2e/smoke-k3d.sh

doctor:  ## Collect diagnostics tarball via deploy-doctor.
	./tools/deploy-doctor.sh --collect-only

snapshot:  ## Regenerate tests/snapshots/default.golden.yaml.
	@# helm 3.13 changed positional/release-name syntax — use `helm template <RELEASE> <CHART>`.
	helm template obs . --namespace $(NAMESPACE) > tests/snapshots/default.golden.yaml
	@echo "Snapshot regenerated."

watch:  ## Skaffold dev mode (Loop 2 inner loop for app code).
	@command -v skaffold >/dev/null && skaffold dev --port-forward \
		|| echo "skaffold not installed; brew install skaffold (or apt/dnf)"

images:  ## Build/list container images for this phase.
	@echo "Phase 0: no images yet. Phase 1 builds neoncart, llm-gateway, specialists, tools."

images-local: ## Build all 13 container images locally with docker (no push)
	@./tools/k3s-import-images.sh --no-build || ./tools/k3s-import-images.sh

k3s-import: ## Import locally-built images into k3s containerd
	@./tools/k3s-import-images.sh --no-build

deploy-k3s-local: images-local ## Build images, import into k3s, helm install with IfNotPresent
	@echo "▸ Deploying to k3s (local images)"
	@helm upgrade --install $(HELM_RELEASE) . \
		--namespace $(NAMESPACE) --create-namespace \
		$(if $(wildcard $(VALUES)),-f $(VALUES),) \
		--set global.imagePullPolicy=IfNotPresent \
		--atomic --wait --timeout $(TIMEOUT)
	@$(MAKE) verify

lint:  ## Run shellcheck + yamllint + helm lint (all best-effort).
	shellcheck install.sh uninstall.sh tools/*.sh tools/**/*.sh 2>/dev/null || true
	yamllint . || true
	helm lint . || true

clean:  ## Remove build artifacts and caches.
	rm -rf tools/.venv tools/bin .observibelity-state* observibelity-failure-*.tar.gz tests/**/__pycache__

init: ## First-run setup: pre-commit, python venv, .env from example, helm plugins
	@echo "▸ ObserVIBElity first-run setup"
	@if [[ ! -f .env ]]; then \
	  cp .env.example .env && \
	  echo "  ✓ created .env from .env.example — edit with your creds before running 'make dev'"; \
	else \
	  echo "  ✓ .env already exists"; \
	fi
	@if command -v pre-commit >/dev/null 2>&1; then \
	  pre-commit install --install-hooks && echo "  ✓ pre-commit hooks installed"; \
	else \
	  echo "  ! pre-commit not installed; pip install pre-commit && pre-commit install"; \
	fi
	@if [[ ! -d tools/.venv ]]; then \
	  python3 -m venv tools/.venv && \
	  tools/.venv/bin/pip install --upgrade pip -q && \
	  tools/.venv/bin/pip install -r tools/requirements.txt -q && \
	  echo "  ✓ tools/.venv created + deps installed"; \
	else \
	  echo "  ✓ tools/.venv exists"; \
	fi
	@if command -v helm >/dev/null 2>&1; then \
	  if ! helm plugin list 2>/dev/null | grep -q '^diff'; then \
	    helm plugin install https://github.com/databus23/helm-diff 2>/dev/null && echo "  ✓ helm-diff plugin installed" || echo "  ! helm-diff plugin install failed (non-fatal)"; \
	  else \
	    echo "  ✓ helm-diff plugin already installed"; \
	  fi; \
	  if ! helm plugin list 2>/dev/null | grep -q '^unittest'; then \
	    helm plugin install https://github.com/helm-unittest/helm-unittest --version v0.6.0 2>/dev/null && echo "  ✓ helm-unittest plugin installed" || echo "  ! helm-unittest plugin install failed (non-fatal)"; \
	  else \
	    echo "  ✓ helm-unittest plugin already installed"; \
	  fi; \
	fi
	@echo ""
	@echo "Next steps:"
	@echo "  1. \$$EDITOR .env                    # fill in Anthropic key, Grafana Cloud creds, GitHub PAT"
	@echo "  2. make dev-cluster                  # create local k3d cluster"
	@echo "  3. make dev                          # deploy"
	@echo "  4. make verify                       # health check"

verify-repo: ## Audit scaffold consistency: executables, links, imports, snapshots
	@./tools/check-scaffold.sh

build-usecases: ## Compile all bundled use case YAMLs in registry/use_cases/ -> registry/_generated/
	@./tools/usecase-build.sh

test-usecases: ## Validate all use case YAMLs against the schema (no compile)
	@./tools/usecase-build.sh --validate-only

new-usecase: ## Interactive wizard to author a new use case YAML
	@./tools/new-usecase.sh

import-usecases: ## Import legacy use cases from /workspace/ai-o11y-demo-pack as bundled YAMLs
	@./tools/import-from-demo-pack.sh

migrate: ## Run Alembic migrations against the deployed Postgres
	@kubectl exec -n $(NAMESPACE) -it deploy/llm-gateway -- alembic -c /app/migrations/alembic.ini upgrade head 2>/dev/null || \
		echo "Run migrations via Helm hook on next 'make dev' instead"

migrate-down: ## Roll back one migration
	@kubectl exec -n $(NAMESPACE) -it deploy/llm-gateway -- alembic -c /app/migrations/alembic.ini downgrade -1

migrate-status: ## Show current migration revision
	@kubectl exec -n $(NAMESPACE) -it deploy/llm-gateway -- alembic -c /app/migrations/alembic.ini current

seed: ## Run the seed loader (idempotent CSV upsert into Postgres)
	@kubectl create job --from=cronjob/seed-loader seed-manual-$(shell date +%s) -n $(NAMESPACE) 2>/dev/null || \
		echo "Seed runs automatically as a Helm hook; this triggers a manual re-run"

seed-regenerate: ## Regenerate the seed data CSVs from _generate.py
	@cd seed_data && python3 _generate.py

logs: ## Tail logs from all observibelity pods
	@kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/instance=$(HELM_RELEASE) --tail=50 -f --max-log-requests=20

logs-app: ## Tail logs from one component: make logs-app APP=neoncart
	@kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=$(APP) --tail=100 -f

pf-neoncart: ## Port-forward neoncart to localhost:8080
	@kubectl port-forward -n $(NAMESPACE) svc/neoncart 8080:80

pf-llm-gateway: ## Port-forward llm-gateway to localhost:8001
	@kubectl port-forward -n $(NAMESPACE) svc/llm-gateway 8001:80

pf-postgres: ## Port-forward Postgres to localhost:5432
	@kubectl port-forward -n $(NAMESPACE) svc/postgres 5432:5432

trigger-mice: ## Trigger the mice-rca demo via the chat endpoint
	@curl -s -X POST http://localhost:8080/chat \
		-H "Content-Type: application/json" \
		-d '{"message":"show me mice","persona_id":"u-demo","usecase":"mice-rca"}' | jq .

usecases: ## List all use cases authored under registry/use_cases/
	@ls -1 registry/use_cases/*.yaml | grep -v _example | xargs -I {} basename {} .yaml | sort

usecases-status: ## Show which use cases have been deployed (vs just authored)
	@for uc in $$(ls registry/use_cases/*.yaml | grep -v _example); do \
		name=$$(basename $$uc .yaml); \
		echo "  $$name $$([ -f registry/_generated/dashboards/ai-obs-$$name.json ] && echo '✓' || echo '⨯')"; \
	done

phase: ## Show current phase setting in values.yaml
	@awk '/^phase:/ {print "  phase:", $$2}' values.yaml

dashboards-push: ## Push dashboards/*.json to Grafana Cloud
	@./tools/dashboards-sync.sh push

dashboards-pull: ## Pull dashboards from Grafana Cloud -> dashboards/
	@./tools/dashboards-sync.sh pull

dashboards-diff: ## Show local vs remote dashboard diff
	@./tools/dashboards-sync.sh diff

evaluators-push: ## Push compiled evaluators to Grafana Cloud
	@./tools/evaluators-sync.sh push

evaluators-status: ## Show local evaluator files
	@./tools/evaluators-sync.sh status

k6-logs: ## Tail k6 traffic engine logs
	@./tools/k6-tail.sh

k6-scenarios: ## List generated scenarios in the ConfigMap
	@kubectl get configmap -n $(NAMESPACE) k6-scenarios -o jsonpath='{.data}' | jq -r 'keys[]'

k6-restart: ## Restart the k6 traffic engine
	@kubectl rollout restart -n $(NAMESPACE) deployment/k6-traffic

alerts-push: ## Push compiled alerts to Grafana Cloud Mimir
	@./tools/alerts-sync.sh push

alerts-status: ## Show local alert files
	@./tools/alerts-sync.sh status

soak: ## Run soak test (5 min of mixed-persona traffic)
	@./tools/soak-test.sh

watch-pods: ## Tail pod state changes in real-time
	@./tools/deploy-watch-pods.sh

quick-test: ## Run 10 demo scenarios + check responses
	@./tools/quick-test.sh

disaster-recovery: ## Tear down everything (DESTRUCTIVE)
	@./tools/disaster-recovery.sh
