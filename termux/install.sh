#!/data/data/com.termux/files/usr/bin/bash
# One-time setup for Termux. Run from the project folder:  bash termux/install.sh
set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

command -v python >/dev/null 2>&1 || pkg install -y python

# `musician-admin` command
mkdir -p "$HOME/bin"
cat > "$HOME/bin/musician-admin" <<SH
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" && exec python musician_admin.py "\$@"
SH
chmod +x "$HOME/bin/musician-admin"
grep -q 'HOME/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"

# Home-screen shortcut for the Termux:Widget add-on (optional)
mkdir -p "$HOME/.shortcuts"
cp "$HOME/bin/musician-admin" "$HOME/.shortcuts/Indie Admin"
chmod +x "$HOME/.shortcuts/Indie Admin"

echo
echo "Installed. Start the app any time with:  musician-admin"
echo "(open a new Termux session first, or run: source ~/.bashrc)"
echo "With Termux:Widget installed, add the 'Indie Admin' widget to your home screen."
