#!/usr/bin/env bash
#
# setup-nomachine.sh — Deterministic NoMachine remote desktop setup for DGX Spark
#
# Installs NoMachine free edition (ARM64) and configures it for LAN-only access.
# Re-running this script is safe (idempotent).
#
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# ── Configuration ──────────────────────────────────────────────────────────────
NX_VERSION="9.3.7"
NX_BUILD="1"
NX_DEB="nomachine_${NX_VERSION}_${NX_BUILD}_arm64.deb"
NX_URL="https://download.nomachine.com/download/9.3/Arm/${NX_DEB}"
NX_MD5="8d4f9de8c95832e93675d58df57ac15e"
NX_CFG="/usr/NX/etc/server.cfg"
NX_PORT=4000
NX_TIMEOUT=30
LOGFILE="/tmp/setup-nomachine-$(date +%Y%m%d-%H%M%S).log"

# ── Helpers ────────────────────────────────────────────────────────────────────
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*" | tee -a "$LOGFILE"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*" | tee -a "$LOGFILE"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" | tee -a "$LOGFILE" >&2; exit 1; }

# Run an nxserver command, logging all output and return code
run_nx() {
    local label="$1"; shift
    info "Running: $*"
    echo "── $label ──" >> "$LOGFILE"
    local rc=0
    "$@" >> "$LOGFILE" 2>&1 || rc=$?
    # Also show NX output lines to the terminal
    grep '^NX>' "$LOGFILE" | tail -5
    echo "── exit code: $rc ──" >> "$LOGFILE"
    return $rc
}

require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)."
    fi
}

get_lan_ip() {
    ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1); exit}'
}

get_lan_subnet() {
    local iface
    iface=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1); exit}')
    ip -4 addr show dev "$iface" 2>/dev/null | awk '/inet /{print $2; exit}'
}

# ── Pre-flight ─────────────────────────────────────────────────────────────────
require_root

echo "=== setup-nomachine.sh started at $(date) ===" > "$LOGFILE"
info "Log file: $LOGFILE"

ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" ]]; then
    error "Expected aarch64 architecture, got $ARCH"
fi

LAN_IP=$(get_lan_ip)
LAN_SUBNET=$(get_lan_subnet)
info "Detected LAN IP: $LAN_IP"
info "Detected LAN subnet: $LAN_SUBNET"

# ── Step 1: Download ──────────────────────────────────────────────────────────
if dpkg -l nomachine 2>/dev/null | grep -q "^ii.*${NX_VERSION}"; then
    info "NoMachine ${NX_VERSION} is already installed, skipping download."
else
    TMPDIR=$(mktemp -d)
    trap 'rm -rf "$TMPDIR"' EXIT

    info "Downloading NoMachine ${NX_VERSION} for ARM64..."
    wget -q --show-progress --timeout=60 --tries=2 -O "${TMPDIR}/${NX_DEB}" "$NX_URL"

    # Verify checksum
    DL_MD5=$(md5sum "${TMPDIR}/${NX_DEB}" | awk '{print $1}')
    if [[ "$DL_MD5" != "$NX_MD5" ]]; then
        error "MD5 mismatch! Expected ${NX_MD5}, got ${DL_MD5}. Download may be corrupted."
    fi
    info "MD5 checksum verified."

    # ── Step 2: Install ───────────────────────────────────────────────────────
    info "Installing NoMachine..."
    dpkg -i --force-confold "${TMPDIR}/${NX_DEB}"
fi

# ── Step 3: Configure for LAN-only access ─────────────────────────────────────
info "Configuring NoMachine for LAN-only access..."

# Helper to set a config key in server.cfg
nx_set() {
    local key="$1" value="$2"
    if grep -q "^${key} " "$NX_CFG" 2>/dev/null; then
        sed -i "s|^${key} .*|${key} ${value}|" "$NX_CFG"
    elif grep -q "^#${key} " "$NX_CFG" 2>/dev/null; then
        sed -i "s|^#${key} .*|${key} ${value}|" "$NX_CFG"
    else
        echo "${key} ${value}" >> "$NX_CFG"
    fi
}

# Bind only to the LAN interface IP (not 0.0.0.0)
nx_set "ServerAddress" "$LAN_IP"

# Restrict connections to local subnet using NoMachine's built-in ACL
# AcceptedAuthenticationMethods — keep password auth for simplicity on LAN
nx_set "AcceptedAuthenticationMethods" "NX-private-key,NX-password,password"

# Enable NX user DB (required for --useradd/--userdel/--passwd to work)
nx_set "EnableUserDB" "1"

# Enable NX password DB so users can authenticate with an NX-specific password
# (required when SSH password auth is disabled on the server)
nx_set "EnablePasswordDB" "1"

# Disable grabbing the physical display (use virtual desktops) —
# or enable it if you want to mirror the physical screen:
nx_set "PhysicalDesktopAuthorization" "0"
nx_set "AutomaticDisconnection" "0"

# Verify EnablePasswordDB is set
if grep -q "^EnablePasswordDB 1" "$NX_CFG"; then
    info "Verified: EnablePasswordDB is set to 1 in $NX_CFG"
else
    error "Failed to set EnablePasswordDB in $NX_CFG"
fi

# Create a trusted networks rule — only allow connections from local subnet
NX_RULES="/usr/NX/etc/rules"
mkdir -p "$NX_RULES"
cat > "${NX_RULES}/trustednetworks" <<RULES_EOF
# Only allow connections from the local subnet
# Deny everything else
trusted-network ${LAN_SUBNET}
RULES_EOF

info "Wrote trusted network rule: ${LAN_SUBNET}"

# ── Step 4: Firewall (ufw) — if active, open port only for LAN ───────────────
if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
    info "Configuring UFW firewall..."
    ufw allow from "$(echo "$LAN_SUBNET" | cut -d/ -f1)/$(echo "$LAN_SUBNET" | cut -d/ -f2)" to any port "$NX_PORT" proto tcp comment "NoMachine LAN"
    ufw reload
else
    info "UFW not active. Consider enabling it for additional security:"
    info "  sudo ufw enable"
    info "  sudo ufw allow from ${LAN_SUBNET} to any port ${NX_PORT} proto tcp"
    info "  sudo ufw allow ssh"
fi

# ── Step 5: Restart NoMachine ─────────────────────────────────────────────────
info "Restarting NoMachine server..."

# Kill any stale nxserver/nxd processes before restart to avoid hangs
pkill -9 -f '/usr/NX/bin/nxserver.bin' 2>/dev/null || true
pkill -9 -f '/usr/NX/bin/nxd' 2>/dev/null || true
sleep 1

# Use timeout to prevent hangs (systemctl stop can block indefinitely)
if ! timeout "${NX_TIMEOUT}" /etc/NX/nxserver --restart >> "$LOGFILE" 2>&1; then
    warn "nxserver --restart timed out or failed. Attempting force stop+start..."
    pkill -9 -f '/usr/NX/bin/' 2>/dev/null || true
    sleep 2
    timeout "${NX_TIMEOUT}" /etc/NX/nxserver --startup >> "$LOGFILE" 2>&1 || warn "nxserver --startup also failed"
fi

# Wait for server to be fully ready
sleep 3

# ── Step 5b: Verify server is running before proceeding ──────────────────────
NX_STATUS=$(/etc/NX/nxserver --status 2>&1) || true
echo "$NX_STATUS" >> "$LOGFILE"
echo "$NX_STATUS"

if echo "$NX_STATUS" | grep -q "Enabled service"; then
    info "NoMachine server is running."
else
    warn "NoMachine server may not be running. Password setup may fail."
    warn "Status output logged to $LOGFILE"
fi

# ── Step 6: Set NoMachine user password ──────────────────────────────────────
echo
read -rp "Enter the username to set a NoMachine password for: " NX_USER
if [[ -z "$NX_USER" ]]; then
    warn "No username entered, skipping password setup."
else
    if id "$NX_USER" &>/dev/null; then
        # Step 6a: Stop server to kill all sessions (sessions block --userdel)
        info "Stopping NoMachine server (to clear active sessions)..."
        /etc/NX/nxserver --shutdown >> "$LOGFILE" 2>&1 || true
        pkill -9 -f '/usr/NX/bin/' 2>/dev/null || true
        sleep 2

        # Step 6b: Clean stale session data that survives restarts
        info "Cleaning stale session data..."
        rm -rf /usr/NX/var/db/running/*  2>/dev/null || true
        rm -rf /usr/NX/var/db/session/*  2>/dev/null || true
        echo "── session cleanup done ──" >> "$LOGFILE"

        # Step 6c: Start server with clean state
        info "Starting NoMachine server..."
        /etc/NX/nxserver --startup >> "$LOGFILE" 2>&1
        sleep 3

        # Step 6d: Remove user from NX DB (clean slate for password DB entry)
        info "Removing $NX_USER from NX DB (if present)..."
        /usr/NX/bin/nxserver --userdel "$NX_USER" >> "$LOGFILE" 2>&1 || true
        echo "── userdel complete ──" >> "$LOGFILE"

        # Step 6e: Add existing system user to NX — prompts for NX password
        # NOTE: Do NOT use --system here. --system creates a new OS account.
        # Without --system, --useradd registers an existing Linux user and
        # prompts for an NX password when EnablePasswordDB=1.
        info "Adding $NX_USER to NoMachine (you will be prompted for an NX password)..."
        echo "── useradd start ──" >> "$LOGFILE"
        # stdout goes to terminal so interactive password prompt works
        /usr/NX/bin/nxserver --useradd "$NX_USER" 2>> "$LOGFILE"
        echo "── useradd complete (exit: $?) ──" >> "$LOGFILE"

        # Step 6f: Verify
        info "Verifying NX user DB..."
        PASSWD_CHECK=$(/usr/NX/bin/nxserver --userlist 2>&1) || true
        echo "── userlist output ──" >> "$LOGFILE"
        echo "$PASSWD_CHECK" >> "$LOGFILE"
        info "NX user list:"
        echo "$PASSWD_CHECK"
    else
        warn "User '$NX_USER' does not exist on this system. Skipping password setup."
    fi
fi

# ── Step 7: Verify ───────────────────────────────────────────────────────────
sleep 2
NX_STATUS_FINAL=$(/etc/NX/nxserver --status 2>&1) || true
echo "── final status ──" >> "$LOGFILE"
echo "$NX_STATUS_FINAL" >> "$LOGFILE"

if echo "$NX_STATUS_FINAL" | grep -q "Enabled service"; then
    info "NoMachine server is running."
else
    warn "NoMachine server may not have started correctly."
    warn "Check: /etc/NX/nxserver --status"
fi

# Dump config state for debugging
echo "── server.cfg (password-related) ──" >> "$LOGFILE"
grep -E "^(EnablePasswordDB|AcceptedAuthenticationMethods)" "$NX_CFG" >> "$LOGFILE" 2>&1

# ── Done ──────────────────────────────────────────────────────────────────────
BOX_W=64
_border_top="╔$(printf '═%.0s' $(seq 1 $BOX_W))╗"
_border_mid="╠$(printf '═%.0s' $(seq 1 $BOX_W))╣"
_border_bot="╚$(printf '═%.0s' $(seq 1 $BOX_W))╝"
_boxline() { printf '║ %-*s ║\n' "$((BOX_W - 2))" "$1"; }

echo
echo "$_border_top"
_boxline "NoMachine Remote Desktop -- Setup Complete"
echo "$_border_mid"
_boxline ""
_boxline "Connect from your Mac:"
_boxline ""
_boxline "1. Download NoMachine client:"
_boxline "   https://download.nomachine.com/download/9.3/MacOSX/"
_boxline ""
_boxline "2. Open NoMachine -> New Connection"
_boxline "   Protocol: NX"
_boxline "   Host:     ${LAN_IP}"
_boxline "   Port:     ${NX_PORT}"
_boxline ""
_boxline "3. Log in with your Ubuntu username/password"
_boxline ""
_boxline "LAN-only: Bound to ${LAN_IP}, subnet ${LAN_SUBNET}"
_boxline ""
_boxline "Full log: ${LOGFILE}"
_boxline ""
echo "$_border_bot"
