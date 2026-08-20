#!/usr/bin/env bash
# Prepares a fresh Ubuntu 24.04 Compute Engine VM to run the stack:
# Docker Engine + the compose plugin, git, and a swapfile.
#
# Run once, on the VM, as a normal (non-root) user with sudo:
#   bash infra/gcp/bootstrap.sh
#
# Log out and back in afterwards so the new docker group membership applies.

set -euo pipefail

echo "==> apt update + base packages"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl git make jq

echo "==> Docker Engine (official apt repository)"
sudo install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

echo "==> add $USER to the docker group"
sudo usermod -aG docker "$USER"

# The image build resolves and compiles the whole dependency tree; on a
# 2-vCPU/8 GB instance that peaks close to the RAM ceiling and the OOM killer
# takes uv down mid-sync. Swap makes the build survive on the smaller shapes.
if [ ! -f /swapfile ]; then
  echo "==> 4 GB swapfile"
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> capping container log growth (default json-file driver never rotates)"
sudo mkdir -p /etc/docker
echo '{"log-driver":"json-file","log-opts":{"max-size":"20m","max-file":"5"}}' \
  | sudo tee /etc/docker/daemon.json >/dev/null
sudo systemctl restart docker

echo
echo "Done. Log out and back in (or run: newgrp docker), then continue with"
echo "docs/14-gcp-vm-deploy.md step 5."
