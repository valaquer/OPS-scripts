#!/bin/bash
# safe.sh — encrypted disk image mount/unmount for teammate file security
# Usage: safe.sh mount|unmount|create|resize <teammate> [size]

set -euo pipefail

TEAMMATE="${2:-}"
if [[ -z "$TEAMMATE" ]]; then
    echo "Usage: safe.sh <mount|unmount|create> <teammate>"
    exit 1
fi

HOME_DIR="/Users/deepak-macmini/honeybloom/${TEAMMATE}"
DMG_PATH="${HOME_DIR}/safe.dmg"
MOUNT_POINT="${HOME_DIR}/safe"
KEYCHAIN_KEY="safe-${TEAMMATE}"

case "${1:-}" in
    create)
        if [[ -f "$DMG_PATH" ]]; then
            echo "Error: ${DMG_PATH} already exists."
            exit 1
        fi

        # Get password from Keychain
        PASSWORD=$(security find-generic-password -s "$KEYCHAIN_KEY" -w 2>/dev/null) || {
            echo "Error: No Keychain entry found for '${KEYCHAIN_KEY}'."
            echo "Add one first: security add-generic-password -s '${KEYCHAIN_KEY}' -a '${TEAMMATE}' -w '<password>'"
            exit 1
        }

        echo "Creating 2 GB encrypted sparse image at ${DMG_PATH}..."
        echo -n "$PASSWORD" | hdiutil create \
            -size 2g \
            -fs APFS \
            -encryption AES-256 \
            -type SPARSE \
            -volname "safe-${TEAMMATE}" \
            -stdinpass \
            "$DMG_PATH"

        echo "Created. Run 'safe.sh mount ${TEAMMATE}' to mount."
        ;;

    mount)
        if [[ ! -f "$DMG_PATH" ]] && [[ ! -f "${DMG_PATH}.sparseimage" ]]; then
            echo "Error: No safe found at ${DMG_PATH}"
            exit 1
        fi

        # Check if already mounted
        if mount | grep -q "${MOUNT_POINT}"; then
            echo "Already mounted."
            exit 0
        fi

        PASSWORD=$(security find-generic-password -s "$KEYCHAIN_KEY" -w 2>/dev/null) || {
            echo "Error: No Keychain entry found for '${KEYCHAIN_KEY}'."
            exit 1
        }

        mkdir -p "$MOUNT_POINT"

        # hdiutil creates .sparseimage extension
        DMG_FILE="$DMG_PATH"
        [[ -f "${DMG_PATH}.sparseimage" ]] && DMG_FILE="${DMG_PATH}.sparseimage"

        echo -n "$PASSWORD" | hdiutil attach \
            -stdinpass \
            -mountpoint "$MOUNT_POINT" \
            -nobrowse \
            "$DMG_FILE"

        echo "Mounted at ${MOUNT_POINT}"
        ;;

    unmount)
        # Safe to call even if not mounted
        if ! mount | grep -q "${MOUNT_POINT}"; then
            echo "Not mounted."
            exit 0
        fi

        hdiutil detach "$MOUNT_POINT" -quiet
        echo "Unmounted."
        ;;

    resize)
        SIZE="${3:-}"
        if [[ -z "$SIZE" ]]; then
            echo "Usage: safe.sh resize <teammate> <size>"
            echo "Example: safe.sh resize felix 4g"
            exit 1
        fi

        # Must be unmounted to resize
        if mount | grep -q "${MOUNT_POINT}"; then
            echo "Unmount first: safe.sh unmount ${TEAMMATE}"
            exit 1
        fi

        DMG_FILE="$DMG_PATH"
        [[ -f "${DMG_PATH}.sparseimage" ]] && DMG_FILE="${DMG_PATH}.sparseimage"

        hdiutil resize -size "$SIZE" "$DMG_FILE"
        echo "Resized to ${SIZE}."
        ;;

    *)
        echo "Usage: safe.sh <mount|unmount|create|resize> <teammate> [size]"
        exit 1
        ;;
esac
