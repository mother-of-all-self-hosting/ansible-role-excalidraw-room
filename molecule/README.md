<!--
SPDX-FileCopyrightText: 2018-2025 Slavi Pantaleev
SPDX-FileCopyrightText: 2019-2022 Aaron Raimist
SPDX-FileCopyrightText: 2019-2023 MDAD project contributors
SPDX-FileCopyrightText: 2023 QEDeD
SPDX-FileCopyrightText: 2024 Fabio Bonelli
SPDX-FileCopyrightText: 2024 Nikita Chernyi
SPDX-FileCopyrightText: 2024-2026 Suguru Hirahara
SPDX-FileCopyrightText: 2026 spatterlight

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Molecule Testing

This role supports [Molecule](https://docs.ansible.com/projects/molecule/), an Ansible testing framework designed for developing and testing Ansible collections, playbooks, and roles.

## Prerequisites

To utilize Molecule you need to prepare several requirements:

- **x86** computer running one of these operating systems that make use of [systemd](https://systemd.io/):
  - **Archlinux**
  - **CentOS**, **Rocky Linux**, **AlmaLinux**, or possibly other RHEL alternatives (although your mileage may vary)
  - **Debian** (10/Buster or newer)
  - **Ubuntu** (18.04 or newer, although [20.04 may be problematic](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/ansible.md#supported-ansible-versions) if you run the Ansible playbook on it)
- `root` access on the computer which Molecule runs against
- [Ansible](http://ansible.com/) program
- [Python](https://www.python.org/)
  - Most distributions install Python by default, but some don't (e.g. Ubuntu 18.04) and require manual installation (something like `apt-get install python3`)
- [Docker](https://www.docker.com)
  - Access to Docker UNIX socket (`/var/run/docker.sock`) is required by default

## Installation

To set up the environment for using Molecule, run the command below on the terminal:

```bash
python3 -m venv ./molecule/venv
source ./molecule/venv/bin/activate
pip3 install -r ./molecule/requirements.txt
```

## Scenarios

There are two testing scenarios available.

### `default`

Tests an installation which uses the pre-built image Excalidraw publishes on Docker Hub (`excalidraw_room_container_image_self_build: false`), with the Traefik labels turned on.

### `default-selfbuild`

Tests an installation which builds the container image itself, which is what the role does by default, with the Traefik labels turned off. This is the scenario which covers the Node.js release that `excalidraw_room_container_image_self_build_base_image_tag` pins — the one dependency Renovate proposes updates for in this repository.

### What both of them check

The collaboration server answers `Excalidraw collaboration server is up :)` on `/` from a two-line Express handler which knows nothing about collaboration, and would keep answering it with Socket.IO entirely broken. So the central check in both scenarios is [`files/excalidraw-room-collaboration-probe.py`](files/excalidraw-room-collaboration-probe.py), which speaks Engine.IO v4 over raw WebSockets with nothing but the Python standard library. It opens two Socket.IO clients, puts them in a room, and requires that a broadcast from one arrives at the other with its binary attachments intact — and that a broadcast addressed to a room nobody is in arrives nowhere.

Both scenarios also pick a port which is none of the ones the collaboration server would bind on its own, and an `Access-Control-Allow-Origin` value which is not the `*` it answers when unconfigured, so that `templates/env.j2` is shown to have been acted upon rather than merely written.

## Running

By default it is configured to run the scenarios on Ubuntu 26.04.

```bash
molecule test --scenario-name default
```

You can utilize other distributions by setting one to the `MOLECULE_DISTRO` environment variable:

```bash
# Ubuntu 24.04
MOLECULE_DISTRO=ubuntu2404 molecule test --scenario-name default

# Debian 13
MOLECULE_DISTRO=debian13 molecule test --scenario-name default

# Debian 12
MOLECULE_DISTRO=debian12 molecule test --scenario-name default
```

The self-build scenario is run the same way:

```bash
molecule test --scenario-name default-selfbuild
```
