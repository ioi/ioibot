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
#   - Generates a systemd user service at ~/.config/systemd/user/ioibot.service
#
# TO START THE BOT:
#   systemctl --user start ioibot.service
#
# TO VIEW LOGS:
#   journalctl --user -u ioibot.service -f
#
# NOTES:
#   - You must edit 'etc/sample.config.yaml' and save it as 'data/config.yaml'
#     before starting the bot.
#   - The systemd service file will be created at:
#     ~/.config/systemd/user/ioibot.service

set -euo pipefail

# Variable names
SERVICE_NAME="ioibot.service"
SYSTEMD_DIR="$HOME/.config/systemd/user"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$PROJECT_DIR/data"
VENV="$PROJECT_DIR/venv"
BOT="$VENV/bin/ioibot"
CONFIG="$DATA_DIR/config.yaml"
TEMPLATE="$PROJECT_DIR/etc/sample.config.yaml"
INIT_SQL="$PROJECT_DIR/ioibot/init.sql"

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

# Activate the virtual environment
source "$VENV/bin/activate"

# Install Python packages
pip install -e .

if [ ! -f "$CONFIG" ]; then
  if [ -f "$TEMPLATE" ]; then
    echo "config.yaml not found."
    echo "Please edit the sample.config.yaml file and save it as config.yaml."
    exit 1
  else
    echo "Error: Neither $CONFIG nor $TEMPLATE found"
    exit 1
  fi
fi

# Initialize database schema if init.sql exists
if [ -f "$INIT_SQL" ]; then
  echo "Initializing database schema from $INIT_SQL"
  psql -f "$INIT_SQL"
else
  echo "$INIT_SQL not found. Skipping database initialization."
  echo "Please initialize your database manually."
fi

# Create data store
mkdir -p "$DATA_DIR/store"

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
WorkingDirectory=$DATA_DIR
ExecStart=$BOT config.yaml
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

# Reload systemd so it sees the new service
systemctl --user daemon-reload
