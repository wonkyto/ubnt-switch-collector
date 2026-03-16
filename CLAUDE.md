# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python-based metric collector for Ubiquiti Unifi switches (specifically USW-16-POE) that lack adequate SNMP support. It SSHes into the switch, reads `/proc/port/all` (CSV format), and writes interface metrics to InfluxDB every minute using APScheduler.

## Commands

All development uses Docker:

```bash
make build    # Build Docker image (wonkyto/ubnt-switch-collector:VERSION)
make flake8   # Lint with flake8 (mounts ./app into existing image)
make test     # Run script with mounted app + config + key (for dev without rebuilding)
make run      # Run from built image with config + key volumes
```

During development, use `make test` to avoid rebuilding the image after each change — it mounts `./app` directly into the container.

## Required files (not committed)

- `config/config.yaml` — InfluxDB connection, switch host/user/key path, and per-port interface descriptions (see `config/config.yaml` for example structure)
- `key/id_rsa` — RSA private key for SSH access to the switch's `admin` user

## Architecture

Single-file app: `app/ubnt-switch-collector.py`

**Data flow:**
1. SSH into switch via paramiko → `cat /proc/port/all`
2. `parse_port_data()` — parses CSV lines like `port=N,link=up,mtu=1500,speed=1000,...`
3. `prepare_port_data()` — maps parsed data to InfluxDB `interface` measurement with SNMP-style field names (`IfInOctets`, `IfOutOctets`, etc.) and tags `host` + `ifDesc`
4. Write to InfluxDB via `influxdb` Python client

**Scheduling:** APScheduler `AsyncIOScheduler` fires `poll()` on `cron(minute='*')` — once per minute on the minute.

**Startup delay:** 10-second `time.sleep` in `main()` to allow InfluxDB to start when both containers launch together via docker-compose.
