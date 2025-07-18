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

# Setting up Excalidraw

This is an [Ansible](https://www.ansible.com/) role which installs the [Excalidraw](https://excalidraw.com/) client to run as a [Docker](https://www.docker.com/) container wrapped in a systemd service.

Excalidraw is a free and open source virtual whiteboard for sketching hand-drawn like diagrams. It saves data locally on the browser, and the data is end-to-end encrypted.

See the project's [documentation](https://docs.excalidraw.com/) to learn what it does and why it might be useful to you.

## Adjusting the playbook configuration

To enable the client with this role, add the following configuration to your `vars.yml` file.

**Note**: the path should be something like `inventory/host_vars/mash.example.com/vars.yml` if you use the [MASH Ansible playbook](https://github.com/mother-of-all-self-hosting/mash-playbook).

```yaml
########################################################################
#                                                                      #
# excalidraw                                                           #
#                                                                      #
########################################################################

excalidraw_enabled: true

########################################################################
#                                                                      #
# /excalidraw                                                          #
#                                                                      #
########################################################################
```

### Set the hostname

To enable the client you need to set the hostname as well. To do so, add the following configuration to your `vars.yml` file. Make sure to replace `example.com` with your own value.

```yaml
excalidraw_hostname: "example.com"
```

After adjusting the hostname, make sure to adjust your DNS records to point the domain to your server.

**Note**: hosting Excalidraw client under a subpath (by configuring the `excalidraw_path_prefix` variable) does not seem to be possible due to Excalidraw's technical limitations.

### Password-protect the instance (optional)

By default the instance is public and accessible to anyone. You can protect it with HTTP Basic authentication by adding the following configuration to your `vars.yml` file:

```yaml
excalidraw_basic_auth_enabled: true
excalidraw_basic_auth_username: YOUR_USERNAME_HERE
excalidraw_basic_auth_password: YOUR_PASSWORD_HERE
```

Replace `YOUR_USERNAME_HERE` and `YOUR_PASSWORD_HERE` with your own values. For `excalidraw_basic_auth_password`, generating a strong one is preferred (e.g. `pwgen -s 64 1`).

### Extending the configuration

There are some additional things you may wish to configure about the component.

Take a look at:

- [`defaults/main.yml`](../defaults/main.yml) for some variables that you can customize via your `vars.yml` file. You can override settings (even those that don't have dedicated playbook variables) using the `excalidraw_environment_variables_additional_variables` variable

## Installing

After configuring the playbook, run the installation command of your playbook as below:

```sh
ansible-playbook -i inventory/hosts setup.yml --tags=setup-all,start
```

If you use the MASH playbook, the shortcut commands with the [`just` program](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/just.md) are also available: `just install-all` or `just setup-all`

## Usage

After running the command for installation, the Excalidraw client becomes available at the specified hostname like `https://example.com`.

>[!NOTE]
> At the moment, self-hosting your own instance doesn't support sharing or collaboration features (see [this section](https://docs.excalidraw.com/docs/introduction/development#self-hosting) on the official documentation).

## Troubleshooting

### Check the service's logs

You can find the logs in [systemd-journald](https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html) by logging in to the server with SSH and running `journalctl -fu excalidraw` (or how you/your playbook named the service, e.g. `mash-excalidraw`).
