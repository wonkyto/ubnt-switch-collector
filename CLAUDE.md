# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python-based metric collector for Ubiquiti Unifi switches (specifically USW-16-POE) that lack adequate SNMP support. It SSHes into the switch, reads `/proc/port/all` (CSV format), and writes interface metrics to InfluxDB every minute using APScheduler.

## Commands

All development uses Docker:

```bash
make build       # Build production Docker image (wonkyto/ubnt-switch-collector:VERSION)
make build-pi    # Build + push arm64 image via docker buildx
make build-all   # Build + push amd64 + arm64 multi-arch image via docker buildx
make lint        # ruff check (dev image)
make format      # ruff format --check (dev image)
make pytest      # Run unit tests (dev image)
make test        # Run script with mounted app + config + key (dev without rebuilding)
make run         # Run from built production image with config + key volumes
```

During development, use `make test` to avoid rebuilding the image after each change — it mounts `./app` directly into the container.

## Required files (not committed)

- `config/config.yaml` — InfluxDB connection, switch host/user/key path, and per-port interface descriptions (see `config/config.yaml` for example structure)
- `key/id_rsa` — RSA private key for SSH access to the switch's `admin` user
- `key/known_hosts` — switch host key for SSH verification; generate with `ssh-keyscan <switch-ip> >> key/known_hosts`

## Architecture

Single-file app: `app/ubnt_switch_collector.py`

**Data flow:**

1. SSH into switch via paramiko → `cat /proc/port/all`
2. `parse_port_data()` — parses CSV lines like `port=N,link=up,mtu=1500,speed=1000,...`
3. `prepare_port_data()` — maps parsed data to InfluxDB `interface` measurement with SNMP-style field names (`IfInOctets`, `IfOutOctets`, etc.) and tags `host` + `ifDesc`
4. Write to InfluxDB via `influxdb` Python client

**Scheduling:** APScheduler `BackgroundScheduler` fires `poll()` on `cron(minute='*')` — once per minute on the minute. The main thread blocks in `while True: time.sleep(1)`.

**InfluxDB startup:** `main()` retries the InfluxDB connection up to 10 times (5s apart) to handle docker-compose startup ordering. Uses the v1 `influxdb` client — if InfluxDB is ever upgraded to v2, switch to `influxdb-client`.

## Docker build stages

The Dockerfile has three stages:

- `base` — python:3.13-slim-bookworm with timezone config
- `production` — installs `requirements.txt` only; used by `make build/build-pi/build-all/run/test`
- `dev` — installs `requirements-dev.txt` (includes prod deps + ruff + pytest); used by `make lint/format/pytest`

## Tests

Unit tests live in `tests/test_ubnt_switch_collector.py`. They test the pure functions (`parse_port_data`, `prepare_port_data`) directly and mock paramiko/InfluxDB for `run_cmd` and `poll`. The `PYTHONPATH=/app` environment variable (set in docker-compose) makes the app module importable.
