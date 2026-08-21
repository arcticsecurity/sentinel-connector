#!/bin/sh
# Keep the release version and the release tags in the documentation in step.
#
# Usage:
#   ./bump_version.sh 1.2.3     Set the version in VERSION and in the docs.
#   ./bump_version.sh --check   Verify the docs match VERSION. Used by CI.
#   ./bump_version.sh --files   List the files that carry a version number.

set -eu

cd "$(dirname "$0")"

# Documentation files that refer to the release tag. Version numbers in other
# files, such as the pinned action versions in the CI workflow, are left alone.
DOC_FILES="README.md
Data Connectors/ArcticSecurityEwsConnector/ArcticSecurityEwsConnector_API_FunctionApp.json"

# A release tag as it appears in the documentation, for example v1.2.3.
TAG='v[0-9]+\.[0-9]+\.[0-9]+'

die() {
    echo "Error: $*" >&2
    exit 1
}

usage() {
    echo "Usage: $0 1.2.3 | --check | --files" >&2
    exit 2
}

# VERSION is a shell assignment, for example VERSION=1.2.3.
current_version() {
    # shellcheck source=/dev/null
    . ./VERSION
    echo "$VERSION"
}

list_files() {
    echo VERSION
    echo "$DOC_FILES"
}

check_version() {
    expected="v$(current_version)"
    result=0

    for file in $DOC_FILES; do
        found="$(grep -Eo "$TAG" "$file" | sort -u | tr '\n' ' ')"
        if [ "$found" != "$expected " ]; then
            echo "$file: expected $expected, found ${found:-nothing}" >&2
            result=1
        fi
    done

    if [ "$result" -eq 0 ]; then
        echo "Documentation refers to $expected"
    else
        echo "Run ./bump_version.sh $(current_version) to update the docs." >&2
    fi
    return "$result"
}

set_version() {
    echo "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' ||
        die "version must be given as MAJOR.MINOR.PATCH, got: $1"

    printf 'VERSION=%s\n' "$1" > VERSION
    echo "VERSION: $1"

    for file in $DOC_FILES; do
        # printf, not echo, as the files contain backslash sequences.
        updated="$(sed -E "s/$TAG/v$1/g" "$file")"
        printf '%s\n' "$updated" > "$file"
        echo "$file: $(grep -Eo "$TAG" "$file" | sort -u | tr '\n' ' ')"
    done
}

# Iterate over file names one line at a time, as they contain spaces.
IFS='
'

[ $# -eq 1 ] || usage

case "$1" in
    --check) check_version ;;
    --files) list_files ;;
    -*)      usage ;;
    *)       set_version "$1" ;;
esac
