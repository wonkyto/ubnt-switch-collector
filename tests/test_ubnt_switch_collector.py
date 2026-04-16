import datetime
import socket
import sys
import os

import pytest
from unittest.mock import MagicMock, patch
import paramiko

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import ubnt_switch_collector as usc  # noqa: E402


# ---------------------------------------------------------------------------
# parse_port_data
# ---------------------------------------------------------------------------

SAMPLE_LINES = [
    "port=1,link=up,mtu=1500,speed=1000,"
    "rx_byte=100,rx_pkt=10,rx_mcast=1,rx_bcast=2,rx_drop=0,rx_error=0,"
    "tx_byte=200,tx_pkt=20,tx_mcast=2,tx_bcast=3,tx_drop=0,tx_error=0\n",
    "port=2,link=down,mtu=1500,speed=0,"
    "rx_byte=0,rx_pkt=0,rx_mcast=0,rx_bcast=0,rx_drop=0,rx_error=0,"
    "tx_byte=0,tx_pkt=0,tx_mcast=0,tx_bcast=0,tx_drop=0,tx_error=0\n",
    "\n",            # empty line — should be skipped
    "malformed\n",  # no port= prefix — should be skipped
]


def test_parse_port_data_parses_fields():
    result = usc.parse_port_data(SAMPLE_LINES)
    assert result['1']['link'] == 'up'
    assert result['1']['mtu'] == '1500'
    assert result['1']['rx_byte'] == '100'


def test_parse_port_data_two_ports():
    result = usc.parse_port_data(SAMPLE_LINES)
    assert set(result.keys()) == {'1', '2'}


def test_parse_port_data_skips_empty_lines():
    result = usc.parse_port_data(["\n", "  \n"])
    assert result == {}


def test_parse_port_data_skips_malformed_lines():
    result = usc.parse_port_data(["malformed\n"])
    assert result == {}


def test_parse_port_data_empty_input():
    assert usc.parse_port_data([]) == {}


# ---------------------------------------------------------------------------
# prepare_port_data
# ---------------------------------------------------------------------------

SWITCH = {'Name': 'myswitch'}
IF_DESC = {'1': 'uplink', '2': 'server'}
POLL_TIME = '2024-01-01T00:00:00Z'

PORT_1 = {
    'link': 'up', 'mtu': '1500', 'speed': '1000',
    'rx_byte': '100', 'rx_pkt': '10', 'rx_mcast': '1', 'rx_bcast': '2',
    'rx_drop': '0', 'rx_error': '0',
    'tx_byte': '200', 'tx_pkt': '20', 'tx_mcast': '2', 'tx_bcast': '3',
    'tx_drop': '0', 'tx_error': '0',
}


def test_prepare_port_data_measurement_and_tags():
    result = usc.prepare_port_data(POLL_TIME, {'1': PORT_1}, SWITCH, IF_DESC)
    assert len(result) == 1
    m = result[0]
    assert m['measurement'] == 'interface'
    assert m['tags']['host'] == 'myswitch'
    assert m['tags']['ifDesc'] == 'uplink'
    assert m['time'] == POLL_TIME


def test_prepare_port_data_fields():
    result = usc.prepare_port_data(POLL_TIME, {'1': PORT_1}, SWITCH, IF_DESC)
    fields = result[0]['fields']
    assert fields['IfAdminStatus'] == 1
    assert fields['IfMtu'] == 1500
    assert fields['IfSpeed'] == 1000
    assert fields['IfInOctets'] == 100
    assert fields['IfOutOctets'] == 200


def test_prepare_port_data_link_down_sets_status_zero():
    port = dict(PORT_1, link='down')
    result = usc.prepare_port_data(POLL_TIME, {'1': port}, SWITCH, IF_DESC)
    assert result[0]['fields']['IfAdminStatus'] == 0


def test_prepare_port_data_skips_port_not_in_if_desc():
    result = usc.prepare_port_data(POLL_TIME, {'99': PORT_1}, SWITCH, IF_DESC)
    assert result == []


def test_prepare_port_data_missing_fields_default_to_zero():
    result = usc.prepare_port_data(POLL_TIME, {'1': {'link': 'up'}}, SWITCH, IF_DESC)
    fields = result[0]['fields']
    assert fields['IfMtu'] == 0
    assert fields['IfInOctets'] == 0
    assert fields['IfOutOctets'] == 0


# ---------------------------------------------------------------------------
# load_yaml_file
# ---------------------------------------------------------------------------

def test_load_yaml_file_reads_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("key: value\n")
    result = usc.load_yaml_file(str(config_file))
    assert result == {'key': 'value'}


def test_load_yaml_file_exits_on_missing_file():
    with pytest.raises(SystemExit):
        usc.load_yaml_file("/nonexistent/path.yaml")


# ---------------------------------------------------------------------------
# run_cmd
# ---------------------------------------------------------------------------

def _make_ssh_mock():
    ssh = MagicMock()
    stdout = MagicMock()
    stdout.readlines.return_value = ["line1\n"]
    ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())
    return ssh


@patch('ubnt_switch_collector.paramiko.RSAKey.from_private_key_file')
@patch('ubnt_switch_collector.paramiko.SSHClient')
def test_run_cmd_returns_output(mock_ssh_cls, mock_key):
    mock_ssh_cls.return_value = _make_ssh_mock()
    result = usc.run_cmd('host', 'user', '/key/id_rsa', 'cat /proc/port/all')
    assert result == ["line1\n"]


@patch('ubnt_switch_collector.paramiko.RSAKey.from_private_key_file')
@patch('ubnt_switch_collector.paramiko.SSHClient')
def test_run_cmd_closes_connection_on_success(mock_ssh_cls, mock_key):
    mock_ssh = _make_ssh_mock()
    mock_ssh_cls.return_value = mock_ssh
    usc.run_cmd('host', 'user', '/key/id_rsa', 'cat /proc/port/all')
    mock_ssh.close.assert_called_once()


@pytest.mark.parametrize("exc", [
    paramiko.AuthenticationException("auth"),
    paramiko.ssh_exception.BadHostKeyException("host", MagicMock(), MagicMock()),
    paramiko.SSHException("ssh"),
    socket.timeout(),
    socket.error(),
])
@patch('ubnt_switch_collector.paramiko.RSAKey.from_private_key_file')
@patch('ubnt_switch_collector.paramiko.SSHClient')
def test_run_cmd_closes_connection_on_error(mock_ssh_cls, mock_key, exc):
    mock_ssh = MagicMock()
    mock_ssh.connect.side_effect = exc
    mock_ssh_cls.return_value = mock_ssh
    result = usc.run_cmd('host', 'user', '/key/id_rsa', 'cat /proc/port/all')
    assert result is None
    mock_ssh.close.assert_called_once()


# ---------------------------------------------------------------------------
# poll
# ---------------------------------------------------------------------------

SWITCH_CONFIG = {
    'Host': '192.168.0.2',
    'User': 'admin',
    'Name': 'myswitch',
    'PrivKeyFile': '/key/id_rsa',
}


@patch('ubnt_switch_collector.run_cmd', return_value=None)
def test_poll_skips_write_when_run_cmd_returns_none(mock_run_cmd):
    mock_influx = MagicMock()
    usc.poll(mock_influx, SWITCH_CONFIG, IF_DESC)
    mock_influx.write_points.assert_not_called()


@patch('ubnt_switch_collector.run_cmd')
def test_poll_skips_write_when_no_metrics_produced(mock_run_cmd):
    # Port 99 is not in IF_DESC so prepare_port_data returns []
    mock_run_cmd.return_value = [
        "port=99,link=up,mtu=1500,speed=1000,"
        "rx_byte=0,rx_pkt=0,rx_mcast=0,rx_bcast=0,rx_drop=0,rx_error=0,"
        "tx_byte=0,tx_pkt=0,tx_mcast=0,tx_bcast=0,tx_drop=0,tx_error=0\n"
    ]
    mock_influx = MagicMock()
    usc.poll(mock_influx, SWITCH_CONFIG, IF_DESC)
    mock_influx.write_points.assert_not_called()


@patch('ubnt_switch_collector.run_cmd')
def test_poll_writes_metrics_when_data_available(mock_run_cmd):
    mock_run_cmd.return_value = [
        "port=1,link=up,mtu=1500,speed=1000,"
        "rx_byte=100,rx_pkt=10,rx_mcast=1,rx_bcast=1,rx_drop=0,rx_error=0,"
        "tx_byte=200,tx_pkt=20,tx_mcast=2,tx_bcast=2,tx_drop=0,tx_error=0\n"
    ]
    mock_influx = MagicMock()
    mock_influx.write_points.return_value = True
    usc.poll(mock_influx, SWITCH_CONFIG, IF_DESC)
    mock_influx.write_points.assert_called_once()
