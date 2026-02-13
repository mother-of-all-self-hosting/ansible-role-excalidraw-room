<!--
SPDX-FileCopyrightText: 2020 - 2024 MDAD project contributors
SPDX-FileCopyrightText: 2020 - 2024 Slavi Pantaleev
SPDX-FileCopyrightText: 2020 Aaron Raimist
SPDX-FileCopyrightText: 2020 Chris van Dijk
SPDX-FileCopyrightText: 2020 Dominik Zajac
SPDX-FileCopyrightText: 2020 Mickaël Cornière
SPDX-FileCopyrightText: 2022 François Darveau
SPDX-FileCopyrightText: 2022 Julian Foad
SPDX-FileCopyrightText: 2022 Warren Bailey
SPDX-FileCopyrightText: 2023 Antonis Christofides
SPDX-FileCopyrightText: 2023 Felix Stupp
SPDX-FileCopyrightText: 2023 Pierre 'McFly' Marty
SPDX-FileCopyrightText: 2024 - 2025 Suguru Hirahara

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Setting up Excalidraw collaboration server

This is an [Ansible](https://www.ansible.com/) role which installs an [example collaboration server](https://github.com/excalidraw/excalidraw-room) for [Excalidraw](https://excalidraw.com/) to run as a [Docker](https://www.docker.com/) container wrapped in a systemd service.

It enables to self-host the collaboration server for your Excalidraw's instance, which by default is configured to connect to the Excalidraw's server at `oss-collab.excalidraw.com`.

See the project's [documentation](https://github.com/excalidraw/excalidraw-room/blob/master/README.md) to learn what it does and why it might be useful to you.

>[!NOTE]
> The role is configured to build the Docker image by default, as it is not provided by the upstream project. Before proceeding, make sure that the machine which you are going to run the Ansible commands against has sufficient computing power to build it.

## Adjusting the playbook configuration

To enable the server with this role, add the following configuration to your `vars.yml` file.

**Note**: the path should be something like `inventory/host_vars/mash.example.com/vars.yml` if you use the [MASH Ansible playbook](https://github.com/mother-of-all-self-hosting/mash-playbook).

```yaml
########################################################################
#                                                                      #
# excalidraw_room                                                      #
#                                                                      #
########################################################################

excalidraw_room_enabled: true

########################################################################
#                                                                      #
# /excalidraw_room                                                     #
#                                                                      #
########################################################################
```

### Set the hostname

To enable the server you need to set the hostname as well. To do so, add the following configuration to your `vars.yml` file. Make sure to replace `example.com` with your own value.

```yaml
excalidraw_room_hostname: "example.com"
```

After adjusting the hostname, make sure to adjust your DNS records to point the domain to your server.

**Note**: hosting Excalidraw collaboration server client under a subpath (by configuring the `excalidraw_room_path_prefix` variable) does not seem to be possible due to Excalidraw collaboration server's technical limitations.

### Extending the configuration

There are some additional things you may wish to configure about the service.

Take a look at:

- [`defaults/main.yml`](../defaults/main.yml) for some variables that you can customize via your `vars.yml` file. You can override settings (even those that don't have dedicated playbook variables) using the `excalidraw_room_environment_variables_additional_variables` variable

## Installing

After configuring the playbook, run the installation command of your playbook as below:

```sh
ansible-playbook -i inventory/hosts setup.yml --tags=setup-all,start
```

If you use the MASH playbook, the shortcut commands with the [`just` program](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/just.md) are also available: `just install-all` or `just setup-all`

## Usage

After running the command for installation, the Excalidraw collaboration server becomes available at the specified hostname like `https://example.com`.

### Build your Excalidraw instance

To use the collaboration server, it is necessary for you to build and install your Excalidraw instance, after setting the hostname of the server to `VITE_APP_WS_SERVER_URL` on its [`.env.production`](https://github.com/excalidraw/excalidraw/blob/master/.env.production).

If you are looking for an Ansible role for installing it on Docker, you can check out [this role (ansible-role-excalidraw)](https://github.com/mother-of-all-self-hosting/ansible-role-excalidraw) maintained by the [Mother-of-All-Self-Hosting (MASH)](https://github.com/mother-of-all-self-hosting) team.

## Troubleshooting

### Check the service's logs

You can find the logs in [systemd-journald](https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html) by logging in to the server with SSH and running `journalctl -fu excalidraw-room` (or how you/your playbook named the service, e.g. `mash-excalidraw-room`).
