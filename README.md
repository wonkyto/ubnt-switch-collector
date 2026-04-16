# ubnt-switch-collector

A small interface metric collector for Ubiquiti Unifi switches (specifically USW-16-POE) that lack adequate SNMP support. It SSHes into the switch, reads `/proc/port/all`, and writes interface metrics to InfluxDB every minute.

## Docker

All development uses Docker.

### Build

```bash
make build         # Build production image (amd64)
make build-pi      # Build and push arm64 image (Raspberry Pi)
make build-all     # Build and push amd64 + arm64 multi-arch image
```

> `build-pi` and `build-all` require `docker buildx`. Install via `brew install docker-buildx`, then:
>
> ```bash
> mkdir -p ~/.docker/cli-plugins
> ln -sfn /opt/homebrew/opt/docker-buildx/bin/docker-buildx ~/.docker/cli-plugins/docker-buildx
> docker buildx create --name multiplatform --driver docker-container --use
> docker buildx inspect --bootstrap
> ```

### Development

During development, use `make test` to avoid rebuilding the image — it mounts `./app` directly into the container:

```bash
make test
```

### Lint and format

```bash
make lint      # ruff check
make format    # ruff format --check
```

### Tests

```bash
make pytest
```

### Run

Once you've built the image:

```bash
make run
```

## Configuration

### config/config.yaml

Defines the InfluxDB endpoint, switch connection details, and human-readable port descriptions. See `config/config.yaml` for the example structure.

### key/id_rsa

RSA private key for SSH access to the `admin` user on the switch.

### key/known_hosts

Switch host key for SSH verification. Generate with:

```bash
ssh-keyscan <switch-ip> >> key/known_hosts
```
