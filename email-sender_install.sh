#!/bin/bash

# Exit immediately if any command fails
set -e

REPO_URL="https://github.com/timmylockley/Email-Sender.git"
TEMP_DIR="/tmp/email-sender-repo"

echo "==> Cloning repository from $REPO_URL..."
git clone "$REPO_URL" "$TEMP_DIR"

echo "==> Creating system directories..."
sudo mkdir -p /usr/bin
sudo mkdir -p /usr/share/pixmaps
sudo mkdir -p /usr/share/applications

echo "==> Installing Python executable..."
# Ensure your main script has a proper shebang line (# /usr/bin/env python3) at the top
sudo cp "$TEMP_DIR/email_sender.py" /usr/bin/email-sender
sudo chmod +x /usr/bin/email-sender

echo "==> Installing application icon..."
if [ -f "$TEMP_DIR/myicon.png" ]; then
    sudo cp "$TEMP_DIR/myicon.png" /usr/share/pixmaps/mypythonapp.png
else
    echo "Warning: myicon.png not found in repository. Skipping icon installation."
fi

echo "==> Installing desktop menu entry..."
sudo tee /usr/share/applications/mypythonapp.desktop > /dev/null <<EOF
[Desktop Entry]
Version=1.0.o
Type=Application
Name=Email Sender
Comment=A Simple Python application which allows the user to send emails and create rss feeds to emails.
Exec=/usr/bin/email-sender
Icon=/usr/share/pixmaps/mypythonapp.png
Terminal=false
Categories=Utility;Development;
EOF

echo "==> Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo "==> Installation complete! You can now search for 'Email Sender' in your application menu."
