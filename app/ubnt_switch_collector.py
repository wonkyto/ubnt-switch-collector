#!/usr/bin/env python3

import argparse
import datetime
import logging
import paramiko
import socket
import sys
import time
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from influxdb import InfluxDBClient

default_config_file = "/config/config.yaml"

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
fmt = logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt="%Y/%m/%d %H:%M:%S",
)
ch.setFormatter(fmt)
logger.addHandler(ch)


def get_args():
    """Parse command-line arguments.

    Returns argparse namespace.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config', required=False,
        help=f'Config file (default: {default_config_file})',
        default=default_config_file,
    )
    return parser.parse_args()


def run_cmd(host, user, ssh_private_key, command):
    """Run a remote command on a remote host.

    Returns stdout of command as a list of strings, or None on error.
    """
    result = None
    ssh = paramiko.SSHClient()
    ssh.load_host_keys('/key/known_hosts')
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    private_key = paramiko.RSAKey.from_private_key_file(ssh_private_key)
    try:
        ssh.connect(host, username=user, pkey=private_key, timeout=5)
        _, stdout, _ = ssh.exec_command(command)
        result = stdout.readlines()
    except (
        paramiko.ssh_exception.BadHostKeyException,
        paramiko.ssh_exception.AuthenticationException,
        paramiko.ssh_exception.SSHException,
    ) as e:
        logger.error(f"Login failure: {e}")
    except socket.timeout:
        logger.error("SSH connection timed out")
    except socket.error:
        logger.error("SSH connection refused")
    finally:
        ssh.close()
    return result


def load_yaml_file(yaml_file):
    """Load config from a YAML file.

    Returns dict, or exits on error.
    """
    try:
        with open(yaml_file) as data_file:
            return yaml.load(data_file, Loader=yaml.FullLoader)
    except FileNotFoundError as e:
        logger.error(f"Could not open file: {yaml_file} - {e}")
        sys.exit(1)


def parse_port_data(data):
    """Parse the raw CSV data from the switch.

    Returns dict keyed by port number string.
    Input lines have the form: port=N,link=up,mtu=1500,speed=1000,...
    """
    interface = {}
    for line in data:
        line = line.strip()
        if not line:
            continue
        bits = line.split(",")
        port_parts = bits[0].split("=")
        if len(port_parts) != 2:
            logger.warning(f"Skipping malformed line: {line}")
            continue
        port_num = port_parts[1]
        port = {}
        for bit in bits[1:]:
            if "=" not in bit:
                continue
            key, value = bit.split("=", 1)
            port[key] = value
        interface[port_num] = port
    return interface


def prepare_port_data(poll_time, port_data, switch, if_desc):
    """Prepare parsed port data for writing to InfluxDB.

    Returns list of interface metric dicts ready for write_points().
    """
    if_metrics = []

    for port_num in port_data:
        if port_num not in if_desc:
            logger.warning(f"Port {port_num} not found in InterfaceDesc, skipping")
            continue
        port = port_data[port_num]
        status = 1 if port.get('link') == 'up' else 0

        interface = {
            'measurement': 'interface',
            'time': poll_time,
            'tags': {
                'host': switch['Name'],
                'ifDesc': if_desc[port_num],
            },
            'fields': {
                'IfIndex': int(port_num),
                'IfAdminStatus': status,
                'IfMtu': int(port.get('mtu', 0)),
                'IfSpeed': int(port.get('speed', 0)),
                'IfInOctets': int(port.get('rx_byte', 0)),
                'IfInUcastPkts': int(port.get('rx_pkt', 0)),
                'IfInMulticastPkts': int(port.get('rx_mcast', 0)),
                'IfInBroadcastPkts': int(port.get('rx_bcast', 0)),
                'IfInDiscards': int(port.get('rx_drop', 0)),
                'IfInErrors': int(port.get('rx_error', 0)),
                'IfOutOctets': int(port.get('tx_byte', 0)),
                'IfOutUcastPkts': int(port.get('tx_pkt', 0)),
                'IfOutMulticastPkts': int(port.get('tx_mcast', 0)),
                'IfOutBroadcastPkts': int(port.get('tx_bcast', 0)),
                'IfOutDiscards': int(port.get('tx_drop', 0)),
                'IfOutErrors': int(port.get('tx_error', 0)),
            },
        }
        if_metrics.append(interface)
    return if_metrics


def poll(influx_client, switch, if_desc):
    """Poll the network device and send collected data to InfluxDB."""
    logger.info(f"Polling {switch['User']}@{switch['Host']}")
    result = run_cmd(switch['Host'], switch['User'],
                     switch['PrivKeyFile'], "cat /proc/port/all")

    if result is None:
        logger.warning(f"No data received from {switch['User']}@{switch['Host']}")
        return

    poll_time = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    port_data = parse_port_data(result)
    if_metrics = prepare_port_data(poll_time, port_data, switch, if_desc)

    if not if_metrics:
        logger.warning("No metrics to send")
        return

    if influx_client.write_points(if_metrics):
        logger.info("Metrics sent to InfluxDB successfully")
    else:
        logger.warning("Failed to send metrics to InfluxDB")


def main():
    args = get_args()
    config = load_yaml_file(args.config)

    influx_client = InfluxDBClient(
        host=config['InfluxDb']['Host'],
        port=int(config['InfluxDb']['Port']),
    )
    for attempt in range(1, 11):
        try:
            influx_client.create_database(config['InfluxDb']['Database'])
            influx_client.switch_database(config['InfluxDb']['Database'])
            logger.info("Connected to InfluxDB")
            break
        except Exception as e:
            logger.warning(f"InfluxDB not ready (attempt {attempt}/10): {e}")
            if attempt == 10:
                logger.error("Could not connect to InfluxDB after 10 attempts, exiting")
                sys.exit(1)
            time.sleep(5)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        poll, 'cron', minute='*',
        args=(influx_client, config['Switch'], config['InterfaceDesc']),
    )
    scheduler.start()

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        influx_client.close()


if __name__ == '__main__':
    main()
