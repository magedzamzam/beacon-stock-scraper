# SELinux on Oracle Linux 9

This stack ships nginx config and TLS certs as bind-mounted volumes.
Oracle Linux 9 enforces SELinux by default, which can block container
processes from reading those files unless the right context is applied.

If you see `Permission denied` from the nginx container, run:

    sudo chcon -Rt svirt_sandbox_file_t /opt/beacon-screener/infra/nginx
    sudo chcon -Rt svirt_sandbox_file_t /opt/beacon-screener/db

Or, in docker-compose.yml, append `:Z` to each bind mount, e.g.:

    - ./infra/nginx/nginx.conf:/etc/nginx/nginx.conf:ro,Z

`:Z` tells Docker to relabel the file with a private SELinux label.
Use `:z` (lowercase) if multiple containers need to share it.

To check enforcement: `sestatus`
To temporarily debug only: `sudo setenforce 0`  (NOT for production).
