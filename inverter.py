#!/usr/bin/env python3
""""""ESC3-5K/ESC3-5KW-DS inverter Modbus/TCP utility.
By Emile 2026 (www.sixbynine.no)

The inverter uses standard Modbus/TCP, Unit ID 1, port 502, and zero-based
register offsets as described ESC3-5KW-DS documentation.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import struct
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_PORT = 502
DEFAULT_TIMEOUT = 5.0
UNIT_ID = 1
UNLOCK_REGISTER = 0x0000
DEFAULT_PIN = 1919


@dataclass(frozen=True)
class Register:
    name: str
    address: int
    function: int                 # 0x03 or 0x04
    length: int = 1
    data_type: str = "uint16"     # uint16, int16, uint32, int32, text
    scale: float = 1.0
    unit: str = ""
    writable: bool = False
    description: str = ""


REGISTERS: dict[str, Register] = {}


def add(name: str, address: int, function: int, **kwargs: Any) -> None:
    REGISTERS[name] = Register(name, address, function, **kwargs)


def add_holding(name: str, address: int, *, writable: bool = False,
                length: int = 1, data_type: str = "uint16", scale: float = 1.0,
                unit: str = "", description: str = "") -> None:
    add(name, address, 0x03, writable=writable, length=length,
        data_type=data_type, scale=scale, unit=unit, description=description)


def add_input(name: str, address: int, *, length: int = 1,
              data_type: str = "uint16", scale: float = 1.0,
              unit: str = "", description: str = "") -> None:
    add(name, address, 0x04, length=length, data_type=data_type,
        scale=scale, unit=unit, description=description)


# Holding registers (function 0x03).  Names intentionally contain underscores
# so every register can be selected directly from a shell command.
_holding = [
    ("AllowUnlockCommand", 0x00, True, 1, "uint16", 1, "", "Unlock/write password"),
    ("SeriesNumber", 0x01, True, 8, "text", 1, "", "Inverter serial number"),
    ("FactoryName", 0x09, False, 8, "text", 1, "", "Factory name"),
    ("ModuleName", 0x11, False, 8, "text", 1, "", "Module name"),
    ("Machine_Type", 0x19, False, 1, "uint16", 1, "", "Machine type"),
    ("MyAddress", 0x1A, True, 1, "uint16", 1, "", "Machine address"),
    ("Language", 0x1B, True, 1, "uint16", 1, "0 English, 1 German"),
    ("IP_Method", 0x1C, True, 1, "uint16", 1, "", "0 DHCP, 1 manual"),
    ("Machine_switch", 0x1D, False, 1, "uint16", 1, "", "Software/hardware switch"),
    ("Password", 0x1E, False, 1, "uint16", 1, "", "Password state"),
    ("Safety", 0x1F, True, 1, "uint16", 1, "", "Grid safety profile"),
    ("PvConnectionMode", 0x20, True, 1, "uint16", 1, "", "PV input mode"),
    ("VpvStart", 0x21, True, 1, "uint16", 0.1, "V", "PV start voltage"),
    ("TimeStart", 0x22, True, 1, "uint16", 1, "s", "Start delay"),
    ("VpvHighStop", 0x23, True, 1, "uint16", 0.1, "V", "PV high voltage stop"),
    ("VpvLowStop", 0x24, True, 1, "uint16", 0.1, "V", "PV low voltage stop"),
    ("VacMinProtect", 0x25, True, 1, "uint16", 0.1, "V", "Minimum grid voltage"),
    ("VacMaxProtect", 0x26, True, 1, "uint16", 0.1, "V", "Maximum grid voltage"),
    ("FacMinProtect", 0x27, True, 1, "uint16", 0.01, "Hz", "Minimum grid frequency"),
    ("FacMaxProtect", 0x28, True, 1, "uint16", 0.01, "Hz", "Maximum grid frequency"),
    ("VacMinSlowProtect", 0x29, True, 1, "uint16", 0.1, "V", "Slow undervoltage limit"),
    ("VacMaxSlowProtect", 0x2A, True, 1, "uint16", 0.1, "V", "Slow overvoltage limit"),
    ("FacMinSlowProtect", 0x2B, True, 1, "uint16", 0.01, "Hz", "Slow underfrequency limit"),
    ("FacMaxSlowProtect", 0x2C, True, 1, "uint16", 0.01, "Hz", "Slow overfrequency limit"),
    ("Grid10MinAvgProtect", 0x2D, True, 1, "uint16", 0.1, "V", "10-minute voltage limit"),
    ("PowerLimitsPercent", 0x3A, True, 1, "uint16", 1, "%", "Output power limit"),
    ("FreqSetPoint", 0x3B, True, 1, "uint16", 0.01, "Hz", "Frequency set point"),
    ("FreqDroopRate", 0x3C, True, 1, "uint16", 0.01, "", "Frequency droop rate"),
    ("PowerfactorMode", 0x3E, True),
    ("PowerfactorData", 0x3F, True, 1, "uint16", 0.01, "", "Power factor"),
    ("UpperLimit", 0x40, True, 1, "uint16", 0.01),
    ("LowerLimit", 0x41, True, 1, "uint16", 0.01),
    ("PowerLow", 0x42, True, 1, "uint16", 0.01),
    ("PowerUp", 0x43, True, 1, "uint16", 0.01),
    ("QuVrateLow", 0x45, True, 1, "uint16", 0.01),
    ("PfLockInPoint", 0x46, True),
    ("PfLockOutPoint", 0x47, True),
    ("SelfTestStep", 0x48, True),
    ("wExt_SetChargerPower", 0x57, True, 1, "int16", 1, "W"),
    ("wExt_SetInverterPower", 0x58, True, 1, "int16", 1, "W"),
    ("PowerManagerConfigData", 0x59, True, 80),
    ("PowerManagerEnable", 0xA9, True),
    ("FirmwareVersion_InverterMaster", 0xAA),
    ("FirmwareVersion_InverterSlave", 0xAB),
    ("FirmwareVersion_Charger1", 0xAC),
    ("FirmwareVersion_Charger2", 0xAD),
    ("FirmwareVersion_Charger3", 0xAE),
    ("FirmwareVersion_Charger4", 0xAF),
    ("FirmwareVersion_Manager", 0xB0),
    ("wFirmwareVersion_Protocol", 0xB1),
    ("ItalySelftestStart", 0xB2, True),
    ("RTC_Seconds", 0xB3), ("RTC_Minutes", 0xB4), ("RTC_Hours", 0xB5),
    ("RTC_Days", 0xB6), ("RTC_Months", 0xB7), ("RTC_Years", 0xB8),
    ("SolarChargerUseMode", 0xB9, True),
    ("Allow_Grid_Charge", 0xBA, True),
    ("Export_control_factory_limit", 0xBB, True),
    ("Export_control_user_limit", 0xBC, True),
    ("EPS_Mute", 0xBD, True), ("EPS_Frequency", 0xBE, True),
    ("frqprotectrestrictive", 0xCF, True),
    ("BatteryNum", 0xD5), ("Battery1_MinCapcity", 0xD6),
    ("Battery1Type", 0xD7, True),
    ("Battery1_ChargeCutVoltage", 0xD8, True, 1, "uint16", 0.01),
    ("Battery1_DischargeCutVoltage", 0xD9, True, 1, "uint16", 0.01),
    ("Battery1_ChargeMaxCurrent", 0xDA, True, 1, "uint16", 0.01),
    ("Battery1_DischargeMaxCurrent", 0xDB, True, 1, "uint16", 0.01),
    ("wBattery1_absorpt_voltage", 0xDC, True, 1, "uint16", 0.01),
    ("wBattery1_wEpsDischargeVolt", 0xDD, True, 1, "uint16", 0.01),
    ("Battery_Health", 0xDE, False, 1, "uint16", 0.01, "%"),
    ("Charge1_MinCapcity", 0xDF, True, 1, "uint16", 0.01),
    ("Bat_awaking", 0xE0, True), ("wBattery1_VendorCode", 0xE1, True),
    ("MAC_Address", 0x10D, True, 3, "text"),
    ("BackUp_GridChargeFlag", 0x110, True),
    ("wBackUp_Chr_Start_H", 0x111, True), ("wBackUp_Chr_Start_M", 0x112, True),
    ("wBackUp_Chr_End_H", 0x113, True), ("wBackUp_Chr_End_M", 0x114, True),
    ("wPFValue", 0x115, True), ("wCTMeterEnableFlg", 0x116, True),
    ("wFreqOverStart", 0x117, True, 1, "uint16", 0.01, "Hz"),
    ("wFreqOverEnd", 0x118, True, 1, "uint16", 0.01, "Hz"),
    ("wFreqUnderStart", 0x119, True, 1, "uint16", 0.01, "Hz"),
    ("wFreqUnderEnd", 0x11A, True, 1, "uint16", 0.01, "Hz"),
    ("wFFR_SOC_Reserved", 0x11B, True, 1, "uint16", 0.01),
    ("wRemoteChargeSubMode", 0x11C, True),
    ("wRemoteChargerPowerSet", 0x11D, True, 1, "int16", 1, "W"),
    ("AllowSolarMaxUse", 0x120, True),
]

for item in _holding:
    # Defaults allow compact entries such as (name, address).
    name, address, *rest = item
    writable = bool(rest[0]) if rest else False
    args = rest[1:] if rest else []
    length = args[0] if len(args) > 0 else 1
    dtype = args[1] if len(args) > 1 else "uint16"
    scale = args[2] if len(args) > 2 else 1.0
    unit = args[3] if len(args) > 3 else ""
    desc = args[4] if len(args) > 4 else ""
    add_holding(name, address, writable=writable, length=length,
                data_type=dtype, scale=scale, unit=unit, description=desc)


# Input registers (function 0x04). These are zero-based offsets; do not add
# 0x300. This is the important distinction from the old register table.
_input = [
    ("LockState", 0x00, "uint16", 1, ""),
    ("GridVoltage", 0x01, "uint16", 0.1, "V"),
    ("GridCurrent", 0x02, "int16", 0.1, "A"),
    ("GridPower", 0x03, "int16", 1, "W"),
    ("GridFrequency", 0x04, "uint16", 0.01, "Hz"),
    ("PvVoltage1", 0x05, "uint16", 0.1, "V"), ("PvVoltage2", 0x06, "uint16", 0.1, "V"),
    ("PvCurrent1", 0x07, "uint16", 0.1, "A"), ("PvCurrent2", 0x08, "uint16", 0.1, "A"),
    ("Temperature", 0x09, "int16", 1, "°C"), ("RunMode", 0x0A, "uint16", 1, ""),
    ("Powerdc1", 0x0B, "uint16", 1, "W"), ("Powerdc2", 0x0C, "uint16", 1, "W"),
    ("TemperFaultValue", 0x0D, "int16", 1, "°C"), ("Pv1VoltFaultValue", 0x0E, "uint16", 0.1, "V"),
    ("Pv2VoltFaultValue", 0x0F, "uint16", 0.1, "V"), ("GfciFaultValue", 0x10, "uint16", 1, "mA"),
    ("GridVoltFaultValue", 0x11, "uint16", 0.1, "V"), ("GridFreqFaultValueT", 0x12, "uint16", 0.01, "Hz"),
    ("DciFaultValue", 0x13, "uint16", 1, "mA"), ("TimeCountDown", 0x14, "uint16", 1, "s"),
    ("feedin_power", 0x16, "int32", 1, "W"), ("feedin_energy", 0x18, "uint32", 0.01, "kWh"),
    ("consum_energy", 0x1A, "uint32", 0.01, "kWh"), ("Etoday", 0x1C, "uint16", 0.01, "kWh"),
    ("Etotal", 0x1E, "uint32", 0.01, "kWh"), ("feedin_power2", 0x20, "int32", 1, "W"),
    ("feedin_energy2", 0x22, "uint32", 0.01, "kWh"), ("consum_energy2", 0x24, "uint32", 0.01, "kWh"),
    ("Etoday2", 0x26, "uint16", 0.01, "kWh"), ("Etotal2", 0x28, "uint32", 0.01, "kWh"),
    ("EPS_Volt", 0x2A, "uint16", 0.1, "V"), ("EPS_Current", 0x2B, "uint16", 0.1, "A"),
    ("EPS_Power", 0x2C, "uint16", 1, "VA"), ("EPS_Frequency", 0x2D, "uint16", 0.01, "Hz"),
    ("EtodayEPS", 0x2E, "uint16", 0.1, "kWh"), ("EtotalEPS", 0x30, "uint32", 0.1, "kWh"),
    ("PowerLoad", 0x32, "uint16", 1, "W"), ("EtodayLoad", 0x33, "uint16", 0.1, "kWh"),
    ("EtotalLoad", 0x34, "uint32", 0.1, "kWh"), ("PvEnergyToday", 0x36, "uint16", 0.1, "kWh"),
    ("PvEnergyTotal", 0x38, "uint32", 0.1, "kWh"), ("wCanCommLost", 0x3A, "uint16", 1, ""),
    ("InvFaultMessage1", 0x40, "uint16", 1, ""), ("InvFaultMessage2", 0x41, "uint16", 1, ""),
    ("InvFaultMessage3", 0x42, "uint16", 1, ""), ("InvFaultMessage4", 0x43, "uint16", 1, ""),
    ("Mgr_FaultMessage", 0x44, "uint16", 1, ""), ("chargerNum", 0x45, "uint16", 1, ""),
]
for name, addr, dtype, scale, unit in _input:
    add_input(name, addr, data_type=dtype, scale=scale, unit=unit)

# Charger blocks in the V008 input table. Charge 1 has the newer transformer
# temperature name at 0x4B; the original table calls it TemperatureBoost.
for charger, base in enumerate((0x46, 0x5C, 0x72, 0x88), 1):
    suffix = f"_Charge{charger}"
    fields = [
        (f"BatVoltage{suffix}", 0, "int16", 0.01, "V"),
        (f"BatCurrent{suffix}", 1, "int16", 0.01, "A"),
        (f"Batpower{suffix}", 2, "int16", 1, "W"),
        (f"TemperatureBoard{suffix}", 3, "int16", 1, "°C"),
        (f"TemperatureBat{suffix}", 4, "int16", 1, "°C"),
        (f"TemperatureTransformer{suffix}", 5, "int16", 1, "°C"),
        (f"TemperatureBoost{suffix}", 5, "int16", 1, "°C"),
        (f"BatVoltageFaultValue{suffix}", 6, "uint16", 0.1, "V"),
        (f"BatCurrentFaultValue{suffix}", 7, "int16", 0.01, "A"),
        (f"BoostVoltageFaultValue{suffix}", 8, "uint16", 0.1, "V"),
        (f"BoostCurrentFaultValue{suffix}", 9, "int16", 0.01, "A"),
        (f"Capacity{suffix}", 10, "uint16", 0.01, "%"),
        (f"OutputEnergy{suffix}", 12, "uint32", 0.1, "kWh"),
        (f"BMS{charger}_warnings", 14, "uint16", 1, ""),
        (f"BMS{charger}_warnings_back", 15, "uint16", 1, ""),
    ]
    for name, offset, dtype, scale, unit in fields:
        if name in REGISTERS:
            continue
        add_input(name, base + offset, data_type=dtype, length=2 if dtype == "uint32" else 1,
                  scale=scale, unit=unit)

# Compatibility aliases accepted by -r/-w.
ALIASES = {
    "Allow_GridCharge": "Allow_Grid_Charge",
    "BatteryHealth": "Battery_Health",
    "IP Method": "IP_Method",
    "IPMethod": "IP_Method",
    "MAC": "MAC_Address",
}


def resolve(name: str) -> Register:
    name = name.strip()
    name = ALIASES.get(name, name)
    if name not in REGISTERS:
        choices = ", ".join(sorted(REGISTERS))
        raise ValueError(f"Unknown register '{name}'. Use --list to see known registers.\nKnown: {choices}")
    return REGISTERS[name]


def decode_words(reg: Register, words: list[int]) -> Any:
    if reg.data_type == "text":
        raw = b"".join(struct.pack(">H", word) for word in words)
        return raw.rstrip(b"\x00 \xff").decode("ascii", errors="replace")
    if reg.data_type == "uint16":
        value: int = words[0]
    elif reg.data_type == "int16":
        value = struct.unpack(">h", struct.pack(">H", words[0]))[0]
    elif reg.data_type in ("uint32", "int32"):
        # The protocol documents multi-register values as low word first.
        raw = struct.pack(">HH", words[1], words[0])
        value = struct.unpack(">I" if reg.data_type == "uint32" else ">i", raw)[0]
    else:
        raise ValueError(f"Unsupported data type: {reg.data_type}")
    value *= reg.scale
    return int(value) if reg.scale == 1 else round(value, 6)


class ModbusTCP:
    def __init__(self, host: str, port: int, timeout: float, verbose: bool = False):
        self.host, self.port, self.timeout, self.verbose = host, port, timeout, verbose
        self.sock: socket.socket | None = None
        self.transaction = 0

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        return self

    def __exit__(self, *_):
        if self.sock:
            self.sock.close()

    def exchange(self, function: int, payload: bytes) -> bytes:
        if not self.sock:
            raise RuntimeError("Not connected")
        self.transaction = (self.transaction + 1) & 0xFFFF
        pdu = bytes([UNIT_ID, function]) + payload
        frame = struct.pack(">HHH", self.transaction, 0, len(pdu)) + pdu
        if self.verbose:
            print(">> " + frame.hex(" "), file=sys.stderr)
        self.sock.sendall(frame)
        header = self._recv_exact(7)
        tid, proto, length, unit = struct.unpack(">HHHB", header)
        if tid != self.transaction or proto != 0 or unit != UNIT_ID:
            raise RuntimeError("Invalid Modbus/TCP response header")
        body = self._recv_exact(length - 1)
        response = header + body
        if self.verbose:
            print("<< " + response.hex(" "), file=sys.stderr)
        if body[0] & 0x80:
            raise RuntimeError(f"Modbus exception 0x{body[1]:02x}")
        return body[1:]

    def _recv_exact(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))  # type: ignore[union-attr]
            if not chunk:
                raise ConnectionError("Connection closed by inverter")
            data += chunk
        return data

    def read(self, reg: Register) -> Any:
        response = self.exchange(reg.function, struct.pack(">HH", reg.address, reg.length))
        if response[0] != reg.length * 2:
            raise RuntimeError(f"Unexpected byte count for {reg.name}")
        words = list(struct.unpack(">" + "H" * reg.length, response[1:]))
        return decode_words(reg, words)

    def write(self, reg: Register, value: int) -> None:
        if not reg.writable or reg.function != 0x03 or reg.length != 1:
            raise ValueError(f"Register '{reg.name}' is not a writable single holding register")
        if not 0 <= value <= 0xFFFF:
            raise ValueError("Write value must be an unsigned 16-bit integer")
        self.exchange(0x06, struct.pack(">HH", reg.address, value))

    def unlock(self, pin: int) -> None:
        self.exchange(0x06, struct.pack(">HH", UNLOCK_REGISTER, pin))


def list_registers(as_json: bool) -> None:
    rows = []
    for reg in sorted(REGISTERS.values(), key=lambda r: (r.function, r.address, r.name)):
        rows.append({"name": reg.name, "access": "read/write" if reg.writable else "read",
                     "function": f"0x{reg.function:02X}", "address": f"0x{reg.address:04X}",
                     "length": reg.length, "type": reg.data_type, "scale": reg.scale,
                     "unit": reg.unit, "description": reg.description})
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{'Name':<38} {'Access':<11} {'Function':<8} {'Address':<8} {'Len':<4} {'Type':<8} Unit")
    print("-" * 100)
    for row in rows:
        print(f"{row['name']:<38} {row['access']:<11} {row['function']:<8} {row['address']:<8} "
              f"{row['length']:<4} {row['type']:<8} {row['unit']}")


def main() -> int:
    print("ESC3 Hybrid inverter communication tool.\nBy Emilie (www.sixbynine.no)\nGit repo: https://github.com/ravng/esc3-inverter\n")
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument("--help", action="help", help="Show this help message and exit")
    parser.add_argument("-r", metavar="X", help="Read register name(s), comma separated")
    parser.add_argument("-w", nargs=2, metavar=("X", "Y"), help="Write value Y to register X")
    parser.add_argument("-h", dest="host", help="Inverter IP address or hostname")
    parser.add_argument("-P", type=int, default=DEFAULT_PORT, help="TCP port (default: 502)")
    parser.add_argument("-p", type=int, default=None, help="Unlock PIN")
    parser.add_argument("-j", "--json", action="store_true", help="Output JSON")
    parser.add_argument("--list", action="store_true", help="List all known registers and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show Modbus frames")
    parser.add_argument("-t", type=float, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    args = parser.parse_args()

    if args.list:
        list_registers(args.json)
        return 0
    if not args.host:
        parser.error("-h HOST is required unless --list is used")
    if bool(args.r) == bool(args.w):
        parser.error("Specify exactly one of -r or -w")

    try:
        with ModbusTCP(args.host, args.P, args.t, args.verbose) as client:
            if args.r:
                names = [n.strip() for n in args.r.split(",") if n.strip()]
                result: dict[str, Any] = {}
                for requested in names:
                    reg = resolve(requested)
                    result[requested] = client.read(reg)
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    for name, value in result.items():
                        print(f"{name}: {value}")
            else:
                requested, raw_value = args.w
                reg = resolve(requested)
                value = int(raw_value, 0)
                client.unlock(args.p if args.p is not None else DEFAULT_PIN)
                client.write(reg, value)
                result = {requested: value}
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(f"{requested}: {value}")
        return 0
    except (OSError, ValueError, RuntimeError, ConnectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
