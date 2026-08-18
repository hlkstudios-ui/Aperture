#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$BASE_DIR/../../.." && pwd)
INPUT="$ROOT_DIR/.env"
MODE=${2:-}

if [ "${1:-}" != "--mode" ] || { [ "$MODE" != "audit" ] && [ "$MODE" != "apply" ]; }; then
  echo "usage: bootstrap_host.sh --mode {audit|apply}" >&2
  exit 2
fi

python3 "$BASE_DIR/validate_host_hardening.py" --input "$INPUT" --mode "$MODE"

if [ "$MODE" = "audit" ]; then
  exec python3 "$BASE_DIR/host_audit.py" --config "$INPUT" \
    --prometheus-output /var/lib/aperture/metrics/host-audit.prom
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "apply mode must run as root on the Hostinger VPS" >&2
  exit 1
fi

EXPECTED_HOSTNAME=$(python3 "$BASE_DIR/read_env.py" --input "$INPUT" --label EXPECTED_HOSTNAME)
SSH_ALLOWED_CIDR=$(python3 "$BASE_DIR/read_env.py" --input "$INPUT" --label SSH_ALLOWED_CIDR)

if [ "$(hostname -f)" != "$EXPECTED_HOSTNAME" ]; then
  echo "current hostname does not match EXPECTED_HOSTNAME" >&2
  exit 1
fi

SSH_CONNECTION_VALUE=${SSH_CONNECTION:-}
REMOTE_IP=${SSH_CONNECTION_VALUE%% *}
if [ -z "$REMOTE_IP" ]; then
  echo "apply mode requires a current SSH connection" >&2
  exit 1
fi
python3 - "$REMOTE_IP" "$SSH_ALLOWED_CIDR" <<'PY'
import ipaddress
import sys
if ipaddress.ip_address(sys.argv[1]) not in ipaddress.ip_network(sys.argv[2], strict=False):
    raise SystemExit("current SSH source is outside SSH_ALLOWED_CIDR")
PY

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install --no-install-recommends -y unattended-upgrades fail2ban ufw jq ca-certificates

temporary=$(mktemp -d /tmp/aperture-host-hardening.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

cat >"$temporary/60-aperture-hardening.conf" <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
MaxAuthTries 3
LoginGraceTime 30
EOF
install -o root -g root -m 0644 "$temporary/60-aperture-hardening.conf" /etc/ssh/sshd_config.d/60-aperture-hardening.conf
/usr/sbin/sshd -t

daemon=/etc/docker/daemon.json
if [ -f "$daemon" ]; then
  jq '. + {"live-restore":true,"no-new-privileges":true,"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"5"}}' "$daemon" >"$temporary/daemon.json"
else
  printf '%s\n' '{"live-restore":true,"no-new-privileges":true,"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"5"}}' >"$temporary/daemon.json"
fi
jq -e . "$temporary/daemon.json" >/dev/null
install -o root -g root -m 0644 "$temporary/daemon.json" "$daemon"

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$SSH_ALLOWED_CIDR" to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

systemctl enable --now unattended-upgrades fail2ban docker
systemctl reload ssh
systemctl reload docker || systemctl restart docker

python3 "$BASE_DIR/host_audit.py" --config "$INPUT" \
  --prometheus-output /var/lib/aperture/metrics/host-audit.prom
