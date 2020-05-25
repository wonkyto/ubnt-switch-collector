#!/usr/bin/env python3

import argparse
import asyncio
import datetime
import logging
import paramiko
import socket
import sys
import time
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from influxdb import InfluxDBClient

default_config_file = "/config/config.yaml"

# Set up logger
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
fmt = logging.Formatter(fmt='%(asctime)s.%(msecs)03d - '
                        + '%(levelname)s - %(message)s',
                        datefmt="%Y/%m/%d %H:%M:%S")
ch.setFormatter(fmt)
logger.addHandler(ch)


def get_args():
    """Parse the command line options

    Returns argparse object
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=False, help='Config File '
                        + 'Default: (' + default_config_file + ')',
                        default=default_config_file)
    args = parser.parse_args()
    return args


def run_cmd(host, user, ssh_private_key, command):
    """Run a remote command on remote host

    Returns stdout of command as a string array
    """
    result = None

    # Make an ssh connection
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    private_key = paramiko.RSAKey.from_private_key_file(ssh_private_key)
    try:
        ssh.connect(host, username=user, pkey=private_key, timeout=5)
        stdin, stdout, stderr = ssh.exec_command(command)
        result = stdout.readlines()
        ssh.close()
    except (paramiko.ssh_exception.BadHostKeyException,
            paramiko.ssh_exception.AuthenticationException,
            paramiko.ssh_exception.SSHException) as e:
        logger.error("Login Failure: {}".format(str(e)))
    except socket.timeout:
        logger.error('timeout')
    except socket.error:
        logger.error('Connection Refused')
    return result


def load_yaml_file(yaml_file):
    """Load the config file info from the yaml

    Returns dict
    """
    result = None

    # Open the yaml file
    try:
        with open(yaml_file) as data_file:
            data = yaml.load(data_file, Loader=yaml.FullLoader)
        result = data
    except (FileNotFoundError) as e:
        logger.error("Could not open file: {} - {}".format(yaml_file, str(e)))
        sys.exit(1)
    return result


def parse_port_data(data):
    """Parse the raw csv data we got from the switch

    Returns dict of data
    """
    interface = {}
    for line in data:
        bits = line.split(",")
        port_num = bits[0].split("=")[1]
        port = {}
        for bit in bits[1:]:
            # Build up interface port dict
            key, value = bit.split("=")
            port[key] = value
        interface[port_num] = port
    return interface


def prepare_port_data(poll_time, port_data, switch, if_desc):
    """Prepare the parsed data into a data object that's ready to send to InfluxDB

    Returns dict of interface metrics to send to influxDB
    """
    if_metrics = []

    for port_num in port_data:
        status = 1 if port_data[port_num]['link'] == 'up' else 0

        interface = {
            'measurement': 'interface',
            'tags': {
                'host': switch['Name'],
                'ifDesc': if_desc[port_num]
            },
            'fields': {
                'IfIndex': port_num,
                'IfAdminStatus': int(status),
                'IfMtu': int(port_data[port_num]['mtu']),
                'IfSpeed': int(port_data[port_num]['speed']),
                'IfInOctets': int(port_data[port_num]['rx_byte']),
                'IfInUcastPkts': int(port_data[port_num]['rx_pkt']),
                'IfInMulticastPkts': int(port_data[port_num]['rx_mcast']),
                'IfInBroadcastPkts': int(port_data[port_num]['rx_bcast']),
                'IfInDiscards': int(port_data[port_num]['rx_drop']),
                'IfInErrors': int(port_data[port_num]['rx_error']),
                'IfOutOctets': int(port_data[port_num]['tx_byte']),
                'IfOutUcastPkts': int(port_data[port_num]['tx_pkt']),
                'IfOutMulticastPkts': int(port_data[port_num]['tx_mcast']),
                'IfOutBroadcastPkts': int(port_data[port_num]['tx_bcast']),
                'IfOutDiscards': int(port_data[port_num]['tx_drop']),
                'IfOutErrors': int(port_data[port_num]['tx_error']),
            }
        }
        if_metrics.append(interface)
    return if_metrics


def poll(influx_client, switch, if_desc):
    """Poll the network device, send collecte data to influxDB"""
    logger.info("Polling {}@{}".format(switch['User'], switch['Host']))
    result = run_cmd(switch['Host'], switch['User'],
                     switch['PrivKeyFile'], "cat /proc/port/all")

    if result is not None:
        poll_time = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        port_data = parse_port_data(result)
        if_metrics = prepare_port_data(poll_time, port_data, switch, if_desc)
        if influx_client.write_points(if_metrics):
            logger.debug("Sending metrics to influxdb: successful")
        else:
            logger.debug("Sending metrics to influxdb: failed")

    else:
        logger.warning("No data received from {}@{}".format(switch['User'],
                                                            switch['Host']))


def main():
    # Get arguements
    args = get_args()
    # Load configure file
    config = load_yaml_file(args.config)

    # We will be running this container in the same docker-compose configuration
    # as influxdb. To ensure we provide enough time for influxdb to start,
    # we wait 10 seconds
    time.sleep(10)

    # Make a connection to the InfluxDB Database
    # Create a new database if it doesn't exist
    influx_client = InfluxDBClient(host=config['InfluxDb']['Host'],
                                   port=config['InfluxDb']['Port'])
    influx_client.create_database(config['InfluxDb']['Database'])
    influx_client.switch_database(config['InfluxDb']['Database'])

    # Create a scheduler, and run the poller every 1 minute on the minute
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll, 'cron', minute='*',
                      args=(influx_client, config['Switch'],
                            config['InterfaceDesc']))
    scheduler.start()

    # Execution will block here until Ctrl+C is pressed.
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass

    influx_client.close()


if __name__ == '__main__':
    main()
