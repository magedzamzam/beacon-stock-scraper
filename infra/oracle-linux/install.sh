#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Beacon Screener — bootstrap script for Oracle Linux 9 (works on RHEL 9 / Rocky 9).
# Installs Docker CE, Docker Compose plugin, opens firewall ports 80/443,
# and prepares a systemd unit so the stack auto-starts on boot.
# -----------------------------------------------------------------------------
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo $0)"; exit 1
fi

REPO_DIR="${REPO_DIR:-/opt/beacon-screener}"
SERVICE_USER="${SERVICE_USER:-beacon}"

echo ">> 1/7  Updating system packages"
dnf -y update

echo ">> 2/7  Installing prerequisites"
dnf -y install dnf-plugins-core git curl wget firewalld policycoreutils-python-utils

echo ">> 3/7  Installing Docker CE + Compose plugin"
if ! command -v docker >/dev/null; then
  dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo ">> 4/7  Creating service user '${SERVICE_USER}'"
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd -r -m -s /bin/bash "${SERVICE_USER}"
fi
usermod -aG docker "${SERVICE_USER}"

echo ">> 5/7  Configuring firewall (open 80, 443)"
systemctl enable --now firewalld
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload

echo ">> 6/7  Cloning / preparing repo at ${REPO_DIR}"
if [[ ! -d "${REPO_DIR}/.git" ]]; then
  echo "    Repo not present. Clone your fork manually:"
  echo "      sudo git clone https://github.com/<you>/beacon-screener.git ${REPO_DIR}"
  echo "      sudo chown -R ${SERVICE_USER}:${SERVICE_USER} ${REPO_DIR}"
else
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${REPO_DIR}"
fi

if [[ -f "${REPO_DIR}/.env.example" && ! -f "${REPO_DIR}/.env" ]]; then
  cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
  chmod 600 "${REPO_DIR}/.env"
  chown "${SERVICE_USER}:${SERVICE_USER}" "${REPO_DIR}/.env"
  echo "    Created ${REPO_DIR}/.env — edit it before starting the stack."
fi

echo ">> 7/7  Installing systemd unit"
cat >/etc/systemd/system/beacon-screener.service <<EOF
[Unit]
Description=Beacon Screener (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable beacon-screener.service

cat <<'EOF'

✓ Bootstrap complete.

Next steps:
  1. If you haven't yet:
       sudo git clone https://github.com/<you>/beacon-screener.git /opt/beacon-screener
       sudo chown -R beacon:beacon /opt/beacon-screener

  2. Edit the environment file (set DB_PASSWORD, JWT_SECRET, PUBLIC_HOST):
       sudo -u beacon vi /opt/beacon-screener/.env

  3. Apply the database migration (one-time):
       sudo -u beacon psql -h db.magedzamzam.ae -U magedzamzam -d beacon \
            -f /opt/beacon-screener/db/migrations/001_enhancements.sql

  4. Start the stack:
       sudo systemctl start beacon-screener

  5. View logs:
       cd /opt/beacon-screener && sudo docker compose logs -f

  6. Make the first user an admin (run inside the container):
       docker compose exec api python -c \
         "from shared.db import SessionLocal, User; \
          s=SessionLocal(); u=s.query(User).first(); u.is_admin=True; s.commit(); print('OK')"

EOF
