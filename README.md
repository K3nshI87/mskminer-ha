# MSKMiner Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant **NOT OFICСIAL** integration for miners running [MSKMiner](https://mskminer.com) firmware.

## Features

- **Auto-discovery** — scans your network range and finds all MSKMiner devices automatically
- **Sensors** — hashrate, temperature (inlet/outlet), power consumption, uptime, PSU fan, active pool, miner status
- **Buttons** — restart miner, reboot device, blink LED

## Installation via HACS

1. Open HACS in Home Assistant
2. Click the three-dot menu → **Custom repositories**
3. Add URL: `https://github.com/K3nshI87/mskminer-ha`
4. Category: **Integration**
5. Click **Download**
6. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **MSKMiner**
3. Enter your network range (e.g. `192.168.1.0/24`), username and password
4. The integration will scan and add all found miners automatically

## Supported formats for IP range

| Format | Example |
|---|---|
| CIDR | `192.168.1.0/24` |
| Range (last octet) | `192.168.1.1-254` |
| Range (full) | `192.168.1.1-192.168.1.254` |
| Single IP | `192.168.1.115` |

## Sensors per device

| Sensor | Unit |
|---|---|
| Hashrate | TH/s |
| Avg Hashrate | TH/s |
| Temperature (Outlet) | °C |
| Temperature (Inlet) | °C |
| Power | W |
| Uptime | h |
| PSU Fan Speed | RPM |
| PSU Temperature | °C |
| Active Pool | — |
| Status | — |
