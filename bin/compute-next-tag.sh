#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Prints the tag that the currently checked out commit should be released as,
# or nothing at all if it does not warrant a release.
#
# Usage: bin/compute-next-tag.sh
#
# Tags look like `v<version>-<release>`, which is what this repository has always
# published (v2023.12.15-0 ... v2023.12.15-9).
#
# The Excalidraw collaboration server is one of the few pieces of software in
# this fleet with no versions at all: its git repository carries no tags and no
# releases, `excalidraw/excalidraw-room` on Docker Hub carries a single usable
# tag - `latest`, pushed in December 2023 - beside a set of `sha-*` ones, and the
# image has no version label either. There is nothing to read a version out of,
# which is why `excalidraw_room_version` says `latest` and why the version
# component of the tags here is a date somebody picked by hand. The sibling
# `ansible-role-excalidraw` is in exactly the same situation and does the same.
#
# So:
#
# - while `excalidraw_room_version` is `latest`, the version component is
#   inherited from the newest tag that already exists, and only the release
#   counter moves
# - should the collaboration server ever start publishing versions and
#   `excalidraw_room_version` name one, that version is used instead, and its
#   counter starts at 0
#
# Either way the answer comes from defaults/main.yml and the existing tags rather
# than from the commit message of whatever pull request got merged. That makes it
# independent of the order in which pull requests land, and lets any change to
# the role - a bugfix, a feature, a dependency bump - release itself without a
# human tagging it. The workflow this replaced looked for a `renovate[bot]`
# commit whose subject mentioned "docker tag to"; because Renovate has never had
# a version here to bump, it had never once produced a tag.

set -euo pipefail

repository_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repository_path"

defaults_path='defaults/main.yml'

# Paths that shape the behavior of the role for its consumers. A commit touching
# only other paths (a README fix, CI configuration, Molecule tests) does not
# change what a playbook run does, and releasing it would only create churn in
# the repositories that consume this role.
role_defining_paths=(
	'defaults'
	'meta'
	'tasks'
	'templates'
)

# Anchored on `excalidraw_room_version:` so that none of the variables which
# merely start with it and none of the ones derived from it - such as
# `excalidraw_room_container_image_tag`, or the
# `excalidraw_room_container_image_self_build_base_image_tag` that Renovate
# actually bumps here - can be mistaken for it.
version="$(sed -nE 's|^excalidraw_room_version:[[:space:]]*"?([^"[:space:]]+)"?.*$|\1|p' "$defaults_path" | head -n1)"

if [ -z "$version" ]; then
	echo >&2 "Could not determine the Excalidraw collaboration server version from $defaults_path"
	exit 1
fi

# Every tag this repository has ever published, newest last. The pattern is
# strict on purpose: only `v<numbers separated by dots>-<number>` counts, so a
# stray or hand-made tag cannot decide which series the next release belongs to.
released_tags="$(git tag --list 'v*' | grep -E '^v[0-9]+(\.[0-9]+)*-[0-9]+$' | sort -V || true)"

if [ "$version" = 'latest' ]; then
	# `latest` is a pointer, not a version. Stay in the series that is already
	# being published and move the release counter.
	newest_tag="$(echo "$released_tags" | tail -n1)"

	if [ -z "$newest_tag" ]; then
		echo >&2 "excalidraw_room_version is 'latest' and there is no previous tag to continue from"
		exit 1
	fi

	tag_prefix="${newest_tag%-*}-"
else
	# The collaboration server would carry its version without a leading `v` (the
	# `v` lives in the tags), but tolerate one so that a future change of
	# convention does not produce a doubled prefix.
	tag_prefix="v${version#v}-"
fi

# Of all releases in this series, the highest release number. Sorted numerically,
# so that -10 is recognized as newer than -9. The dots are escaped because the
# prefix is about to be used as a regular expression.
tag_prefix_pattern="${tag_prefix//./\\.}"
last_release="$(echo "$released_tags" | sed -ne "s|^${tag_prefix_pattern}||p" | grep -E '^[0-9]+$' | sort -n | tail -n1 || true)"

if [ -z "$last_release" ]; then
	echo >&2 "Version ${tag_prefix%-} has never been released"
	echo "${tag_prefix}0"
	exit 0
fi

previous_tag="${tag_prefix}${last_release}"

if git diff --quiet "$previous_tag" HEAD -- "${role_defining_paths[@]}"; then
	echo >&2 "Nothing affecting the role has changed since $previous_tag"
	exit 0
fi

echo >&2 "The role has changed since $previous_tag"
echo "${tag_prefix}$((last_release + 1))"
