# shellcheck shell=bash
# ObserVIBElity shared lib: OS detection + per-tool installer (static binary or system package manager).

source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"

# detect_os — export OS_FAMILY, OS_ARCH, OS_DISTRO.
#   OS_FAMILY: linux | darwin
#   OS_ARCH:   amd64 | arm64
#   OS_DISTRO: debian | ubuntu | rhel | fedora | alpine | arch | macos | unknown
detect_os() {
    local kernel machine
    kernel="$(uname -s)"
    machine="$(uname -m)"

    case "${kernel}" in
        Linux)   OS_FAMILY="linux"  ;;
        Darwin)  OS_FAMILY="darwin" ;;
        *)       die "detect_os: unsupported OS kernel '${kernel}'" ;;
    esac

    case "${machine}" in
        x86_64|amd64)    OS_ARCH="amd64" ;;
        arm64|aarch64)   OS_ARCH="arm64" ;;
        *)               die "detect_os: unsupported architecture '${machine}'" ;;
    esac

    if [[ "${OS_FAMILY}" == "darwin" ]]; then
        OS_DISTRO="macos"
    elif [[ -r /etc/os-release ]]; then
        local id_field id_like
        # shellcheck disable=SC1091
        id_field="$(. /etc/os-release && printf '%s' "${ID:-}")"
        # shellcheck disable=SC1091
        id_like="$(. /etc/os-release && printf '%s' "${ID_LIKE:-}")"
        case "${id_field}" in
            debian)              OS_DISTRO="debian" ;;
            ubuntu)              OS_DISTRO="ubuntu" ;;
            rhel|centos|rocky|almalinux) OS_DISTRO="rhel" ;;
            fedora)              OS_DISTRO="fedora" ;;
            alpine)              OS_DISTRO="alpine" ;;
            arch|manjaro)        OS_DISTRO="arch" ;;
            *)
                case "${id_like}" in
                    *debian*) OS_DISTRO="debian" ;;
                    *rhel*|*fedora*) OS_DISTRO="rhel" ;;
                    *arch*)   OS_DISTRO="arch" ;;
                    *)        OS_DISTRO="unknown" ;;
                esac
                ;;
        esac
    else
        OS_DISTRO="unknown"
    fi

    export OS_FAMILY OS_ARCH OS_DISTRO
}

# _os_bindir — echo the local tools/bin directory and ensure it exists + on PATH.
_os_bindir() {
    : "${REPO_ROOT:?REPO_ROOT must be set by caller}"
    local bindir="${REPO_ROOT}/tools/bin"
    mkdir -p "${bindir}" || die "_os_bindir: could not create ${bindir}"
    case ":${PATH}:" in
        *":${bindir}:"*) ;;
        *) export PATH="${bindir}:${PATH}" ;;
    esac
    printf '%s' "${bindir}"
}

# _os_download <url> <dest> — fetch with curl, fall back to wget. Die on failure.
_os_download() {
    local url="$1"
    local dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "${dest}" "${url}" || die "download failed: ${url}"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "${dest}" "${url}" || die "download failed: ${url}"
    else
        die "neither curl nor wget available; cannot download ${url}"
    fi
}

# _os_system_install <tool> — install via OS package manager.
_os_system_install() {
    local tool="$1"
    case "${OS_DISTRO}" in
        macos)
            command -v brew >/dev/null 2>&1 || die "brew not installed; cannot install ${tool}"
            brew install "${tool}" || die "brew install ${tool} failed"
            ;;
        debian|ubuntu)
            sudo apt-get update -qq && sudo apt-get install -y "${tool}" \
                || die "apt-get install ${tool} failed"
            ;;
        fedora|rhel)
            sudo dnf install -y "${tool}" || die "dnf install ${tool} failed"
            ;;
        arch)
            sudo pacman -S --noconfirm "${tool}" || die "pacman install ${tool} failed"
            ;;
        alpine)
            sudo apk add --no-cache "${tool}" || die "apk add ${tool} failed"
            ;;
        *)
            die "system install not supported on distro '${OS_DISTRO}' (set OBSERVIBELITY_SYSTEM_INSTALL=0 to use static binaries)"
            ;;
    esac
}

# _os_verify <tool> — run version check; die on failure.
_os_verify() {
    local tool="$1"
    case "${tool}" in
        kubectl) kubectl version --client >/dev/null 2>&1 || die "kubectl install verify failed" ;;
        helm)    helm version >/dev/null 2>&1 || die "helm install verify failed" ;;
        gh)      gh --version >/dev/null 2>&1 || die "gh install verify failed" ;;
        k3d)     k3d version >/dev/null 2>&1 || die "k3d install verify failed" ;;
        jq)      jq --version >/dev/null 2>&1 || die "jq install verify failed" ;;
        yq)      yq --version >/dev/null 2>&1 || die "yq install verify failed" ;;
        *)       die "_os_verify: unknown tool '${tool}'" ;;
    esac
}

# _os_install_static <tool> — download official static binary to tools/bin.
_os_install_static() {
    local tool="$1"
    local bindir
    bindir="$(_os_bindir)"

    case "${tool}" in
        kubectl)
            local stable
            stable="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" \
                || die "kubectl: could not fetch stable version pointer"
            local url="https://dl.k8s.io/release/${stable}/bin/${OS_FAMILY}/${OS_ARCH}/kubectl"
            _os_download "${url}" "${bindir}/kubectl"
            chmod +x "${bindir}/kubectl"
            ;;
        helm)
            local url="https://get.helm.sh/helm-v3.13.3-${OS_FAMILY}-${OS_ARCH}.tar.gz"
            local tmpdir
            tmpdir="$(mktemp -d)" || die "helm: mktemp failed"
            _os_download "${url}" "${tmpdir}/helm.tar.gz"
            tar -xzf "${tmpdir}/helm.tar.gz" -C "${tmpdir}" \
                || { rm -rf "${tmpdir}"; die "helm: extract failed"; }
            mv "${tmpdir}/${OS_FAMILY}-${OS_ARCH}/helm" "${bindir}/helm" \
                || { rm -rf "${tmpdir}"; die "helm: move binary failed"; }
            chmod +x "${bindir}/helm"
            rm -rf "${tmpdir}"
            ;;
        gh)
            local url="https://github.com/cli/cli/releases/download/v2.40.1/gh_2.40.1_${OS_FAMILY}_${OS_ARCH}.tar.gz"
            local tmpdir
            tmpdir="$(mktemp -d)" || die "gh: mktemp failed"
            _os_download "${url}" "${tmpdir}/gh.tar.gz"
            tar -xzf "${tmpdir}/gh.tar.gz" -C "${tmpdir}" \
                || { rm -rf "${tmpdir}"; die "gh: extract failed"; }
            mv "${tmpdir}/gh_2.40.1_${OS_FAMILY}_${OS_ARCH}/bin/gh" "${bindir}/gh" \
                || { rm -rf "${tmpdir}"; die "gh: move binary failed"; }
            chmod +x "${bindir}/gh"
            rm -rf "${tmpdir}"
            ;;
        k3d)
            local url="https://github.com/k3d-io/k3d/releases/download/v5.6.0/k3d-${OS_FAMILY}-${OS_ARCH}"
            _os_download "${url}" "${bindir}/k3d"
            chmod +x "${bindir}/k3d"
            ;;
        jq)
            local url="https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-${OS_FAMILY}-${OS_ARCH}"
            _os_download "${url}" "${bindir}/jq"
            chmod +x "${bindir}/jq"
            ;;
        yq)
            local url="https://github.com/mikefarah/yq/releases/download/v4.40.5/yq_${OS_FAMILY}_${OS_ARCH}"
            _os_download "${url}" "${bindir}/yq"
            chmod +x "${bindir}/yq"
            ;;
        *)
            die "_os_install_static: unsupported tool '${tool}'"
            ;;
    esac
}

# pkg_install <tool> — install one of: kubectl, helm, gh, k3d, jq, yq.
# Default: static binary into ${REPO_ROOT}/tools/bin. With
# OBSERVIBELITY_SYSTEM_INSTALL=1: use OS package manager.
pkg_install() {
    local tool="$1"
    case "${tool}" in
        kubectl|helm|gh|k3d|jq|yq) ;;
        *) die "pkg_install: unsupported tool '${tool}' (supported: kubectl helm gh k3d jq yq)" ;;
    esac

    if [[ -z "${OS_FAMILY:-}" || -z "${OS_ARCH:-}" || -z "${OS_DISTRO:-}" ]]; then
        detect_os
    fi

    log "installing ${tool} (family=${OS_FAMILY} arch=${OS_ARCH} distro=${OS_DISTRO})"

    if [[ "${OBSERVIBELITY_SYSTEM_INSTALL:-0}" == "1" ]]; then
        _os_system_install "${tool}"
    else
        _os_install_static "${tool}"
    fi

    _os_verify "${tool}"
    ok "${tool} installed"
}
