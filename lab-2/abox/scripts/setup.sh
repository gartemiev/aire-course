#!/bin/bash
set -euo pipefail

LOG=/tmp/setup.log
exec > >(tee -a "$LOG") 2>&1

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "=== k8sdiy-env setup start ==="

# Install OpenTofu
log "Installing OpenTofu..."
curl -fsSL https://get.opentofu.org/install-opentofu.sh | sh -s -- --install-method standalone
log "OpenTofu installed"

# Install K9s
log "Installing K9s..."
curl -sS https://webi.sh/k9s | sh
log "K9s installed"

# Install Capacitor Next (local Flux UI binary)
log "Installing Capacitor Next..."
case "$(uname -s)" in
  Linux)  CAP_OS=Linux ;;
  Darwin) CAP_OS=Darwin ;;
  *)      log "Unsupported OS for Capacitor Next; skipping"; CAP_OS= ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  CAP_ARCH=x86_64 ;;
  arm64|aarch64) CAP_ARCH=arm64 ;;
  *)             log "Unsupported arch for Capacitor Next; skipping"; CAP_ARCH= ;;
esac
if [[ -n "${CAP_OS:-}" && -n "${CAP_ARCH:-}" ]]; then
  CAP_TAG=$(curl -fsSL https://api.github.com/repos/gimlet-io/capacitor/releases/latest \
    | grep '"tag_name"' | cut -d'"' -f4)
  mkdir -p "${HOME}/.local/bin"
  curl -fsSL "https://github.com/gimlet-io/capacitor/releases/download/${CAP_TAG}/next-${CAP_OS}-${CAP_ARCH}" \
    -o "${HOME}/.local/bin/next"
  chmod +x "${HOME}/.local/bin/next"
  log "Capacitor Next ${CAP_TAG} installed at ${HOME}/.local/bin/next"
fi

# Add aliases to bashrc
cat >> ~/.bashrc <<'EOF'

# k8sdiy-env aliases
alias kk="EDITOR='code --wait' k9s"
alias tf=tofu
alias k=kubectl
export PATH="$HOME/.local/bin:$PATH"
EOF

# Initialize Tofu
log "Running tofu init..."
cd bootstrap
tofu init
log "tofu init done"

log "Running tofu apply..."
tofu apply -auto-approve
log "tofu apply done"

export KUBECONFIG=~/.kube/config

cd ..

# Install cloud-provider-kind (LoadBalancer support)
log "Installing cloud-provider-kind..."
case "$(uname -s)" in
  Linux)  CPK_OS=linux ;;
  Darwin) CPK_OS=darwin ;;
  *)
    log "Unsupported OS: $(uname -s); skipping cloud-provider-kind"
    CPK_OS=
    ;;
esac
case "$(uname -m)" in
  x86_64|amd64) CPK_ARCH=amd64 ;;
  arm64|aarch64) CPK_ARCH=arm64 ;;
  *)
    log "Unsupported arch: $(uname -m); skipping cloud-provider-kind"
    CPK_ARCH=
    ;;
esac
if [[ -n "${CPK_OS:-}" && -n "${CPK_ARCH:-}" ]]; then
  CPK_URL="https://github.com/kubernetes-sigs/cloud-provider-kind/releases/download/v0.6.0/cloud-provider-kind_0.6.0_${CPK_OS}_${CPK_ARCH}.tar.gz"
  curl -fsSL "$CPK_URL" -o /tmp/cloud-provider-kind.tar.gz
  tar -xzf /tmp/cloud-provider-kind.tar.gz -C /tmp cloud-provider-kind
  rm -f /tmp/cloud-provider-kind.tar.gz
  nohup /tmp/cloud-provider-kind > /tmp/cloud-provider-kind.log 2>&1 &
  log "cloud-provider-kind started (pid $!)"
fi


log "=== setup complete ==="
log ""
log "Flux UI (Capacitor Next):  KUBECONFIG=\"$PWD/bootstrap/abox-config\" next  (then open http://localhost:4739)"
