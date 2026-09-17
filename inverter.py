#!/usr/bin/env python3
"""ESC3-5K/ESC3-5KW-DS inverter Modbus/TCP utility.
By Emile 2026 (www.sixbynine.no)

Examples:
  ./inverter.py -r SeriesNumber -h 192.168.0.1
  ./inverter.py -r GridVoltage -h 192.168.0.1
  ./inverter.py -w Allow_Grid_Charge 3 -p 1919 -h 192.168.0.1
  ./inverter.py --list
  ./inverter.py --list -j

The inverter uses standard Modbus/TCP, Unit ID 1, port 502, and zero-based
register offsets as described ESC3-5KW-DS documentation.
"""

import argparse
import json
import logging
import socket
import struct
import sys
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class Register:
    name: str
    function: int                 # 3 = holding, 4 = input
    address: int
    length: int = 1
    data_type: str = "uint16"
    scale: float = 1.0
    unit: str = ""
    writable: bool = False
    description: str = ""


REGISTERS: Dict[str, Register] = {}


def add(name, function, address, length=1, data_type="uint16", scale=1.0,
        unit="", writable=False, description=""):
    REGISTERS[name] = Register(name, function, address, length, data_type,
                               scale, unit, writable, description)


# Holding-register table (0x03). These are the named registers from the sheet.
HOLDING = [
    ("AllowUnlock", 0x00, 1, "uint16", 1, "", True, "Unlock writes; (factory default is 1919)"),
    ("SeriesNumber", 0x01, 8, "text", 1, "", True, "16-character serial number"),
    ("FactoryName", 0x09, 8, "text", 1, "", False, "16-character factory name"),
    ("ModuleName", 0x11, 8, "text", 1, "", False, "16-character module name"),
    ("MyAddress", 0x1A, 1, "uint16", 1, "", True, "Reserved machine address"),
    ("Language", 0x1B, 1, "uint16", 1, "", True, "0=English, 1=German"),
    ("IP Method", 0x1C, 1, "uint16", 1, "", True, "0=DHCP, 1=Static"),
    ("Allow_Grid_Charge", 0xBA, 1, "uint16", 1, "", True, "Allowed charge from grid. 0=Forbidden, 1=Allow period 1, 2=Allow period 2, 3=Allow always"),
    ("Machine_Type", 0x19, 1, "uint16", 1, "", False, "Machine type"),
    ("Machine switch", 0x1D, 1, "uint16", 1, "", False, "Software/hardware switch"),
    ("Safety", 0x1F, 1, "uint16", 1, "", True, "Grid safety profile"),
    ("PvConnectionMode", 0x20, 1, "uint16", 1, "", True, "Solar input mode. 0=No solar, 1=Comm(Two strings in parallel, 2=Multi(Two strings in parallel independent)"),
    ("VpvStart", 0x21, 1, "uint16", 10, "V", True, "PV start voltage"),
    ("TimeStart", 0x22, 1, "uint16", 1, "s", True, "PV start delay"),
    ("VpvHighStop", 0x23, 1, "uint16", 10, "V", True, "PV high voltage threshold"),
    ("VpvLowStop", 0x24, 1, "uint16", 10, "V", True, "PV low voltage threshold"),
    ("VacMinProtect", 0x25, 1, "uint16", 10, "V", True, "Minimum grid voltage"),
    ("VacMaxProtect", 0x26, 1, "uint16", 10, "V", True, "Maximum grid voltage"),
    ("FacMinProtect", 0x27, 1, "uint16", 100, "Hz", True, "Minimum grid frequency"),
    ("FacMaxProtect", 0x28, 1, "uint16", 100, "Hz", True, "Maximum grid frequency"),
    ("VacMinSlowProtect", 0x29, 1, "uint16", 10, "V", True, "Slow undervoltage threshold"),
    ("VacMaxSlowProtect", 0x2A, 1, "uint16", 10, "V", True, "Slow overvoltage threshold"),
    ("FacMinSlowProtect", 0x2B, 1, "uint16", 100, "Hz", True, "Slow underfrequency threshold"),
    ("FacMaxSlowProtect", 0x2C, 1, "uint16", 100, "Hz", True, "Slow overfrequency threshold"),
    ("Grid10MinAvgProtect", 0x2D, 1, "uint16", 10, "V", True, "10-minute overvoltage threshold"),
    ("PowerLimitsPercent", 0x3A, 1, "uint16", 1, "%", True, "Output power limit"),
    ("FreqSetPoint", 0x3B, 1, "uint16", 100, "Hz", True, "Frequency droop set point"),
    ("FreqDroopRate", 0x3C, 1, "uint16", 100, "", True, "Frequency droop rate"),
    ("PowerfactorMode", 0x3E, 1, "uint16", 1, "", True, "Power factor mode"),
    ("PowerfactorData", 0x3F, 1, "uint16", 100, "", True, "Power factor"),
    ("wExt_SetChargerPower", 0x57, 1, "int16", 1, "W", True, "External charger power."),
    ("wExt_SetSolarPower", 0x58, 1, "int16", 1, "W", True, "External solar power"),
    ("PowerManagerConfigData", 0x59, 80, "uint16", 1, "", True, "Power manager configuration"),
    ("PowerManagerEnable", 0xA9, 1, "uint16", 1, "", True, "Power manager enable"),
    ("SolarChargerUseMode", 0xB9, 1, "uint16", 1, "", True, "Operating mode"),
    ("Password", 0x1E, 1, "uint16", 1, "", False, "Password/status register"),
    ("Export control factory limit", 0xBB, 1, "uint16", 1, "W", True, "Factory export limit"),
    ("Export control user limit", 0xBC, 1, "uint16", 1, "W", True, "User export limit"),
    ("EPS_Mute", 0xBD, 1, "uint16", 1, "", True, "EPS mute"),
    ("EPS Frequency", 0xBE, 1, "uint16", 1, "", True, "0 50Hz, 1 60Hz"),
    ("BatteryNum", 0xD5, 1, "uint16", 1, "", False, "Battery count"),
    ("Battery1Type", 0xD7, 1, "uint16", 1, "", True, "0 lead acid, 1 lithium"),
    ("Battery1_ChargeCutVoltage", 0xD8, 1, "uint16", 100, "V", True, "Battery charge cutoff"),
    ("Battery1_DischargeCutVoltage", 0xD9, 1, "uint16", 100, "V", True, "Battery discharge cutoff"),
    ("Battery1_ChargeMaxCurrent", 0xDA, 1, "uint16", 100, "A", True, "Maximum charge current"),
    ("Battery1_DischargeMaxCurrent", 0xDB, 1, "uint16", 100, "A", True, "Maximum discharge current"),
    ("wBattery1_healthy", 0xDE, 1, "uint16", 100, "%", False, "Battery health"),
    ("Bat_awaking", 0xE0, 1, "uint16", 1, "", True, "Wake battery"),
    ("wBattery1_VendorCode", 0xE1, 1, "uint16", 1, "", True, "Battery BMS vendor"),
    ("MAC Address", 0x10D, 3, "text", 1, "", True, "MAC address"),
    ("BackUp_GridChargeFlag", 0x110, 1, "uint16", 1, "", True, "Backup grid charge"),
    ("wCTMeterEnableFlg", 0x116, 1, "uint16", 1, "", True, "External CT/meter enable"),
    ("wRemoteChargeSubMode", 0x11C, 1, "uint16", 1, "", True, "Remote charge mode"),
    ("wRemoteChargerPowerSet", 0x11D, 1, "int16", 1, "W", True, "Remote charge/discharge power"),
    ("AllowSolarMaxUse", 0x120, 1, "uint16", 1, "", True, "Allow remaining solar power to grid"),
]
for row in HOLDING:
    add(row[0], 3, row[1], row[2], row[3], row[4], row[5], row[6], row[7])

# Holding-register write-only commands.
for name, addr, desc in [
    ("Inverter_Reset_E2prom", 0x00, "Reset EEPROM"),
    ("Inverter_Clear_History", 0x01, "Clear history"),
    ("Clear overload fault", 0x02, "Write 1 to clear overload fault"),
    ("Reset_Mgr_EE", 0x03, "Manager reset: 1 normal, 2 all configuration"),
]:
    # Keep the unlock register visible, but use a separate name for commands.
    add(name, 3, addr, 1, "uint16", 1, "", True, desc)

# Read-only input-register table (0x04).
INPUTS = [
    ("LockState", 0x00, 1, "uint16", 1, "", "Lock state"),
    ("GridVoltage", 0x01, 1, "uint16", 10, "V", "Grid voltage"),
    ("GridCurrent", 0x02, 1, "int16", 10, "A", "Grid current"),
    ("GridPower", 0x03, 1, "int16", 1, "W", "Grid power"),
    ("GridFrequency", 0x04, 1, "uint16", 100, "Hz", "Grid frequency"),
    ("PvVoltage1", 0x05, 1, "uint16", 10, "V", "PV input 1 voltage"),
    ("PvVoltage2", 0x06, 1, "uint16", 10, "V", "PV input 2 voltage"),
    ("PvCurrent1", 0x07, 1, "uint16", 10, "A", "PV input 1 current"),
    ("PvCurrent2", 0x08, 1, "uint16", 10, "A", "PV input 2 current"),
    ("Temperature", 0x09, 1, "int16", 1, "°C", "Inverter temperature"),
    ("RunMode", 0x0A, 1, "uint16", 1, "", "Operating mode"),
    ("Powerdc1", 0x0B, 1, "uint16", 1, "W", "PV input 1 power"),
    ("Powerdc2", 0x0C, 1, "uint16", 1, "W", "PV input 2 power"),
    ("feedin_power", 0x16, 2, "int32_lsw", 1, "W", "Grid feed-in power"),
    ("feedin_energy", 0x18, 2, "uint32_lsw", 100, "kWh", "Grid feed-in energy"),
    ("consum_energy", 0x1A, 2, "uint32_lsw", 100, "kWh", "Grid consumption energy"),
    ("Etoday", 0x1C, 1, "uint16", 100, "kWh", "Today's generation"),
    ("Etotal", 0x1E, 2, "uint32_lsw", 100, "kWh", "Total generation"),
    ("EPS_Volt", 0x2A, 1, "uint16", 10, "V", "EPS voltage"),
    ("EPS_Current", 0x2B, 1, "uint16", 10, "A", "EPS current"),
    ("EPS_Power", 0x2C, 1, "uint16", 1, "VA", "EPS power"),
    ("EPS_Frequency", 0x2D, 1, "uint16", 100, "Hz", "EPS frequency"),
    ("PowerLoad", 0x32, 1, "uint16", 1, "W", "Home load power"),
    ("EtodayLoad", 0x33, 1, "uint16", 10, "kWh", "Today's home-load energy"),
    ("EtotalLoad", 0x34, 2, "uint32_lsw", 10, "kWh", "Total home-load energy"),
    ("PvEnergyToday", 0x36, 1, "uint16", 10, "kWh", "Today's PV energy"),
    ("PvEnergyTotal", 0x38, 2, "uint32_lsw", 10, "kWh", "Total PV energy"),
    ("wCanCommLost", 0x3A, 1, "uint16", 1, "", "BMS connection state"),
    ("InvFaultMessage1", 0x40, 1, "uint16", 1, "", "Inverter fault word 1"),
    ("InvFaultMessage2", 0x41, 1, "uint16", 1, "", "Inverter fault word 2"),
    ("InvFaultMessage3", 0x42, 1, "uint16", 1, "", "Inverter fault word 3"),
    ("InvFaultMessage4", 0x43, 1, "uint16", 1, "", "Inverter fault word 4"),
    ("Mgr FaultMessage", 0x44, 1, "uint16", 1, "", "Manager fault word"),
    ("chargerNum", 0x45, 1, "uint16", 1, "", "Number of chargers"),
]
for charger in range(1, 5):
    base = {1: 0x46, 2: 0x5C, 3: 0x72, 4: 0x88}[charger]
    INPUTS += [
        (f"BatVoltage_Charge{charger}", base, 1, "int16", 100, "V", "Battery voltage"),
        (f"BatCurrent_Charge{charger}", base+1, 1, "int16", 100, "A", "Battery current"),
        (f"Batpower_Charge{charger}", base+2, 1, "int16", 1, "W", "Battery power"),
        (f"TemperatureBoard_Charge{charger}", base+3, 1, "int16", 1, "°C", "Charger board temperature"),
        (f"TemperatureBat_Charge{charger}", base+4, 1, "int16", 1, "°C", "Battery/cell temperature"),
        (f"TemperatureTransformer_Charge{charger}" if charger == 1 else f"TemperatureBoost_Charge{charger}", base+5, 1, "int16", 1, "°C", "Charger transformer/boost temperature"),
        (f"Capacity_Charge{charger}", base+10, 1, "uint16", 100, "%", "Battery capacity"),
        (f"BMS{charger} warnings", base+14, 1, "uint16", 1, "", "BMS warning word"),
    ]
for row in INPUTS:
    add(row[0], 4, row[1], row[2], row[3], row[4], row[5], False, row[6])


# Case/spacing/underscore-insensitive lookup, while retaining exact display names.
def find_register(name: str) -> Register:
    key = ''.join(c for c in name.lower() if c.isalnum())
    matches = [r for r in REGISTERS.values()
               if ''.join(c for c in r.name.lower() if c.isalnum()) == key]
    if not matches:
        raise KeyError(f"Unknown register: {name}")
    return matches[0]


class ModbusTCP:
    def __init__(self, host: str, port: int, timeout: float, verbose=False):
        self.host, self.port, self.timeout = host, port, timeout
        self.verbose = verbose
        self.sock = None
        self.transaction = 0

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        return self

    def __exit__(self, *_):
        if self.sock:
            self.sock.close()

    def exchange(self, function: int, payload: bytes) -> bytes:
        self.transaction = (self.transaction + 1) & 0xFFFF
        packet = struct.pack(">HHHB", self.transaction, 0, len(payload) + 2, 1)
        packet += bytes([function]) + payload
        if self.verbose:
            logging.info("TX %s", packet.hex(" "))
        self.sock.sendall(packet)
        header = recv_exact(self.sock, 7)
        tid, proto, length, unit = struct.unpack(">HHHB", header)
        if tid != self.transaction or proto != 0 or unit != 1:
            raise RuntimeError("Invalid Modbus/TCP response header")
        body = recv_exact(self.sock, length - 1)
        if self.verbose:
            logging.info("RX %s", (header + body).hex(" "))
        if body[0] & 0x80:
            raise RuntimeError(f"Modbus exception 0x{body[1]:02x}")
        if body[0] != function:
            raise RuntimeError("Unexpected Modbus function code")
        return body[1:]

    def read(self, function: int, address: int, count: int) -> List[int]:
        response = self.exchange(function, struct.pack(">HH", address, count))
        if not response or response[0] != count * 2:
            raise RuntimeError("Invalid register read response")
        return list(struct.unpack(">" + "H" * count, response[1:]))

    def write_single(self, address: int, value: int):
        response = self.exchange(6, struct.pack(">HH", address, value & 0xFFFF))
        if response != struct.pack(">HH", address, value & 0xFFFF):
            raise RuntimeError("Write verification failed")


def recv_exact(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("Connection closed by inverter")
        data += chunk
    return data


def decode(reg: Register, words: List[int]) -> Any:
    if reg.data_type == "text":
        raw = b"".join(struct.pack(">H", w) for w in words)
        return raw.rstrip(b"\x00 ").decode("ascii", errors="replace")
    if reg.data_type == "int16":
        value = struct.unpack(">h", struct.pack(">H", words[0]))[0]
    elif reg.data_type == "int32_lsw":
        value = struct.unpack(">i", struct.pack(">I", words[1] << 16 | words[0]))[0]
    elif reg.data_type == "uint32_lsw":
        value = words[1] << 16 | words[0]
    else:
        value = words[0]
    value = value / reg.scale
    return int(value) if reg.scale == 1 else value


def list_registers(as_json=False):
    rows = []
    for r in sorted(REGISTERS.values(), key=lambda x: (x.function, x.address, x.name.lower())):
        rows.append({"name": r.name, "access": "read/write" if r.writable else "read",
                     "function": f"0x{r.function:02X}", "register": f"0x{r.address:04X}",
                     "length": r.length, "type": r.data_type, "unit": r.unit,
                     "description": r.description})
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    print(f"{'Variable':38} {'Access':11} {'Function':9} {'Register':10} {'Length':6} {'Type':13} Unit  Description")
    print("-" * 125)
    for x in rows:
        print(f"{x['name'][:38]:38} {x['access']:11} {x['function']:9} {x['register']:10} {x['length']:<6} {x['type']:<13} {x['unit']:<5} {x['description']}")


def parse_value(text, reg: Register) -> int:
    if reg.data_type == "text":
        raise ValueError("Text registers require a multiple-register write and are not supported by -w")
    number = float(text)
    raw = round(number * reg.scale)
    if reg.data_type == "int16":
        if not -32768 <= raw <= 32767:
            raise ValueError("Value is outside signed 16-bit range")
    elif not 0 <= raw <= 65535:
        raise ValueError("Value is outside unsigned 16-bit range")
    return raw


def main():
    print("ESC3 Hybrid inverter communication tool.\nBy Emilie (www.sixbynine.no)\nGit repo: https://github.com/ravng/esc3-inverter\n")
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument("-r", metavar="X", help="read register X by variable name")
    parser.add_argument("-w", nargs=2, metavar=("X", "Y"), help="write value Y to register X")
    parser.add_argument("-h", dest="host", metavar="HOST", help="inverter IP address or hostname")
    parser.add_argument("-P", type=int, default=502, metavar="PORT", help="TCP port (default 502)")
    parser.add_argument("-p", dest="pin", type=int, metavar="PIN", help="unlock PIN for writes")
    parser.add_argument("-j", "--json", action="store_true", help="output JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose protocol logging")
    parser.add_argument("-t", type=float, default=5, metavar="SECONDS", help="timeout (default 5)")
    parser.add_argument("--list", action="store_true", help="list all known registers and exit")
    parser.add_argument("--help", action="help", help="show this help message and exit")
    args = parser.parse_args()

    if args.list:
        list_registers(args.json)
        return 0
    if bool(args.r) == bool(args.w):
        parser.error("specify exactly one of -r or -w")
    if not args.host:
        parser.error("-h HOST is required")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    try:
        name = args.r if args.r else args.w[0]
        reg = find_register(name)
        if args.r:
            with ModbusTCP(args.host, args.P, args.t, args.verbose) as client:
                value = decode(reg, client.read(reg.function, reg.address, reg.length))
            result = {reg.name: value}
        else:
            if not reg.writable or reg.function != 3:
                raise ValueError(f"Register {reg.name} is not a writable holding register")
            if args.pin is None:
                raise ValueError("-p PIN is required for writes")
            value = parse_value(args.w[1], reg)
            with ModbusTCP(args.host, args.P, args.t, args.verbose) as client:
                client.write_single(0, args.pin)
                client.write_single(reg.address, value)
            result = {reg.name: "written", "value": value / reg.scale if reg.scale != 1 else value}
        print(json.dumps(result, ensure_ascii=False) if args.json else "\n".join(f"{k}: {v}" for k, v in result.items()))
        return 0
    except (OSError, KeyError, ValueError, RuntimeError, ConnectionError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
