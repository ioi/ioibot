#!/usr/bin/env bash
# IOIBot Setup Script
#
# This script installs dependencies, creates a Python virtual environment,
# copies the default config file if missing, and generates a systemd user
# service to run the bot.
#
# USAGE:
#   ./install-and-setup.sh
#
# WHAT IT DOES:
#   - Creates a Python virtual environment in ./env
#   - Installs project dependencies with pip
#   - Verifies that data/config.yaml exists
#   - Generates a systemd user service at ~/.config/systemd/user/ioibot2025.service
#
# TO START THE BOT:
#   systemctl --user start ioibot2025.service
#
# TO VIEW LOGS:
#   journalctl --user -u ioibot2025.service -f
#
# NOTES:
#   - You must edit 'data/sample.config.yaml' and save it as 'data/config.yaml'
#     before starting the bot.
#   - You must set the environment variables VOTING_USERNAME and VOTING_PASSWORD
#     in the systemd service file:
#     ~/.config/systemd/user/ioibot2025.service
#     These are required for the bot to work properly.

set -euo pipefail

# Variable names
SERVICE_NAME="ioibot2025.service"
SYSTEMD_DIR="$HOME/.config/systemd/user"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$PROJECT_DIR/data"
VENV="$PROJECT_DIR/env"
BOT="$VENV/bin/ioibot"
CONFIG="$DATA_DIR/config.yaml"
TEMPLATE="$DATA_DIR/sample.config.yaml"

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

# Activate the virtual environment
source "$VENV/bin/activate"

# Install Python packages
pip install --upgrade pip
pip install flit
pip install -e ".[postgres]"
pip install -e .

if [ ! -f "$CONFIG" ]; then
  if [ -f "$TEMPLATE" ]; then
    echo "config.yaml not found."
    echo "Please edit the sample.config.yaml file and save it as config.yaml."
    exit 1
  else
    echo "Error: No config.yaml or sample.config.yaml found in $DATA_DIR"
    exit 1
  fi
fi


# Make sure the bot file is executable
if [ ! -x "$BOT" ]; then
  chmod +x "$BOT"
fi

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Create the systemd service file
echo "Creating systemd service file..."
cat > "$SYSTEMD_DIR/$SERVICE_NAME" <<EOF
[Unit]
Description=A Matrix bot that does amazing things!
After=network.target

[Service]
Type=simple
Environment=VOTING_USERNAME=
Environment=VOTING_PASSWORD=
WorkingDirectory=$DATA_DIR
ExecStart=$BOT config.yaml
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

# Reload systemd so it sees the new service
systemctl --user daemon-reexec || true
systemctl --user daemon-reload

echo ""
echo "Please update \"$SYSTEMD_DIR/$SERVICE_NAME\" with your custom configurations if needed."
echo ""
echo "To start the bot run:"
echo "   systemctl --user start $SERVICE_NAME"
echo ""
echo "To show logs, run:"
echo "   journalctl --user -u $SERVICE_NAME -f"
echo ""

