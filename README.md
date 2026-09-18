# Inverter Modbus/TCP Tool

A small dependency-free Python command-line tool for reading and writing registers on ESC3-XK / ESC3-XKW-DS hybrid inverters over Ethernet using Modbus/TCP.

The register definitions are based on the ESC3-5K-DS Modbus register sheet V008 and the ESC3-5KW-DS Communication Protocol documentation.

> **Important:** Writing inverter settings can affect grid compliance, battery operation, and equipment safety. Verify every value against the inverter documentation before writing it. 

## Features

- Read holding and input registers
- Write a single holding register
- Unlock writes with the inverter PIN
- Read several registers in one command using comma-separated names
- Human-readable output by default
- JSON output with `-j`
- List all registers known by the tool with `--list`
- Verbose Modbus/TCP frame logging with `-v`
- Configurable host, TCP port, and timeout
- Handles text registers, signed values, scaled values, and multi-register 32-bit values
- Uses register variable names rather than raw register addresses

## Requirements

- Python 3.8 or newer
- Network access to the inverter
- No third-party Python packages are required

## Installation

Copy `inverter.py` to the desired directory and make it executable:

```bash
chmod +x inverter.py
```

## Command-line syntax

```text
./inverter.py [options]
```

### Options

| Option | Description |
|---|---|
| `-r NAME[,NAME...]` | Read one or more registers |
| `-w NAME VALUE` | Write `VALUE` to a writable register |
| `-h HOST` | Inverter IP address or hostname |
| `-P PORT` | Modbus/TCP port; default is `502` |
| `-p PIN` | Unlock PIN for writing; normally `1919` |
| `-j` | Return JSON instead of text output |
| `--list` | List all known registers and exit |
| `-v` | Show verbose request and response frames |
| `-t SECONDS` | Socket timeout; default is `5` seconds |
| `--help` | Show command help |


## Reading registers

Read one register:

```bash
./inverter.py -r SeriesNumber -h 192.168.0.1
```

Example output:

```text
SeriesNumber: SDHGr42342
```

Read multiple registers by separating names with commas:

```bash
./inverter.py -r SeriesNumber,Language,Temperature -h 10.0.1.40
```

Example output:

```text
SeriesNumber: SDHGr42342
Language: 0
Temperature: 24
```

Whitespace around commas is ignored, so this is also valid:

```bash
./inverter.py -r SeriesNumber, GridVoltage, Temperature -h 10.0.1.40
```

Read registers as JSON:

```bash
./inverter.py -r SeriesNumber,Language,Temperature \
  -h 10.0.1.40 -j
```

Example:

```json
{
  "SeriesNumber": "SDHGr42342",
  "Language": 0,
  "Temperature": 24
}
```

Read with Modbus/TCP frames displayed:

```bash
./inverter.py -r Temperature -h 10.0.1.40 -v
```

Example request for `Temperature`:

```text
>> 00 01 00 00 00 06 01 04 00 09 00 01
```

## Writing registers

Most writable holding registers require the inverter to be unlocked first. Supply the PIN with `-p`:

```bash
./inverter.py -w Allow_Grid_Charge 3 \
  -p 1919 -h 10.0.1.40
```

Set the language to German:

```bash
./inverter.py -w Language 1 \
  -p 1919 -h 10.0.1.40
```

Use verbose mode when testing writes:

```bash
./inverter.py -w Language 0 \
  -p 1919 -h 10.0.1.40 -v
```

The tool unlocks by writing the PIN to register `0x0000`, then writes the requested value using function `0x06`.

## Listing registers

List all registers known to the tool:

```bash
./inverter.py --list
```

The list includes the variable name, access mode, function code, register address, length, data type, scale, unit, and description where available.

Register names are case-sensitive unless the script's alias handling says otherwise. Use the names shown by `--list`.

## Common register names

### Holding registers

| Name | Address | Access | Description |
|---|---:|---|---|
| `SeriesNumber` | `0x01` | Read/write | Inverter serial number |
| `FactoryName` | `0x09` | Read | Factory name |
| `ModuleName` | `0x11` | Read | Module name |
| `Machine_Type` | `0x19` | Read | Machine type |
| `MyAddress` | `0x1A` | Read/write | Machine address |
| `Language` | `0x1B` | Read/write | 0=English, 1=German |
| `IP_Method` | `0x1C` | Read/write | 0=Dhcp, 1=Static |
| `Machine_switch` | `0x1D` | Read | Software and hardware switch state |
| `Safety` | `0x1F` | Read/write | Grid safety profile, refer manual |
| `PvConnectionMode` | `0x20` | Read/write | PV input mode: 0=No solar, 1=Two strings in parallel, 2=Two strings parallell independent |
| `SolarChargerUseMode` | `0xB9` | Read/write | Operating mode: 0: Self use mode, 1=ForceTimeUse, 2=ExternalUse, 3=BackupUse, 4=FFR, 5=RemoteControl |
| `Allow_Grid_Charge` | `0xBA` | Read/write | Grid-charging permissions, 0=No, 1=Allow period 1, 2=Allow period 2, 3=Allow |
| `Export_control_user_limit` | `0xBC` | Read/write | User export limit |
| `Battery1Type` | `0xD7` | Read/write | Battery type: 0=Lead acid, 1=Lithium |
| `Battery_Health` | `0xDE` | Read | Battery health |
| `BackUp_GridChargeFlag` | `0x110` | Read/write | Allow grid charging in backup mode |
| `AllowSolarMaxUse` | `0x120` | Read/write | Allow remaining solar power to feed into the grid |
| `wRemoteChargeSubMode` | `0x11c` | Read/write | Mode: 0=Charge only from solar, 1=Charge, 2=4, 3=Discharge, 4=Charge/Discharge as set by 0x11d, 9=Self use |
| `wRemoteChargerPowerSet` | `0x11d` | Read/write | Watt to charge (postive) or discharge (negative) |
### Input registers

| Name | Address | Description |
|---|---:|---|
| `GridVoltage` | `0x0001` | Grid voltage |
| `GridCurrent` | `0x0002` | Grid current |
| `GridPower` | `0x0003` | Inverter output power |
| `GridFrequency` | `0x0004` | Grid frequency |
| `PvVoltage1` | `0x0005` | PV input 1 voltage |
| `PvVoltage2` | `0x0006` | PV input 2 voltage |
| `PvCurrent1` | `0x0007` | PV input 1 current |
| `PvCurrent2` | `0x0008` | PV input 2 current |
| `Temperature` | `0x0009` | Inverter temperature |
| `RunMode` | `0x000A` | Current operating mode |
| `Powerdc1` | `0x000B` | PV input 1 power |
| `Powerdc2` | `0x000C` | PV input 2 power |
| `feedin_power` | `0x0016` | Power exported to the grid |
| `Etoday` | `0x001C` | Today's grid-connected energy |
| `Etotal` | `0x001E` | Total grid-connected energy |
| `EPS_Volt` | `0x002A` | EPS output voltage |
| `EPS_Current` | `0x002B` | EPS output current |
| `EPS_Power` | `0x002C` | EPS output power |
| `PowerLoad` | `0x0032` | Home load power |
| `PvEnergyTotal` | `0x0038` | Total PV energy |
| `chargerNum` | `0x0045` | Number of chargers |
| `BatVoltage_Charge1` | `0x0046` | Charger 1 battery voltage |
| `BatCurrent_Charge1` | `0x0047` | Charger 1 battery current |
| `Batpower_Charge1` | `0x0048` | Charger 1 battery power |
| `TemperatureBoard_Charge1` | `0x0049` | Charger 1 board temperature |
| `TemperatureBat_Charge1` | `0x004A` | Charger 1 battery temperature |
| `TemperatureTransformer_Charge1` | `0x004B` | Charger 1 DAB transformer temperature |

Use `./inverter.py --list` for the complete register list, including charger 2–4 registers, fault messages, firmware values, energy counters, and protection parameters.



