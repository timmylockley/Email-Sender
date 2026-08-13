#!/bin/bash
set -e

REPO_URL="https://github.com/timmylockley/Email-Sender.git"
TEMP_DIR="/tmp/email-sender-repo"

echo "==> Cloning repository..."
git clone "$REPO_URL" "$TEMP_DIR"

echo "==> Installing files..."
sudo cp "$TEMP_DIR/email_sender.py" /usr/bin/email-sender
sudo chmod +x /usr/bin/email-sender

if [ -f "$TEMP_DIR/myicon.png" ]; then
    sudo cp "$TEMP_DIR/myicon.png" /usr/share/pixmaps/email-sender.png
fi

sudo tee /usr/share/applications/email-sender.desktop > /dev/null <<EOF
[Desktop Entry]
Version=1.0.0
Type=Application
Name=Email Sender
Comment=A Simple Python application which allows the user to send emails and create rss feeds to emails.
Exec=/usr/bin/email-sender
Icon=/usr/share/pixmaps/email-sender.png
Terminal=false
Categories=Utility;Development;
EOF

rm -rf "$TEMP_DIR"
echo "==> Installation complete!"
