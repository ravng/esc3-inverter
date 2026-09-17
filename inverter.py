#!/usr/bin/env python3
"""ESC3-5K/ESC3-5KW-DS inverter Modbus/TCP utility, By Emile (www.sixbynine.no). GitHub: https://github.com/ravng/esc3-inverter"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_PORT = 502
DEFAULT_TIMEOUT = 5.0
UNIT_ID = 1
DEFAULT_PIN = 1919


@dataclass(frozen=True)
class Register:
    name: str
    address: int
    function: int
    length: int = 1
    data_type: str = "uint16"
    scale: float = 1.0
    unit: str = ""
    writable: bool = False
    description: str = ""


REGISTERS: dict[str, Register] = {}


def add(name: str, address: int, function: int = 0x03, **kwargs: Any) -> None:
    REGISTERS[name] = Register(name, address, function, **kwargs)


def h(name: str, address: int, writable: bool = False, **kwargs: Any) -> None:
    add(name, address, 0x03, writable=writable, **kwargs)


def i(name: str, address: int, **kwargs: Any) -> None:
    add(name, address, 0x04, **kwargs)


# Holding registers.  Values are raw register values; scaled values are used
# when reading only.  Int16 registers are specially handled when writing.
_holding = {
    "AllowUnlockCommand": (0x00, True), "SeriesNumber": (0x01, True),
    "FactoryName": (0x09, False), "ModuleName": (0x11, False),
    "Machine_Type": (0x19, False), "MyAddress": (0x1A, True),
    "Language": (0x1B, True), "IP_Method": (0x1C, True),
    "Machine_switch": (0x1D, False), "Password": (0x1E, False),
    "Safety": (0x1F, True), "PvConnectionMode": (0x20, True),
    "VpvStart": (0x21, True), "TimeStart": (0x22, True),
    "VpvHighStop": (0x23, True), "VpvLowStop": (0x24, True),
    "VacMinProtect": (0x25, True), "VacMaxProtect": (0x26, True),
    "FacMinProtect": (0x27, True), "FacMaxProtect": (0x28, True),
    "VacMinSlowProtect": (0x29, True), "VacMaxSlowProtect": (0x2A, True),
    "FacMinSlowProtect": (0x2B, True), "FacMaxSlowProtect": (0x2C, True),
    "Grid10MinAvgProtect": (0x2D, True), "PowerLimitsPercent": (0x3A, True),
    "FreqSetPoint": (0x3B, True), "FreqDroopRate": (0x3C, True),
    "PowerfactorMode": (0x3E, True), "PowerfactorData": (0x3F, True),
    "UpperLimit": (0x40, True), "LowerLimit": (0x41, True),
    "PowerLow": (0x42, True), "PowerUp": (0x43, True),
    "QuVrateLow": (0x45, True), "PfLockInPoint": (0x46, True),
    "PfLockOutPoint": (0x47, True), "SelfTestStep": (0x48, True),
    "wExt_SetChargerPower": (0x57, True), "wExt_SetInverterPower": (0x58, True),
    "PowerManagerEnable": (0xA9, True), "FirmwareVersion_InverterMaster": (0xAA, False),
    "FirmwareVersion_InverterSlave": (0xAB, False), "FirmwareVersion_Charger1": (0xAC, False),
    "FirmwareVersion_Charger2": (0xAD, False), "FirmwareVersion_Charger3": (0xAE, False),
    "FirmwareVersion_Charger4": (0xAF, False), "FirmwareVersion_Manager": (0xB0, False),
    "wFirmwareVersion_Protocol": (0xB1, False), "ItalySelftestStart": (0xB2, True),
    "RTC_Seconds": (0xB3, False), "RTC_Minutes": (0xB4, False),
    "RTC_Hours": (0xB5, False), "RTC_Days": (0xB6, False),
    "RTC_Months": (0xB7, False), "RTC_Years": (0xB8, False),
    "SolarChargerUseMode": (0xB9, True), "Allow_Grid_Charge": (0xBA, True),
    "Export_control_factory_limit": (0xBB, True), "Export_control_user_limit": (0xBC, True),
    "EPS_Mute": (0xBD, True), "EPS_Frequency": (0xBE, True),
    "frqprotectrestrictive": (0xCF, True), "BatteryNum": (0xD5, False),
    "Battery1_MinCapcity": (0xD6, False), "Battery1Type": (0xD7, True),
    "Battery1_ChargeCutVoltage": (0xD8, True), "Battery1_DischargeCutVoltage": (0xD9, True),
    "Battery1_ChargeMaxCurrent": (0xDA, True), "Battery1_DischargeMaxCurrent": (0xDB, True),
    "wBattery1_absorpt_voltage": (0xDC, True), "wBattery1_wEpsDischargeVolt": (0xDD, True),
    "Battery_Health": (0xDE, False), "Charge1_MinCapcity": (0xDF, True),
    "Bat_awaking": (0xE0, True), "wBattery1_VendorCode": (0xE1, True),
    "MAC_Address": (0x10D, True), "BackUp_GridChargeFlag": (0x110, True),
    "wBackUp_Chr_Start_H": (0x111, True), "wBackUp_Chr_Start_M": (0x112, True),
    "wBackUp_Chr_End_H": (0x113, True), "wBackUp_Chr_End_M": (0x114, True),
    "wPFValue": (0x115, True), "wCTMeterEnableFlg": (0x116, True),
    "wFreqOverStart": (0x117, True), "wFreqOverEnd": (0x118, True),
    "wFreqUnderStart": (0x119, True), "wFreqUnderEnd": (0x11A, True),
    "wFFR_SOC_Reserved": (0x11B, True), "wRemoteChargeSubMode": (0x11C, True),
    "wRemoteChargerPowerSet": (0x11D, True), "AllowSolarMaxUse": (0x120, True),
}
for name, (address, writable) in _holding.items():
    dtype = "text" if name in {"SeriesNumber", "FactoryName", "ModuleName", "MAC_Address"} else "uint16"
    length = 8 if name in {"SeriesNumber", "FactoryName", "ModuleName"} else 3 if name == "MAC_Address" else 1
    if name in {"wExt_SetChargerPower", "wExt_SetInverterPower", "wRemoteChargerPowerSet"}:
        dtype = "int16"
    scale = 0.01 if name == "Battery_Health" else 1.0
    h(name, address, writable, length=length, data_type=dtype, scale=scale)

# Function 0x04 input-register offsets are zero-based (not 0x300-based).
_input = [
    ("LockState", 0x00, "uint16", 1, ""), ("GridVoltage", 0x01, "uint16", .1, "V"),
    ("GridCurrent", 0x02, "int16", .1, "A"), ("GridPower", 0x03, "int16", 1, "W"),
    ("GridFrequency", 0x04, "uint16", .01, "Hz"), ("PvVoltage1", 0x05, "uint16", .1, "V"),
    ("PvVoltage2", 0x06, "uint16", .1, "V"), ("PvCurrent1", 0x07, "uint16", .1, "A"),
    ("PvCurrent2", 0x08, "uint16", .1, "A"), ("Temperature", 0x09, "int16", 1, "°C"),
    ("RunMode", 0x0A, "uint16", 1, ""), ("Powerdc1", 0x0B, "uint16", 1, "W"),
    ("Powerdc2", 0x0C, "uint16", 1, "W"), ("TemperFaultValue", 0x0D, "int16", 1, "°C"),
    ("Pv1VoltFaultValue", 0x0E, "uint16", .1, "V"), ("Pv2VoltFaultValue", 0x0F, "uint16", .1, "V"),
    ("GfciFaultValue", 0x10, "uint16", 1, "mA"), ("GridVoltFaultValue", 0x11, "uint16", .1, "V"),
    ("GridFreqFaultValueT", 0x12, "uint16", .01, "Hz"), ("DciFaultValue", 0x13, "uint16", 1, "mA"),
    ("TimeCountDown", 0x14, "uint16", 1, "s"), ("feedin_power", 0x16, "int32", 1, "W"),
    ("feedin_energy", 0x18, "uint32", .01, "kWh"), ("consum_energy", 0x1A, "uint32", .01, "kWh"),
    ("Etoday", 0x1C, "uint16", .01, "kWh"), ("Etotal", 0x1E, "uint32", .01, "kWh"),
    ("EPS_Volt", 0x2A, "uint16", .1, "V"), ("EPS_Current", 0x2B, "uint16", .1, "A"),
    ("EPS_Power", 0x2C, "uint16", 1, "VA"), ("EPS_Frequency", 0x2D, "uint16", .01, "Hz"),
    ("PowerLoad", 0x32, "uint16", 1, "W"), ("PvEnergyToday", 0x36, "uint16", .1, "kWh"),
    ("PvEnergyTotal", 0x38, "uint32", .1, "kWh"), ("wCanCommLost", 0x3A, "uint16", 1, ""),
    ("InvFaultMessage1", 0x40, "uint16", 1, ""), ("InvFaultMessage2", 0x41, "uint16", 1, ""),
    ("InvFaultMessage3", 0x42, "uint16", 1, ""), ("InvFaultMessage4", 0x43, "uint16", 1, ""),
    ("Mgr_FaultMessage", 0x44, "uint16", 1, ""), ("chargerNum", 0x45, "uint16", 1, ""),
]
for name, address, dtype, scale, unit in _input:
    i(name, address, data_type=dtype, scale=scale, unit=unit, length=2 if dtype in {"uint32", "int32"} else 1)
for charger, base in enumerate((0x46, 0x5C, 0x72, 0x88), 1):
    fields = [("BatVoltage", "int16", .01, "V"), ("BatCurrent", "int16", .01, "A"),
              ("Batpower", "int16", 1, "W"), ("TemperatureBoard", "int16", 1, "°C"),
              ("TemperatureBat", "int16", 1, "°C"), ("TemperatureTransformer", "int16", 1, "°C"),
              ("TemperatureBoost", "int16", 1, "°C"), ("BatVoltageFaultValue", "uint16", .1, "V"),
              ("BatCurrentFaultValue", "int16", .01, "A"), ("BoostVoltageFaultValue", "uint16", .1, "V"),
              ("BoostCurrentFaultValue", "int16", .01, "A"), ("Capacity", "uint16", .01, "%")]
    for offset, (prefix, dtype, scale, unit) in enumerate(fields):
        i(f"{prefix}_Charge{charger}", base + offset, data_type=dtype, scale=scale, unit=unit)

ALIASES = {"Allow_GridCharge": "Allow_Grid_Charge", "BatteryHealth": "Battery_Health",
           "IP Method": "IP_Method", "IPMethod": "IP_Method", "MAC": "MAC_Address"}


def resolve(name: str) -> Register:
    name = ALIASES.get(name.strip(), name.strip())
    if name not in REGISTERS:
        raise ValueError(f"Unknown register '{name}'. Use --list to see known registers.")
    return REGISTERS[name]


def decode(reg: Register, words: list[int]) -> Any:
    if reg.data_type == "text":
        raw = b"".join(struct.pack(">H", x) for x in words)
        return raw.rstrip(b"\0 \xff").decode("ascii", errors="replace")
    if reg.data_type == "uint16": value = words[0]
    elif reg.data_type == "int16": value = struct.unpack(">h", struct.pack(">H", words[0]))[0]
    elif reg.data_type in {"uint32", "int32"}:
        raw = struct.pack(">HH", words[1], words[0])
        value = struct.unpack(">I" if reg.data_type == "uint32" else ">i", raw)[0]
    else: raise ValueError(f"Unsupported data type: {reg.data_type}")
    value *= reg.scale
    return int(value) if reg.scale == 1 else round(value, 6)


class ModbusTCP:
    def __init__(self, host: str, port: int, timeout: float, verbose: bool = False):
        self.host, self.port, self.timeout, self.verbose = host, port, timeout, verbose
        self.sock: socket.socket | None = None
        self.transaction = 0
    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout); self.sock.settimeout(self.timeout); return self
    def __exit__(self, *_):
        if self.sock: self.sock.close()
    def exchange(self, function: int, payload: bytes) -> bytes:
        self.transaction = (self.transaction + 1) & 0xFFFF
        pdu = bytes([UNIT_ID, function]) + payload
        frame = struct.pack(">HHH", self.transaction, 0, len(pdu)) + pdu
        if self.verbose: print(">> " + frame.hex(" "), file=sys.stderr)
        self.sock.sendall(frame)  # type: ignore[union-attr]
        header = self._recv(7); tid, proto, length, unit = struct.unpack(">HHHB", header)
        body = self._recv(length - 1)
        if self.verbose: print("<< " + (header + body).hex(" "), file=sys.stderr)
        if tid != self.transaction or proto != 0 or unit != UNIT_ID: raise RuntimeError("Invalid response header")
        if body[0] & 0x80: raise RuntimeError(f"Modbus exception 0x{body[1]:02x}")
        return body[1:]
    def _recv(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            part = self.sock.recv(count - len(data))  # type: ignore[union-attr]
            if not part: raise ConnectionError("Connection closed by inverter")
            data += part
        return data
    def read(self, reg: Register) -> Any:
        response = self.exchange(reg.function, struct.pack(">HH", reg.address, reg.length))
        if response[0] != reg.length * 2: raise RuntimeError(f"Unexpected byte count for {reg.name}")
        return decode(reg, list(struct.unpack(">" + "H" * reg.length, response[1:])))
    def unlock(self, pin: int) -> None:
        if not 0 <= pin <= 0xFFFF: raise ValueError("PIN must be 0..65535")
        self.exchange(0x06, struct.pack(">HH", 0, pin))
    def write(self, reg: Register, value: int) -> None:
        if not reg.writable or reg.function != 0x03 or reg.length != 1: raise ValueError(f"Register '{reg.name}' is not writable")
        if reg.data_type == "int16":
            if not -32768 <= value <= 32767: raise ValueError("Int16 value must be -32768..32767")
            wire_value = value & 0xFFFF  # two's complement for Modbus
        else:
            if not 0 <= value <= 0xFFFF: raise ValueError("Uint16 value must be 0..65535")
            wire_value = value
        self.exchange(0x06, struct.pack(">HH", reg.address, wire_value))


def list_registers(as_json: bool) -> None:
    rows = [{"name": r.name, "access": "read/write" if r.writable else "read", "function": f"0x{r.function:02X}", "address": f"0x{r.address:04X}", "length": r.length, "type": r.data_type, "scale": r.scale, "unit": r.unit} for r in sorted(REGISTERS.values(), key=lambda x: (x.function, x.address, x.name))]
    print(json.dumps(rows, indent=2) if as_json else "\n".join(f"{r['name']}: {r['access']} {r['function']} {r['address']} {r['type']}" for r in rows))


def main() -> int:
    p = argparse.ArgumentParser(add_help=False, description=__doc__)
    p.add_argument("--help", action="help"); p.add_argument("-r"); p.add_argument("-w", nargs=2, metavar=("REGISTER", "VALUE"))
    p.add_argument("-h", dest="host"); p.add_argument("-P", type=int, default=DEFAULT_PORT); p.add_argument("-p", type=int)
    p.add_argument("-j", "--json", action="store_true"); p.add_argument("--list", action="store_true"); p.add_argument("-v", "--verbose", action="store_true"); p.add_argument("-t", type=float, default=DEFAULT_TIMEOUT)
    a = p.parse_args()
    if a.list: list_registers(a.json); return 0
    if not a.host: p.error("-h HOST is required unless --list is used")
    if bool(a.r) == bool(a.w): p.error("Specify exactly one of -r or -w")
    try:
        with ModbusTCP(a.host, a.P, a.t, a.verbose) as client:
            if a.r:
                result = {name: client.read(resolve(name)) for name in (x.strip() for x in a.r.split(",")) if name}
            else:
                name, raw = a.w; value = int(raw, 0); client.unlock(a.p if a.p is not None else DEFAULT_PIN); client.write(resolve(name), value); result = {name: value}
        print(json.dumps(result, indent=2) if a.json else "\n".join(f"{k}: {v}" for k, v in result.items()))
        return 0
    except (OSError, ValueError, RuntimeError, ConnectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1


if __name__ == "__main__": sys.exit(main())
