# GitOps with ObserVIBElity

The default deploy path is `make dev` — a simple imperative `helm upgrade --install`. For users who want declarative push-to-deploy semantics, ObserVIBElity also works with Argo CD or Flux. This doc covers the Argo CD path.

## Why GitOps

- **Declarative:** the cluster state matches `main` in git, always
- **Audit log:** every change is a commit, every deploy a sync
- **Multi-cluster:** the same chart can deploy to dev/staging/prod from one repo
- **Drift detection:** Argo CD alerts when someone makes manual changes
- **Rollback by revert:** `git revert` undoes a deploy

## When NOT to use GitOps

- **Solo dev iteration:** `make dev` is faster (no commit round-trip)
- **Ephemeral local cluster:** k3d teardown invalidates anything synced
- **Secret-rotation-heavy workflows:** GitOps complicates secret refresh

## Setup with Argo CD

### Install Argo CD in your cluster

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### Get the admin password

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Create the Application

```yaml
# observibelity-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: observibelity
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<your-org>/observibelity.git
    targetRevision: main
    path: .
    helm:
      valueFiles:
        - values.yaml
      # Secrets — point at External Secrets or Sealed Secrets resources, NOT raw values
      values: |
        global:
          namespace: observibelity
        postgres:
          password: from-external-secret  # ExternalSecret/SealedSecret refs
  destination:
    server: https://kubernetes.default.svc
    namespace: observibelity
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Apply: `kubectl apply -f observibelity-app.yaml`

### Sync

The Application appears in the Argo CD UI. Click sync; Argo CD applies the chart. Subsequent commits to `main` trigger automatic sync.

## Handling secrets in GitOps mode

GitOps repos shouldn't contain raw secrets. Two patterns:

### Option A: External Secrets (recommended)

Use the External Secrets Operator to pull from AWS Secrets Manager / GCP Secret Manager / Vault / etc. Your repo contains `ExternalSecret` resources; Argo CD syncs those; ESO creates the actual `Secret`.

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: observibelity-creds
spec:
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: observibelity-creds
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef: { key: observibelity/anthropic-key }
    - secretKey: GRAFANA_CLOUD_API_TOKEN
      remoteRef: { key: observibelity/grafana-cloud-token }
```

### Option B: Sealed Secrets

Bitnami's Sealed Secrets encrypts a Secret with the controller's public key; the encrypted resource is committed to git; the controller in-cluster decrypts at apply time.

```bash
kubectl create secret generic obs-creds --from-literal=ANTHROPIC_API_KEY=... -o yaml --dry-run=client \
  | kubeseal --format yaml > sealed-obs-creds.yaml
git add sealed-obs-creds.yaml
```

## Tradeoffs vs `make dev`

| concern | make dev | GitOps |
|---|---|---|
| Iteration speed | ~20s | ~30-60s (commit + sync) |
| Audit trail | shell history | git log |
| Secret handling | wizard writes `.env` | ExternalSecrets / SealedSecrets |
| Multi-cluster | manual `KUBECONFIG` flipping | one Argo CD project per cluster |
| Drift detection | none | continuous |
| Rollback | `helm rollback` | `git revert` + sync |
| Setup complexity | zero | install Argo CD + ESO + per-cluster bootstrap |

## Bottom line

Both paths are supported from the same chart. Start with `make dev`; add Argo CD when you need declarative state across multiple environments.
