# Deploying to local k3s

If you have a k3s cluster on your dev machine, you can deploy ObserVIBElity without going through any external container registry. Images are built with `docker`, saved as tarballs, and imported directly into k3s's containerd.

## Prerequisites
- k3s installed and running
- `docker` (or podman with docker compat) for building
- `kubectl` configured against the k3s cluster
- Passwordless sudo (k3s containerd ops require root)

## One-command deploy

```bash
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity
cp .env.example .env && $EDITOR .env   # fill in creds
make deploy-k3s-local
```

This will:
1. Build 13 images via `docker build` (~5-10 min the first time, cached after)
2. Save each as a tar and `sudo k3s ctr images import`
3. Run `helm upgrade --install` with `imagePullPolicy=IfNotPresent` so k3s uses the imported images
4. Wait for all pods Ready
5. Run verify.sh to confirm health

## Remote k3s node

If your k3s runs on a different machine:

```bash
./tools/k3s-import-images.sh --remote pi@k3s.lan
```

This ssh's to the node, scp's each tar, runs `sudo k3s ctr images import`. Requires passwordless ssh + sudo on the target.

## Rebuilding after code changes

```bash
make images-local                # rebuilds + reimports just the changed images
kubectl rollout restart -n observibelity deployment/<app>
```

Or filter to a single image:
```bash
./tools/k3s-import-images.sh --filter neoncart
kubectl rollout restart -n observibelity deployment/neoncart
```

## Cleanup

```bash
make dev-down                         # uninstall the release
docker images "ghcr.io/stephenwagner-grafana/observibelity-*" -q | xargs docker rmi
sudo k3s ctr images ls | grep observibelity | awk '{print $1}' | xargs -I {} sudo k3s ctr images rm {}
```

## Caveats
- Image arch: locally-built images are `linux/amd64` by default. If your k3s nodes are arm64, use `docker buildx build --platform linux/arm64`.
- Sudo required: k3s containerd ops need root.
- Disk space: 13 images × ~500 MB each = ~6 GB. Prune unused with `docker system prune`.

## See also
- `docs/INSTALL.md` for the full install flow
- `docs/DEVELOPMENT.md` for the 4-loop iteration design
