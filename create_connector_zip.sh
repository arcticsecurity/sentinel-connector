#!/bin/sh
set -eu

# Usage: ./create_connector_zip.sh [output-zip-name.zip]
# Default name: ArcticSecurityEwsConnector.zip

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$ROOT_DIR/Data Connectors/ArcticSecurityEwsConnector"
ZIP_NAME="${1:-ArcticSecurityEwsConnector.zip}"
PYTHON_VER="$(cat "${ROOT_DIR}/.python-version")"

if ! command -v zip >/dev/null 2>&1; then
  echo "Error: 'zip' is not installed." >&2
  exit 1
fi

# Build dependencies with Python 3.12 to match Azure Functions runtime (python|3.12).
# Python 3.12 is the last Python version supported for Linux Consumption plan apps. 
# Newer Python versions aren't added to Linux Consumption.
PYTHON_BIN="${PYTHON_BIN:-python${PYTHON_VER}}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: '$PYTHON_BIN' not found. Install Python ${PYTHON_VER} or set PYTHON_BIN." >&2
  exit 1
fi

py_ver="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$py_ver" != "${PYTHON_VER}" ]; then
  echo "Error: packaging must use Python ${PYTHON_VER} for Azure Functions runtime, got $py_ver via $PYTHON_BIN." >&2
  exit 1
fi

# Ensure pip exists for the selected interpreter.
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "pip missing for $PYTHON_BIN, attempting bootstrap via ensurepip..."
  "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || {
    echo "Error: could not bootstrap pip for $PYTHON_BIN. Install python${PYTHON_VER}-venv or equivalent." >&2
    exit 1
  }
fi

# Ensure required files exist
for f in host.json requirements.txt; do
  if [ ! -f "$SRC_DIR/$f" ]; then
    echo "Error: Missing $f in: $SRC_DIR" >&2
    exit 1
  fi
done

if [ ! -f "$ROOT_DIR/LICENSE" ]; then
  echo "Error: Missing LICENSE in: $ROOT_DIR" >&2
  exit 1
fi

# Ensure connector folder and files exist
if [ ! -d "$SRC_DIR/ArcticSecurityEwsConnector" ]; then
  echo "Error: Missing folder: $SRC_DIR/ArcticSecurityEwsConnector" >&2
  exit 1
fi
for f in __init__.py data_collector.py ews.py function.json state_manager.py; do
  if [ ! -f "$SRC_DIR/ArcticSecurityEwsConnector/$f" ]; then
    echo "Error: Missing $f in: $SRC_DIR/ArcticSecurityEwsConnector" >&2
    exit 1
  fi
done

# Ensure no unexpected files in connector folder
file_count=$(find "$SRC_DIR/ArcticSecurityEwsConnector" -maxdepth 1 -type f ! -name '.*' | wc -l | tr -d ' ')
if [ "$file_count" -ne 5 ]; then
  echo "Error: Unexpected number of files in: $SRC_DIR/ArcticSecurityEwsConnector" >&2
  exit 1
fi
for path in "$SRC_DIR/ArcticSecurityEwsConnector"/*; do
  [ -f "$path" ] || continue
  base=$(basename "$path")
  case "$base" in
    __init__.py|data_collector.py|ews.py|function.json|state_manager.py) ;;
    *)
      echo "Error: Unexpected file '$base' in: $SRC_DIR/ArcticSecurityEwsConnector" >&2
      exit 1
      ;;
  esac
done

STAGE_DIR="$(mktemp -d "$ROOT_DIR/.zipstage.XXXXXX")"
cleanup() { rm -rf "$STAGE_DIR"; }
trap 'cleanup' EXIT

cp "$SRC_DIR/host.json" "$STAGE_DIR/"
cp "$SRC_DIR/requirements.txt" "$STAGE_DIR/"
cp "$ROOT_DIR/LICENSE" "$STAGE_DIR/"
cp -R "$SRC_DIR/ArcticSecurityEwsConnector" "$STAGE_DIR/"

# Vendor Python deps into .python_packages/lib/site-packages same level as host.json
SITE_PACKAGES="$STAGE_DIR/.python_packages/lib/site-packages"
mkdir -p "$SITE_PACKAGES"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install \
  --upgrade \
  --only-binary=:all: \
  --platform manylinux_2_28_x86_64 \
  --implementation cp \
  --python-version "${PYTHON_VER}" \
  --abi cp312 \
  --no-compile \
  -r "$STAGE_DIR/requirements.txt" \
  -t "$SITE_PACKAGES"

# Sanity check
[ -d "$SITE_PACKAGES/azure/storage/fileshare" ] || {
  echo "Error: azure.storage.fileshare not found in packaged deps." >&2
  exit 1
}

TARGET_DIR="$SRC_DIR"
mkdir -p "$TARGET_DIR"
OUT_ZIP="$TARGET_DIR/$ZIP_NAME"
rm -f "$OUT_ZIP"
(
  cd "$STAGE_DIR"
  zip -r "$OUT_ZIP" . >/dev/null
)

echo "Created: $OUT_ZIP"
