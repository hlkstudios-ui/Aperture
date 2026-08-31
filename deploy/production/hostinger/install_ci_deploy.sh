#!/bin/sh
set -eu

ACCOUNT=aperture-deploy
ACCOUNT_HOME=/var/lib/aperture-deploy
INCOMING_ROOT=$ACCOUNT_HOME/incoming
CONTROLLER_DIR=/usr/local/sbin
CONTROLLER=$CONTROLLER_DIR/aperture-deploy-release
SUDOERS_FILE=/etc/sudoers.d/aperture-deploy
RECOVERY_UNIT=/etc/systemd/system/aperture-deploy-recovery.service
GC_UNIT=/etc/systemd/system/aperture-deploy-gc.service
GC_TIMER=/etc/systemd/system/aperture-deploy-gc.timer
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PUBLIC_KEY_FILE=
unit_temp=
gc_unit_temp=
gc_timer_temp=

fail() {
  echo "$1" >&2
  exit 1
}

require_root_directory() {
  path=$1
  mode=$2
  if [ -L "$path" ] || [ ! -d "$path" ]; then
    fail "$path must be a real directory"
  fi
  if [ "$(stat -c %u:%g "$path")" != "0:0" ] || \
     [ "$(stat -c %a "$path")" != "$mode" ]; then
    fail "$path has unsafe ownership or permissions"
  fi
}

require_existing_directory() {
  path=$1
  owner=$2
  group=$3
  mode=$4
  if [ -L "$path" ] || [ ! -d "$path" ]; then
    fail "$path must be a real directory"
  fi
  if [ "$(stat -c %u "$path")" != "$owner" ] || \
     [ "$(stat -c %g "$path")" != "$group" ] || \
     [ "$(stat -c %a "$path")" != "$mode" ]; then
    fail "$path has unsafe ownership or permissions"
  fi
}

require_existing_file() {
  path=$1
  owner=$2
  group=$3
  mode=$4
  if [ -L "$path" ] || [ ! -f "$path" ]; then
    fail "$path must be a regular non-symlink file"
  fi
  if [ "$(stat -c %u "$path")" != "$owner" ] || \
     [ "$(stat -c %g "$path")" != "$group" ] || \
     [ "$(stat -c %a "$path")" != "$mode" ]; then
    fail "$path has unsafe ownership or permissions"
  fi
}

usage() {
  echo "usage: install_ci_deploy.sh --public-key-file PATH" >&2
  exit 2
}

if [ "$(id -u)" -ne 0 ]; then
  echo "CI deploy installation must run as root" >&2
  exit 1
fi

if [ -L "$BASE_DIR/deploy_release.py" ] || \
   [ ! -f "$BASE_DIR/deploy_release.py" ]; then
  fail "deployment controller source must be a regular non-symlink file"
fi
controller_shebang=$(sed -n '1p' "$BASE_DIR/deploy_release.py")
if [ "$controller_shebang" != '#!/usr/bin/python3' ] || \
   LC_ALL=C grep -q "$(printf '\r')" "$BASE_DIR/deploy_release.py"; then
  fail "deployment controller must use an exact LF-only Python shebang"
fi

if [ "${1:-}" != "--public-key-file" ] || [ "$#" -ne 2 ]; then
  usage
fi
PUBLIC_KEY_FILE=$2

if [ -L "$PUBLIC_KEY_FILE" ] || [ ! -f "$PUBLIC_KEY_FILE" ]; then
  echo "deploy public key must be a regular non-symlink file" >&2
  exit 1
fi
if [ "$(wc -l < "$PUBLIC_KEY_FILE" | tr -d ' ')" -ne 1 ]; then
  echo "deploy public key file must contain exactly one key" >&2
  exit 1
fi
public_key=$(sed -n '1p' "$PUBLIC_KEY_FILE")
case "$public_key" in
  ssh-ed25519\ *) ;;
  *) echo "deploy key must be an Ed25519 OpenSSH public key" >&2; exit 1 ;;
esac
ssh-keygen -l -f "$PUBLIC_KEY_FILE" >/dev/null

if id "$ACCOUNT" >/dev/null 2>&1; then
  passwd_entry=$(getent passwd "$ACCOUNT")
  if [ "$(printf '%s\n' "$passwd_entry" | wc -l | tr -d ' ')" -ne 1 ]; then
    fail "dedicated deploy account must have exactly one passwd entry"
  fi
  account_uid=$(id -u "$ACCOUNT")
  if [ "$account_uid" -eq 0 ]; then
    fail "dedicated deploy account must not be root"
  fi
  account_gid=$(id -g "$ACCOUNT")
  if [ "$account_gid" -eq 0 ]; then
    fail "dedicated deploy account must not use the root group"
  fi
  recorded_home=$(printf '%s\n' "$passwd_entry" | cut -d: -f6)
  if [ "$recorded_home" != "$ACCOUNT_HOME" ]; then
    fail "existing deploy account has an unexpected home"
  fi
  recorded_shell=$(printf '%s\n' "$passwd_entry" | cut -d: -f7)
  if [ "$recorded_shell" != "/bin/bash" ]; then
    fail "existing deploy account has an unsafe shell"
  fi
  account_group=$(id -gn "$ACCOUNT")
  if [ "$account_group" != "$ACCOUNT" ]; then
    fail "dedicated deploy account must use its private primary group"
  fi
  if [ "$(id -G "$ACCOUNT")" != "$account_gid" ]; then
    fail "dedicated deploy account must not have supplementary groups"
  fi
  shadow_entry=$(getent shadow "$ACCOUNT")
  if [ "$(printf '%s\n' "$shadow_entry" | wc -l | tr -d ' ')" -ne 1 ]; then
    fail "dedicated deploy account must have exactly one shadow entry"
  fi
  password_field=$(printf '%s\n' "$shadow_entry" | cut -d: -f2)
  case "$password_field" in
    \!*|\**) ;;
    *) fail "dedicated deploy account password must remain locked" ;;
  esac
  password_status=$(passwd -S "$ACCOUNT" | awk '{print $2}')
  case "$password_status" in
    L|LK) ;;
    *) fail "dedicated deploy account password must remain locked" ;;
  esac
else
  if getent group "$ACCOUNT" >/dev/null 2>&1; then
    fail "pre-existing deploy group requires manual review"
  fi
  groupadd --system "$ACCOUNT"
  useradd --system --gid "$ACCOUNT" --home-dir "$ACCOUNT_HOME" \
    --shell /bin/bash --no-create-home "$ACCOUNT"
  usermod --lock "$ACCOUNT"
  account_uid=$(id -u "$ACCOUNT")
  account_gid=$(id -g "$ACCOUNT")
  account_group=$ACCOUNT
fi

if [ ! -x /usr/bin/systemd-run ] || [ ! -d /run/systemd/system ]; then
  fail "systemd transient services are required for durable deployment"
fi
require_root_directory /etc/systemd/system 755
if [ -e "$RECOVERY_UNIT" ] || [ -L "$RECOVERY_UNIT" ]; then
  require_existing_file "$RECOVERY_UNIT" 0 0 644
fi
if [ -e "$GC_UNIT" ] || [ -L "$GC_UNIT" ]; then
  require_existing_file "$GC_UNIT" 0 0 644
fi
if [ -e "$GC_TIMER" ] || [ -L "$GC_TIMER" ]; then
  require_existing_file "$GC_TIMER" 0 0 644
fi

if [ -x /usr/sbin/sshd ]; then
  effective_sshd=$(/usr/sbin/sshd -T)
  if ! printf '%s\n' "$effective_sshd" | grep -Fqx 'pubkeyauthentication yes'; then
    echo "effective sshd policy does not permit public-key authentication" >&2
    exit 1
  fi
fi

# The account can write only the incoming spool.  Root owns its SSH policy and
# every production/runtime path, so a compromised deploy job cannot replace the
# controller, keys, release baseline, or live credentials.
require_root_directory /var 755
require_root_directory /var/lib 755
if [ -e "$ACCOUNT_HOME" ] || [ -L "$ACCOUNT_HOME" ]; then
  require_existing_directory "$ACCOUNT_HOME" 0 0 755
fi
install -d -o root -g root -m 0755 "$ACCOUNT_HOME"
if [ -e "$INCOMING_ROOT" ] || [ -L "$INCOMING_ROOT" ]; then
  require_existing_directory "$INCOMING_ROOT" "$account_uid" "$account_gid" 700
fi
install -d -o "$ACCOUNT" -g "$account_group" -m 0700 "$INCOMING_ROOT"
if [ -e "$ACCOUNT_HOME/.ssh" ] || [ -L "$ACCOUNT_HOME/.ssh" ]; then
  require_existing_directory "$ACCOUNT_HOME/.ssh" 0 0 755
fi
install -d -o root -g root -m 0755 "$ACCOUNT_HOME/.ssh"
if [ -e "$ACCOUNT_HOME/.ssh/authorized_keys" ] || \
   [ -L "$ACCOUNT_HOME/.ssh/authorized_keys" ]; then
  require_existing_file "$ACCOUNT_HOME/.ssh/authorized_keys" 0 0 444
fi

key_temp=$(mktemp "$ACCOUNT_HOME/.ssh/.authorized_keys.XXXXXX")
sudoers_temp=$(mktemp /etc/sudoers.d/.aperture-deploy.XXXXXX)
unit_temp=$(mktemp /etc/systemd/system/.aperture-deploy-recovery.XXXXXX)
gc_unit_temp=$(mktemp /etc/systemd/system/.aperture-deploy-gc-service.XXXXXX)
gc_timer_temp=$(mktemp /etc/systemd/system/.aperture-deploy-gc-timer.XXXXXX)
trap 'rm -f -- "$key_temp" "$sudoers_temp" "$unit_temp" "$gc_unit_temp" "$gc_timer_temp"' EXIT
printf 'restrict %s\n' "$public_key" >"$key_temp"
# sshd reads AuthorizedKeysFile after dropping to the target account on this
# host. Keep the public key root-owned and immutable to the deploy account, but
# world-readable so that the unprivileged authentication process can open it.
chmod 0444 "$key_temp"
chown root:root "$key_temp"
mv -f -- "$key_temp" "$ACCOUNT_HOME/.ssh/authorized_keys"

install -d -o root -g root -m 0755 "$CONTROLLER_DIR"
install -o root -g root -m 0755 "$BASE_DIR/deploy_release.py" "$CONTROLLER"

install -d -o root -g root -m 0755 /etc/aperture
install -d -o root -g root -m 0755 /opt/aperture
install -d -o root -g root -m 0700 /opt/aperture/shared
install -d -o root -g root -m 0755 /opt/aperture/releases
install -d -o root -g root -m 0700 /opt/aperture/release-history
if [ -e /opt/aperture/deploy-attempts ] || \
   [ -L /opt/aperture/deploy-attempts ]; then
  require_existing_directory /opt/aperture/deploy-attempts 0 0 700
fi
install -d -o root -g root -m 0700 /opt/aperture/deploy-attempts
install -d -o root -g root -m 0700 /opt/aperture/deploy-jobs
install -d -o root -g root -m 0700 /opt/aperture/deploy-status

cat >"$unit_temp" <<EOF
[Unit]
Description=Aperture interrupted production deployment recovery
ConditionPathIsDirectory=|/opt/aperture/deploy-transaction
ConditionPathIsDirectory=|/opt/aperture/deploy-transaction.completed
Wants=docker.service network-online.target
After=docker.service network-online.target
RefuseManualStop=yes

[Service]
Type=exec
User=root
Group=root
UMask=0077
ExecStart=$CONTROLLER --recover
Restart=on-failure
RestartSec=5s
RuntimeMaxSec=3h
TimeoutStopSec=30min
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ReadWritePaths=/opt/aperture -/var/lib/aperture

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$unit_temp"
chown root:root "$unit_temp"
mv -f -- "$unit_temp" "$RECOVERY_UNIT"

cat >"$gc_unit_temp" <<EOF
[Unit]
Description=Aperture bounded production release garbage collection
ConditionPathIsRegularFile=/etc/aperture/production-launch-enabled
ConditionPathExists=/opt/aperture/current
Wants=docker.service network-online.target
After=docker.service network-online.target
RefuseManualStop=yes

[Service]
Type=exec
User=root
Group=root
UMask=0077
ExecStart=$CONTROLLER --gc
Restart=on-failure
RestartSec=5m
RuntimeMaxSec=3h
TimeoutStopSec=30min
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ReadWritePaths=/opt/aperture /var/lib/aperture-deploy -/var/lib/aperture
EOF
chmod 0644 "$gc_unit_temp"
chown root:root "$gc_unit_temp"
mv -f -- "$gc_unit_temp" "$GC_UNIT"

cat >"$gc_timer_temp" <<'EOF'
[Unit]
Description=Daily Aperture production release garbage collection

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=yes
Unit=aperture-deploy-gc.service

[Install]
WantedBy=timers.target
EOF
chmod 0644 "$gc_timer_temp"
chown root:root "$gc_timer_temp"
mv -f -- "$gc_timer_temp" "$GC_TIMER"

systemctl daemon-reload
systemctl enable aperture-deploy-recovery.service >/dev/null
systemctl enable --now aperture-deploy-gc.timer >/dev/null

cat >"$sudoers_temp" <<EOF
$ACCOUNT ALL=(root) NOPASSWD: $CONTROLLER
EOF
chmod 0440 "$sudoers_temp"
chown root:root "$sudoers_temp"
visudo -cf "$sudoers_temp" >/dev/null
mv -f -- "$sudoers_temp" "$SUDOERS_FILE"

# Deliberately do not create the launch marker, runtimes, or current symlink.
# Those represent a manually accepted production baseline, not host setup.
echo "Aperture CI deploy boundary installed; production remains launch-gated."
