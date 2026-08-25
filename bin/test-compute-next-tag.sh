#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Exercises bin/compute-next-tag.sh against throwaway git repositories.
#
# Usage: bin/test-compute-next-tag.sh
#
# Every scenario creates a repository in a temporary directory, gives it role
# files and a release history, and then replays a series of merges through the
# real script, tagging as it goes just like the autotag workflow does. This
# repository is never touched and no network access is needed.

set -euo pipefail

script_under_test="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/compute-next-tag.sh"

failures=0
workdir=''

cleanup() {
	cd /
	if [ -n "$workdir" ]; then
		rm -rf "$workdir"
		workdir=''
	fi
}

trap cleanup EXIT

# Starts a scenario with a repository in the state this one really is in: an
# `excalidraw_room_version` of `latest`, and a release history whose version
# component is a date rather than anything derived from that value.
#
# The defaults file deliberately carries the traps this role's real one has: an
# image tag derived from the version, and a self-build base image whose own tag
# is a version - the leaf Renovate proposes updates for, and the one thing here
# that must never be mistaken for the version of the role. The `# renovate:`
# annotation is included so that a future refactor which moved it onto the wrong
# variable would be noticed here.
scenario() {
	echo "$1"

	cleanup
	workdir="$(mktemp -d)"

	mkdir -p "$workdir/bin" "$workdir/defaults" "$workdir/meta" "$workdir/tasks" "$workdir/templates"
	cp "$script_under_test" "$workdir/bin/"
	cd "$workdir"

	git init -q -b main .
	git config user.email 'test@example.com'
	git config user.name 'Test'
	git config commit.gpgsign false

	cat > defaults/main.yml <<-'YAML'
		excalidraw_room_version: latest
		excalidraw_room_container_image: "{{ excalidraw_room_container_image_registry_prefix }}excalidraw/excalidraw-room:{{ excalidraw_room_container_image_tag }}"
		excalidraw_room_container_image_tag: "{{ excalidraw_room_version }}"
		excalidraw_room_container_image_self_build_repo_version: "{{ excalidraw_room_version if excalidraw_room_version != 'latest' else 'master' }}"
		excalidraw_room_container_image_self_build_base_image: "{{ excalidraw_room_container_image_self_build_base_image_name }}:{{ excalidraw_room_container_image_self_build_base_image_tag }}"
		excalidraw_room_container_image_self_build_base_image_name: docker.io/library/node
		# renovate: datasource=docker depName=node versioning=docker
		excalidraw_room_container_image_self_build_base_image_tag: 24.19.0-alpine
	YAML
	printf 'placeholder\n' > meta/main.yml
	printf 'placeholder\n' > tasks/main.yml
	printf 'placeholder\n' > templates/env.j2
	printf 'placeholder\n' > README.md

	git add -A
	git commit -qm 'Initial commit'

	local tag
	for tag in v2023.1.5-4 v2023.6.15-3 v2023.12.15-0 v2023.12.15-9; do
		git tag "$tag"
	done
}

# Applies a change, commits it, and tags whatever the script says it should be.
# Prints the tag, or nothing when the script decided against a release.
merge() {
	local change="$1" tag

	eval "$change"
	git add -A
	git commit -qm 'Merge'

	tag="$(bin/compute-next-tag.sh 2>/dev/null)"

	if [ -n "$tag" ]; then
		git tag "$tag"
	fi

	printf '%s' "$tag"
}

expect() {
	local description="$1" expected="$2" actual="$3"

	if [ "$actual" = "$expected" ]; then
		printf '  ok   | %s -> %s\n' "$description" "${actual:-no release}"
	else
		printf '  FAIL | %s -> expected %s, got %s\n' "$description" "${expected:-no release}" "${actual:-no release}"
		failures=$((failures + 1))
	fi
}

bump_base_image="sed -i 's|^excalidraw_room_container_image_self_build_base_image_tag: 24.19.0-alpine|excalidraw_room_container_image_self_build_base_image_tag: 24.19.1-alpine|' defaults/main.yml"
pin_version="sed -i 's|^excalidraw_room_version: latest|excalidraw_room_version: 1.0.0|' defaults/main.yml"
edit_task="printf 'a task\n' >> tasks/main.yml"
edit_template="printf 'a line\n' >> templates/env.j2"
edit_meta="printf 'a line\n' >> meta/main.yml"
edit_readme="printf 'documentation\n' >> README.md"
edit_script="printf '# a comment\n' >> bin/compute-next-tag.sh"

# Every change that affects the role has to be released exactly once, and the
# order in which the changes arrive must not matter.
scenario 'Changes to the role, released one after another'
expect 'task edit'       v2023.12.15-10 "$(merge "$edit_task")"
expect 'template edit'   v2023.12.15-11 "$(merge "$edit_template")"
expect 'meta edit'       v2023.12.15-12 "$(merge "$edit_meta")"

scenario 'A base image bump, which is a dependency and not the role version'
# Renovate's only leaf in this repository is the Node.js base image tag. Bumping
# it must move the release counter and must not be mistaken for a version of the
# role, which would publish a `v24.19.1-0` tag out of nowhere.
expect 'base image bump' v2023.12.15-10 "$(merge "$bump_base_image")"
expect 'task edit'       v2023.12.15-11 "$(merge "$edit_task")"

scenario 'A base image bump merged after other role changes'
expect 'task edit'       v2023.12.15-10 "$(merge "$edit_task")"
expect 'base image bump' v2023.12.15-11 "$(merge "$bump_base_image")"

# Older series exist and must not be continued from. If the version were read
# with a loose pattern, or the newest tag picked lexically rather than by
# version, the counter would carry on from v2023.6.15-3 or v2023.1.5-4. A lexical
# sort would also rank -9 above -10, which is exactly where this repository is.
scenario 'Older release series'
expect 'task edit' v2023.12.15-10 "$(merge "$edit_task")"

scenario 'Commits that do not affect the role'
expect 'README'   ''               "$(merge "$edit_readme")"
expect 'a script' ''               "$(merge "$edit_script")"
expect 'a task'   v2023.12.15-10   "$(merge "$edit_task")"

scenario 'Release numbers past 9'
for release_number in 10 11; do
	git tag "v2023.12.15-$release_number"
done
expect 'a task' v2023.12.15-12 "$(merge "$edit_task")"

# Should the collaboration server ever start publishing versions, naming one in
# `excalidraw_room_version` has to open a series of its own rather than carry on
# counting from the dates.
scenario 'The collaboration server starting to publish versions'
expect 'a real version' v1.0.0-0 "$(merge "$pin_version")"
expect 'task edit'      v1.0.0-1 "$(merge "$edit_task")"

scenario 'A pinned version that has already been released'
git tag v1.0.0-0
expect 'a real version' v1.0.0-1 "$(merge "$pin_version")"

if [ "$failures" -gt 0 ]; then
	echo >&2 "$failures scenario(s) behaved unexpectedly"
	exit 1
fi

echo 'All scenarios behaved as expected'
