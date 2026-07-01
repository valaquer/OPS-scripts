#!/bin/bash
# Provision a new Workbench-family app from the template.
# Usage: provision-workbench-app.sh <app-name> <port> <lucide-icon-name>
# Example: provision-workbench-app.sh cernere 51760 MessageSquare

set -euo pipefail

APP_NAME="${1:-}"
PORT="${2:-}"
ICON="${3:-}"

if [[ -z "$APP_NAME" || -z "$PORT" || -z "$ICON" ]]; then
	echo "Usage: $0 <app-name> <port> <lucide-icon-name>"
	echo "Example: $0 cernere 51760 MessageSquare"
	exit 1
fi

LIBRARY="/Users/deepak-macmini/honeybloom/library"
TEMPLATE="$LIBRARY/workbench-template"
TARGET="$LIBRARY/${APP_NAME}-app"
REGISTRY="$LIBRARY/aether/workbench-apps.json"
APP_TITLE="$(echo "$APP_NAME" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')"

if [[ -d "$TARGET" ]]; then
	echo "Error: $TARGET already exists."
	exit 1
fi

echo "==> Copying template to $TARGET"
cp -R "$TEMPLATE" "$TARGET"

echo "==> Replacing placeholders"
sed -i '' "s/__APP_NAME__/$APP_NAME/g" "$TARGET/package.json"
sed -i '' "s/__PORT__/$PORT/g" "$TARGET/vite.config.ts"
sed -i '' "s/__APP_TITLE__/$APP_TITLE/g" "$TARGET/src/routes/+page.svelte"
sed -i '' "s/__APP_NAME__/$APP_NAME/g" "$TARGET/src/routes/+page.svelte"

echo "==> Creating symlinks"
ln -sf "$LIBRARY/styles/foundation.css" "$TARGET/src/lib/foundation.css"
ln -sf "$LIBRARY/styles/sidebar.css" "$TARGET/src/lib/sidebar.css"

echo "==> Installing dependencies"
cd "$TARGET"
npm install --silent

echo "==> Initializing git repo"
git init -q
git add -A
git commit -q -m "Initial commit from workbench template

Co-authored-by: Chica <noreply@anthropic.com>"

echo "==> Creating GitHub repo"
gh repo create "valaquer/$APP_NAME" --public --source=. --push

echo "==> Registering in workbench-apps.json"
# Remove trailing ] and add new entry
cd "$LIBRARY"
python3 -c "
import json
with open('$REGISTRY') as f:
    apps = json.load(f)
apps.append({'name': '$APP_TITLE', 'port': $PORT, 'icon': '$ICON'})
apps.sort(key=lambda x: x['name'])
with open('$REGISTRY', 'w') as f:
    json.dump(apps, f, indent='\t')
    f.write('\n')
"

echo ""
echo "=== Done ==="
echo "App created at: $TARGET"
echo "GitHub repo: https://github.com/valaquer/$APP_NAME"
echo "Port: $PORT"
echo "Dev server: cd $TARGET && npm run dev"
echo ""
echo "The app is registered in workbench-apps.json."
echo "Aether's dropdown will pick it up on next page load."
