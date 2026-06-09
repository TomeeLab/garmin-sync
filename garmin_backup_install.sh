#!/bin/bash
# garmin_backup_install.sh – installation and setup of garmin_backup.py
# Run as a regular user (not root); sudo is used only where necessary.
#
# What this script does:
#  1. Creates a Python virtualenv and installs dependencies
#  2. Creates the FIT files target directory
#  3. Creates a wrapper script for cron (sets environment variables)
#  4. Adds a cron job – runs backup every 30 minutes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_PY="${SCRIPT_DIR}/garmin_backup.py"
VENV_DIR="${SCRIPT_DIR}/venv"
WRAPPER="${SCRIPT_DIR}/run_garmin_backup.sh"
FIT_DIR="${HOME}/garmin-fit"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

# ── Checks ────────────────────────────────────────────────────────────────────
info "Checking dependencies..."
command -v python3 >/dev/null || error "python3 is not installed"
command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1 || \
    { warn "pip not found, installing..."; sudo apt-get install -y python3-pip; }

[[ -f "${BACKUP_PY}" ]] || error "File ${BACKUP_PY} not found!"

# ── Garmin credentials ────────────────────────────────────────────────────────
echo
info "Enter Garmin Connect credentials (will be saved to ${WRAPPER})"
read -rp "  Garmin email: " GARMIN_EMAIL
read -rsp "  Garmin password: " GARMIN_PASSWORD
echo
[[ -z "${GARMIN_EMAIL}" || -z "${GARMIN_PASSWORD}" ]] && error "Email and password cannot be empty!"

# ── Python venv ───────────────────────────────────────────────────────────────
info "Creating Python virtualenv in ${VENV_DIR}..."
python3 -m venv "${VENV_DIR}"

info "Installing garminconnect into venv..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet garminconnect

info "garminconnect version: $("${VENV_DIR}/bin/pip" show garminconnect | grep Version)"

# ── FIT directory ─────────────────────────────────────────────────────────────
info "Creating FIT files directory: ${FIT_DIR}"
mkdir -p "${FIT_DIR}"

# ── Wrapper script ────────────────────────────────────────────────────────────
info "Creating wrapper script ${WRAPPER}..."
cat > "${WRAPPER}" << WEOF
#!/bin/bash
# Wrapper for cron – sets environment variables and runs the Garmin FIT backup.
# Edit this file to change settings, not garmin_backup.py.

export GARMIN_EMAIL="${GARMIN_EMAIL}"
export GARMIN_PASSWORD="${GARMIN_PASSWORD}"
export GARMIN_FIT_DIR="${FIT_DIR}"
# LOOKBACK is only used when .garmin_last_sync does not exist (bulk/first run).
# 3650 = download everything up to ~10 years back.
export GARMIN_LOOKBACK="3650"

# Log output with rotation at 512 kB
LOG_FILE="${SCRIPT_DIR}/garmin_backup.log"
MAX_LOG_SIZE=524288

rotate_log() {
    if [[ -f "\${LOG_FILE}" && \$(stat -c%s "\${LOG_FILE}") -gt \${MAX_LOG_SIZE} ]]; then
        mv "\${LOG_FILE}" "\${LOG_FILE}.1"
    fi
}

rotate_log
"${VENV_DIR}/bin/python3" "${BACKUP_PY}" >> "\${LOG_FILE}" 2>&1
WEOF

# 700 = owner can read/write/execute, no access for others (password is stored inside)
chmod 700 "${WRAPPER}"
info "Wrapper created: chmod 700"

# ── Cron job ──────────────────────────────────────────────────────────────────
CRON_LINE="*/30 * * * * ${WRAPPER}"

info "Adding cron job (every 30 minutes)..."
if crontab -l 2>/dev/null | grep -qF "${BACKUP_PY}"; then
    warn "Cron job for garmin_backup.py already exists, skipping."
else
    (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
    info "Cron job added: ${CRON_LINE}"
fi

# ── First run test ────────────────────────────────────────────────────────────
echo
info "Running first test (may take a while for bulk download)..."
bash "${WRAPPER}"
echo
info "Log output (last 30 lines):"
tail -30 "${SCRIPT_DIR}/garmin_backup.log" 2>/dev/null || warn "Log file does not exist yet."

# ── Summary ───────────────────────────────────────────────────────────────────
echo
info "═══════════════════════════════════════════════════════"
info "Installation complete!"
info ""
info "  FIT files:  ${FIT_DIR}/YYYY/MM/"
info "  Log:        ${SCRIPT_DIR}/garmin_backup.log"
info "  Tokens:     ${SCRIPT_DIR}/.garmin_tokens"
info "  Cron:       every 30 minutes"
info ""
info "  Manual run:   bash ${WRAPPER}"
info "  Follow log:   tail -f ${SCRIPT_DIR}/garmin_backup.log"
info "═══════════════════════════════════════════════════════"
