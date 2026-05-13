# Deployment Scenarios

ObserVIBElity targets **any Kubernetes 1.27+** cluster with a default
StorageClass and a working ingress controller. This page collects per-target
recipes; pick yours.

Each section ends with a **Verified-on** badge to set honest expectations:
- `✓ Verified on Phase 0 scaffolding` — the install scaffolding has been
  exercised on this target.
- `○ Untested in Phase 0; please report results.` — we believe it should work
  but haven't run it ourselves yet.

---

## Docker Desktop (Kubernetes enabled)

**Prereqs**
- Docker Desktop with Kubernetes enabled
  (Settings → Kubernetes → "Enable Kubernetes")
- At least 4 GiB RAM allocated to Docker (Settings → Resources)

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

The wizard offers `values-docker-desktop.yaml` as the overlay; accept it.

**Access**

```
kubectl port-forward -n observibelity svc/neoncart 8080:80
```

Then open http://localhost:8080.

**Limits**
- Single-node only — no real ingress.
- ~2 GiB RAM committed for the full stack.
- No persistent storage outside the Docker VM — `docker volume rm` wipes it.

**Uninstall**

```
./uninstall.sh
```

`○ Untested in Phase 0; please report results.`

---

## k3d (local lightweight Kubernetes)

**Prereqs**
- Docker installed
- k3d itself can be **auto-installed** by the preflight subsystem to
  `./tools/bin/k3d` — you don't need to install it yourself.

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

If no cluster is detected, the wizard offers to bootstrap a k3d cluster for
you via `tools/bootstrap-cluster.sh`.

**Access**

Ingress is exposed on `neoncart.localhost:8080`. Add this to `/etc/hosts` if
your OS doesn't resolve `*.localhost` to `127.0.0.1` automatically.

**Uninstall**

```
./uninstall.sh --destroy-cluster
```

`✓ Verified on Phase 0 scaffolding` (k3d-in-GHA smoke test covers the install
scaffolding end-to-end).

---

## k3s (single-node "real" cluster)

**Prereqs**
- k3s installed: https://k3s.io
- `kubectl` configured against the cluster
  (`sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config && sudo chown $USER ~/.kube/config`)

**StorageClass**

k3s ships `local-path` as the default StorageClass. It works out of the box
for the `postgres-data` PVC.

**Ingress**

k3s ships Traefik by default. Leave the default in `values.yaml`, or set
`INGRESS_CLASS=traefik` in `.env`.

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

**Access**

Ingress on whatever hostname you set via the wizard. Create a DNS A record
pointing at the k3s node's IP.

`○ Untested in Phase 0; please report results.`

---

## EKS (AWS)

**Prereqs**
- `aws` CLI configured (`aws sts get-caller-identity` works)
- EKS cluster running, kubeconfig updated
  (`aws eks update-kubeconfig --name <cluster>`)
- `aws-iam-authenticator` in your kubeconfig (or the AWS CLI v2 token provider)

**StorageClass**

Install the **EBS CSI driver** (recommended) or EFS CSI driver. Default is
`gp2` which works for Phase 0; `gp3` is cheaper.

```
STORAGE_CLASS=gp2   # or gp3 with EBS CSI driver
```

**Ingress**

The **AWS Load Balancer Controller** (ALB) is the cleanest option. NGINX
ingress also works.

```
INGRESS_CLASS=alb   # or nginx
```

**DNS**

Create a Route 53 A record pointing at the LB DNS name, or use the
**external-dns** controller to do it automatically.

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

`○ Untested in Phase 0; please report results.`

---

## GKE (Google Cloud)

**Prereqs**
- `gcloud` configured (`gcloud auth list` shows your account)
- GKE cluster running, kubeconfig updated
  (`gcloud container clusters get-credentials <cluster> --region <region>`)
- `gke-gcloud-auth-plugin` installed
  (`gcloud components install gke-gcloud-auth-plugin`)

**StorageClass**

GKE ships `standard-rwo` as the default — works for Postgres.

```
STORAGE_CLASS=standard-rwo
```

**Ingress**

GCE Ingress (default) or NGINX. The GCE ingress is GKE-native and integrates
with Google Cloud Load Balancing.

```
INGRESS_CLASS=gce   # or nginx
```

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

`○ Untested in Phase 0; please report results.`

---

## AKS (Azure)

**Prereqs**
- `az` CLI configured (`az account show` works)
- AKS cluster running, kubeconfig merged
  (`az aks get-credentials --resource-group <rg> --name <cluster>`)

**StorageClass**

AKS ships `default` (managed-csi) — works.

```
STORAGE_CLASS=default
```

**Ingress**

Application Gateway Ingress Controller (AGIC) or NGINX.

```
INGRESS_CLASS=azure-application-gateway   # or nginx
```

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

`○ Untested in Phase 0; please report results.`

---

## Any other K8s (k0s, KIND, Rancher, OpenShift, etc.)

**Prereqs**
- A working `kubectl` context with admin (or namespace-admin) permissions
- A default StorageClass (`kubectl get sc` shows one with `(default)`)
- An ingress controller (`kubectl get pods -A | grep -E 'ingress|traefik|nginx'`)

**Install**

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity && ./install.sh
```

The preflight subsystem probes what's there. If it can't auto-detect a
StorageClass or an ingress class, the wizard asks you to pick.

`○ Untested in Phase 0; please report results.`

---

## Reporting results

If you successfully (or unsuccessfully) deploy on a target marked `○`, please
open an issue tagged `verified:<target>` with:
- Your target + version
- Any non-default values you used
- The output of `./install.sh verify`

That converts the badge to `✓` for the next user.
