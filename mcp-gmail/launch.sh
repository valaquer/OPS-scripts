#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec uv run "$DIR/server.py"
