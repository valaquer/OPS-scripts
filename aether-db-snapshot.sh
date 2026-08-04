#!/bin/bash
# Hourly Aether DB snapshot with local rotation.
# Daily encrypted backup to Google Drive (14-day rolling window).
# Weekly backup of large reconstructible assets.
# Launchd runs this every hour.

set -euo pipefail

AETHER_DB="/Users/deepak-macmini/honeybloom/library/aether/aether.db"
SNAPSHOT_DIR="/Users/deepak-macmini/honeybloom/library/aether/snapshots"
BACKUP_ROOT="/Users/deepak-macmini/honeybloom/library/aether/backups"
KEY_FILE="/Users/deepak-macmini/.secrets/aether-backup-key"
LOG="/var/tmp/aether-db-snapshot.log"
HOMEDIR="/Users/deepak-macmini/honeybloom"

mkdir -p "$SNAPSHOT_DIR"
mkdir -p "$BACKUP_ROOT"/{aether-db,houston-db,manhattan-db,stuttgart-db,felix-safe,bavaria-assets,watermark-infra,sierra-venv}

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TODAY=$(date +%Y%m%d)
DAY_OF_WEEK=$(date +%u)

# --- Hourly: Aether DB local snapshot ---

HOURLY_FILE="$SNAPSHOT_DIR/aether-$TIMESTAMP.sql"
/usr/bin/sqlite3 "$AETHER_DB" ".dump" > "$HOURLY_FILE" 2>>"$LOG"

FILE_SIZE=$(stat -f%z "$HOURLY_FILE" 2>/dev/null || echo "0")
if [ "$FILE_SIZE" -lt 100 ]; then
    echo "$(date): FAILED -- snapshot too small ($FILE_SIZE bytes), skipping" >> "$LOG"
    rm -f "$HOURLY_FILE"
    exit 1
fi

echo "$(date): hourly snapshot ($FILE_SIZE bytes)" >> "$LOG"

ls -t "$SNAPSHOT_DIR"/aether-*.sql 2>/dev/null | tail -n +7 | xargs rm -f 2>/dev/null

# --- Daily backup to Google Drive (once per calendar day) ---

if ! ls "$BACKUP_ROOT"/aether-db/aether-"$TODAY"-*.sql.gz.enc 1>/dev/null 2>&1; then
    if [ ! -f "$KEY_FILE" ]; then
        echo "$(date): FAILED -- encryption key not found ($KEY_FILE)" >> "$LOG"
        exit 1
    fi
    ENC_KEY=$(cat "$KEY_FILE")

    encrypt_file() {
        local src="$1" dst="$2"
        gzip -c "$src" | openssl enc -aes-256-cbc -salt -pbkdf2 -pass "pass:$ENC_KEY" -out "$dst" 2>>"$LOG"
    }

    encrypt_dir() {
        local src="$1" dst="$2"
        tar -cf - -C "$(dirname "$src")" "$(basename "$src")" 2>/dev/null | \
            gzip | openssl enc -aes-256-cbc -salt -pbkdf2 -pass "pass:$ENC_KEY" -out "$dst" 2>>"$LOG"
    }

    # Aether DB
    encrypt_file "$HOURLY_FILE" "$BACKUP_ROOT/aether-db/aether-$TIMESTAMP.sql.gz.enc" && \
        echo "$(date): Aether DB backed up" >> "$LOG"
    find "$BACKUP_ROOT/aether-db" -name "*.gz.enc" -mtime +14 -delete 2>/dev/null

    # Houston DB
    if [ -f "$HOMEDIR/library/houston-app/houston.db" ]; then
        encrypt_file "$HOMEDIR/library/houston-app/houston.db" "$BACKUP_ROOT/houston-db/houston-$TIMESTAMP.db.gz.enc" && \
            echo "$(date): Houston DB backed up" >> "$LOG"
        find "$BACKUP_ROOT/houston-db" -name "*.gz.enc" -mtime +14 -delete 2>/dev/null
    fi

    # Manhattan DB (sqlite3 .dump -- raw file copy fails with WAL mode)
    if [ -f "$HOMEDIR/library/manhattan-app/manhattan.db" ]; then
        MANHATTAN_DUMP=$(mktemp)
        if /usr/bin/sqlite3 "$HOMEDIR/library/manhattan-app/manhattan.db" ".dump" > "$MANHATTAN_DUMP" 2>>"$LOG"; then
            DUMP_SIZE=$(stat -f%z "$MANHATTAN_DUMP" 2>/dev/null || echo "0")
            if [ "$DUMP_SIZE" -gt 100 ]; then
                encrypt_file "$MANHATTAN_DUMP" "$BACKUP_ROOT/manhattan-db/manhattan-$TIMESTAMP.sql.gz.enc" && \
                    echo "$(date): Manhattan DB backed up ($DUMP_SIZE bytes dump)" >> "$LOG"
            else
                echo "$(date): Manhattan DB dump too small ($DUMP_SIZE bytes), skipping" >> "$LOG"
            fi
        else
            echo "$(date): Manhattan DB dump failed" >> "$LOG"
        fi
        rm -f "$MANHATTAN_DUMP"
        find "$BACKUP_ROOT/manhattan-db" -name "*.gz.enc" -mtime +14 -delete 2>/dev/null
    fi

    # Stuttgart DB (when created)
    if [ -f "$HOMEDIR/library/stuttgart-app/stuttgart.db" ]; then
        encrypt_file "$HOMEDIR/library/stuttgart-app/stuttgart.db" "$BACKUP_ROOT/stuttgart-db/stuttgart-$TIMESTAMP.db.gz.enc" && \
            echo "$(date): Stuttgart DB backed up" >> "$LOG"
        find "$BACKUP_ROOT/stuttgart-db" -name "*.gz.enc" -mtime +14 -delete 2>/dev/null
    fi

    # Felix vault.db (already SQLCipher encrypted)
    if [ -f "$HOMEDIR/felix/vault.db" ]; then
        cp "$HOMEDIR/felix/vault.db" "$BACKUP_ROOT/felix-safe/" 2>>"$LOG" && \
            echo "$(date): Felix vault.db backed up" >> "$LOG"
    fi

    # Felix safe (already AES-256 encrypted)
    if [ -f "$HOMEDIR/felix/safe.dmg.sparseimage" ]; then
        cp "$HOMEDIR/felix/safe.dmg.sparseimage" "$BACKUP_ROOT/felix-safe/" 2>>"$LOG" && \
            echo "$(date): Felix safe backed up" >> "$LOG"
    fi

    # Bavaria assets (daily, ~320MB)
    if [ -d "$HOMEDIR/library/bavaria" ]; then
        encrypt_dir "$HOMEDIR/library/bavaria" "$BACKUP_ROOT/bavaria-assets/bavaria-$TIMESTAMP.tar.gz.enc" && \
            echo "$(date): Bavaria assets backed up" >> "$LOG"
        find "$BACKUP_ROOT/bavaria-assets" -name "*.tar.gz.enc" -mtime +14 -delete 2>/dev/null
    fi

    echo "$(date): daily backup done" >> "$LOG"
fi

# --- Weekly backup of large assets (Sunday = day 7) ---

if [ "$DAY_OF_WEEK" = "7" ]; then
    if [ ! -f "$KEY_FILE" ]; then exit 0; fi
    ENC_KEY=${ENC_KEY:-$(cat "$KEY_FILE")}

    # Watermark infra (weekly, ~3.5GB, keep 2 rolling copies)
    if [ -d "$HOMEDIR/library/watermark" ]; then
        if ! ls "$BACKUP_ROOT"/watermark-infra/watermark-"$TODAY"-*.tar.gz.enc 1>/dev/null 2>&1; then
            encrypt_dir "$HOMEDIR/library/watermark" "$BACKUP_ROOT/watermark-infra/watermark-$TIMESTAMP.tar.gz.enc" && \
                echo "$(date): Watermark infra backed up (weekly)" >> "$LOG"
            ls -t "$BACKUP_ROOT"/watermark-infra/watermark-*.tar.gz.enc 2>/dev/null | tail -n +3 | xargs rm -f 2>/dev/null
        fi
    fi

    # Sierra venv (weekly, ~718MB, keep 2 rolling copies)
    if [ -d "$HOMEDIR/sierra/.venv" ]; then
        if ! ls "$BACKUP_ROOT"/sierra-venv/sierra-venv-"$TODAY"-*.tar.gz.enc 1>/dev/null 2>&1; then
            encrypt_dir "$HOMEDIR/sierra/.venv" "$BACKUP_ROOT/sierra-venv/sierra-venv-$TIMESTAMP.tar.gz.enc" && \
                echo "$(date): Sierra venv backed up (weekly)" >> "$LOG"
            ls -t "$BACKUP_ROOT"/sierra-venv/sierra-venv-*.tar.gz.enc 2>/dev/null | tail -n +3 | xargs rm -f 2>/dev/null
        fi
    fi
fi
