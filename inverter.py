#!/usr/bin/env python3
"""ESC3-5K / ESC3-5KW-DS inverter Modbus/TCP utility. By Emilie (www.sixbynine.no) Git: https://github.com/ravng/esc3-inverter"""
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
UNLOCK_REGISTER = 0x0000
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


def add_holding(name: str, address: int, *, writable: bool = False,
                length: int = 1, data_type: str = "uint16",
                scale: float = 1.0, unit: str = "", description: str = "") -> None:
    REGISTERS[name] = Register(name, address, 0x03, length, data_type,
                               scale, unit, writable, description)


def add_input(name: str, address: int, *, length: int = 1,
              data_type: str = "uint16", scale: float = 1.0,
              unit: str = "", description: str = "") -> None:
    REGISTERS[name] = Register(name, address, 0x04, length, data_type,
                               scale, unit, False, description)


# Holding registers, function 0x03.  The names use underscores so they are
# convenient and unambiguous when used from a shell.
_HOLDING = [
    ("AllowUnlockCommand", 0x00, True, 1, "uint16", 1, "", "Unlock/write password"),
    ("SeriesNumber", 0x01, True, 8, "text", 1, "", "Inverter serial number"),
    ("FactoryName", 0x09, False, 8, "text", 1, "", "Factory name"),
    ("ModuleName", 0x11, False, 8, "text", 1, "", "Module name"),
    ("Machine_Type", 0x19, False, 1, "uint16", 1, "", "Machine type"),
    ("MyAddress", 0x1A, True, 1, "uint16", 1, "", "Machine address"),
    ("Language", 0x1B, True, 1, "uint16", 1, "", "0 English, 1 German"),
    ("IP_Method", 0x1C, True, 1, "uint16", 1, "", "0 DHCP, 1 manual"),
    ("Machine_switch", 0x1D, False, 1, "uint16", 1, "", "Software/hardware switch"),
    ("Password", 0x1E, False, 1, "uint16", 1, "", "Password state"),
    ("Safety", 0x1F, True, 1, "uint16", 1, "", "Grid safety profile"),
    ("PvConnectionMode", 0x20, True, 1, "uint16", 1, "", "PV input mode"),
    ("VpvStart", 0x21, True, 1, "uint16", .1, "V", "PV start voltage"),
    ("TimeStart", 0x22, True, 1, "uint16", 1, "s", "Start delay"),
    ("VpvHighStop", 0x23, True, 1, "uint16", .1, "V", "PV high voltage stop"),
    ("VpvLowStop", 0x24, True, 1, "uint16", .1, "V", "PV low voltage stop"),
    ("VacMinProtect", 0x25, True, 1, "uint16", .1, "V", "Minimum grid voltage"),
    ("VacMaxProtect", 0x26, True, 1, "uint16", .1, "V", "Maximum grid voltage"),
    ("FacMinProtect", 0x27, True, 1, "uint16", .01, "Hz", "Minimum grid frequency"),
    ("FacMaxProtect", 0x28, True, 1, "uint16", .01, "Hz", "Maximum grid frequency"),
    ("VacMinSlowProtect", 0x29, True, 1, "uint16", .1, "V", "Slow undervoltage limit"),
    ("VacMaxSlowProtect", 0x2A, True, 1, "uint16", .1, "V", "Slow overvoltage limit"),
    ("FacMinSlowProtect", 0x2B, True, 1, "uint16", .01, "Hz", "Slow underfrequency limit"),
    ("FacMaxSlowProtect", 0x2C, True, 1, "uint16", .01, "Hz", "Slow overfrequency limit"),
    ("Grid10MinAvgProtect", 0x2D, True, 1, "uint16", .1, "V", "10-minute voltage limit"),
    ("wTimeVacMin_FastAdj", 0x2E, True), ("wTimeVacMax_FastAdj", 0x2F, True),
    ("wTimeFacMin_FastAdj", 0x30, True), ("wTimeFacMax_FastAdj", 0x31, True),
    ("wTimeVacMin_SlowAdj", 0x32, True), ("wTimeVacMax_SlowAdj", 0x33, True),
    ("wTimeFacMin_SlowAdj", 0x34, True), ("wTimeFacMax_SlowAdj", 0x35, True),
    ("DciLimits", 0x36, True), ("DciLimits2", 0x37, True),
    ("DciProtectTime", 0x38, True), ("DciProtectTime2", 0x39, True),
    ("PowerLimitsPercent", 0x3A, True, 1, "uint16", 1, "%", "Output power limit"),
    ("FreqSetPoint", 0x3B, True, 1, "uint16", .01, "Hz"),
    ("FreqDroopRate", 0x3C, True, 1, "uint16", .01),
    ("FreDroopDelayTime", 0x3D, True), ("PowerfactorMode", 0x3E, True),
    ("PowerfactorData", 0x3F, True, 1, "uint16", .01),
    ("UpperLimit", 0x40, True, 1, "uint16", .01), ("LowerLimit", 0x41, True, 1, "uint16", .01),
    ("PowerLow", 0x42, True, 1, "uint16", .01), ("PowerUp", 0x43, True, 1, "uint16", .01),
    ("Connect_Time", 0x44, True), ("QuVrateLow", 0x45, True, 1, "uint16", .01),
    ("PfLockInPoint", 0x46, True), ("PfLockOutPoint", 0x47, True),
    ("SelfTestStep", 0x48, True),
    ("SelfTestOvpValue", 0x49), ("SelfTestOvpTime", 0x4A),
    ("SelfTestUvpValue", 0x4B), ("SelfTestUvpTime", 0x4C),
    ("SelfTestOfpValue", 0x4D), ("SelfTestOfpTime", 0x4E),
    ("SelfTestUfpValue", 0x4F), ("SelfTestUfpTime", 0x50),
    ("SelfTestOvp10mAvgVal", 0x51), ("SelfTestOvp10mAvgTime", 0x52),
    ("SelfTestOfpValue_Restrictive", 0x53), ("SelfTestOfpTime_Restrictive", 0x54),
    ("SelfTestUfpValue_Restrictive", 0x55), ("SelfTestUfpTime_Restrictive", 0x56),
    ("wExt_SetChargerPower", 0x57, True, 1, "int16", 1, "W"),
    ("wExt_SetInverterPower", 0x58, True, 1, "int16", 1, "W"),
    ("PowerManagerConfigData", 0x59, True, 80), ("PowerManagerEnable", 0xA9, True),
    ("FirmwareVersion_InverterMaster", 0xAA), ("FirmwareVersion_InverterSlave", 0xAB),
    ("FirmwareVersion_Charger1", 0xAC), ("FirmwareVersion_Charger2", 0xAD),
    ("FirmwareVersion_Charger3", 0xAE), ("FirmwareVersion_Charger4", 0xAF),
    ("FirmwareVersion_Manager", 0xB0), ("wFirmwareVersion_Protocol", 0xB1),
    ("ItalySelftestStart", 0xB2, True),
    ("RTC_Seconds", 0xB3), ("RTC_Minutes", 0xB4), ("RTC_Hours", 0xB5),
    ("RTC_Days", 0xB6), ("RTC_Months", 0xB7), ("RTC_Years", 0xB8),
    ("SolarChargerUseMode", 0xB9, True), ("Allow_Grid_Charge", 0xBA, True),
    ("Export_control_factory_limit", 0xBB, True), ("Export_control_user_limit", 0xBC, True),
    ("EPS_Mute", 0xBD, True), ("EPS_Frequency", 0xBE, True),
    ("ChargerStartTime1_Hours", 0xBF, True), ("ChargerStartTime1_Minutes", 0xC0, True),
    ("ChargerEndTime1_Hours", 0xC1, True), ("ChargerEndTime1_Minutes", 0xC2, True),
    ("DischargerStartTime1_Hours", 0xC3, True), ("DischargerStartTime1_Minutes", 0xC4, True),
    ("DischargerEndTime1_Hours", 0xC5, True), ("DischargerEndTime1_Minutes", 0xC6, True),
    ("ChargerStartTime2_Hours", 0xC7, True), ("ChargerStartTime2_Minutes", 0xC8, True),
    ("ChargerEndTime2_Hours", 0xC9, True), ("ChargerEndTime2_Minutes", 0xCA, True),
    ("DischargerStartTime2_Hours", 0xCB, True), ("DischargerStartTime2_Minutes", 0xCC, True),
    ("DischargerEndTime2_Hours", 0xCD, True), ("DischargerEndTime2_Minutes", 0xCE, True),
    ("frqprotectrestrictive", 0xCF, True), ("BatteryNum", 0xD5),
    ("Battery1_MinCapcity", 0xD6, False, 1, "uint16", .01, "%"),
    ("Battery1Type", 0xD7, True), ("Battery1_ChargeCutVoltage", 0xD8, True, 1, "uint16", .01),
    ("Battery1_DischargeCutVoltage", 0xD9, True, 1, "uint16", .01),
    ("Battery1_ChargeMaxCurrent", 0xDA, True, 1, "uint16", .01),
    ("Battery1_DischargeMaxCurrent", 0xDB, True, 1, "uint16", .01),
    ("wBattery1_absorpt_voltage", 0xDC, True, 1, "uint16", .01),
    ("wBattery1_wEpsDischargeVolt", 0xDD, True, 1, "uint16", .01),
    ("Battery_Health", 0xDE, False, 1, "uint16", .01, "%"),
    ("Charge1_MinCapcity", 0xDF, True, 1, "uint16", .01), ("Bat_awaking", 0xE0, True),
    ("wBattery1_VendorCode", 0xE1, True),
    ("MAC_Address", 0x10D, True, 3, "text"), ("BackUp_GridChargeFlag", 0x110, True),
    ("wBackUp_Chr_Start_H", 0x111, True), ("wBackUp_Chr_Start_M", 0x112, True),
    ("wBackUp_Chr_End_H", 0x113, True), ("wBackUp_Chr_End_M", 0x114, True),
    ("wPFValue", 0x115, True), ("wCTMeterEnableFlg", 0x116, True),
    ("wFreqOverStart", 0x117, True, 1, "uint16", .01, "Hz"),
    ("wFreqOverEnd", 0x118, True, 1, "uint16", .01, "Hz"),
    ("wFreqUnderStart", 0x119, True, 1, "uint16", .01, "Hz"),
    ("wFreqUnderEnd", 0x11A, True, 1, "uint16", .01, "Hz"),
    ("wFFR_SOC_Reserved", 0x11B, True, 1, "uint16", .01),
    ("wRemoteChargeSubMode", 0x11C, True),
    ("wRemoteChargerPowerSet", 0x11D, True, 1, "int16", 1, "W"),
    ("AllowSolarMaxUse", 0x120, True),
]

for row in _HOLDING:
    name, address, *rest = row
    writable = rest[0] if rest else False
    values = rest[1:]
    values += [None] * (6 - len(values))
    length = values[0] if values[0] is not None else 1
    dtype = values[1] if values[1] is not None else "uint16"
    scale = values[2] if values[2] is not None else 1.0
    unit = values[3] if values[3] is not None else ""
    desc = values[4] if values[4] is not None else ""
    add_holding(name, address, writable=writable, length=length,
                data_type=dtype, scale=scale, unit=unit, description=desc)


# Input registers, function 0x04. These are zero-based offsets. In particular,
# Capacity_Charge1 is 0x50 (not 0x51); 0x51 is reserved.
_INPUT = [
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
    ("feedin_power2", 0x20, "int32", 1, "W"), ("feedin_energy2", 0x22, "uint32", .01, "kWh"),
    ("consum_energy2", 0x24, "uint32", .01, "kWh"), ("Etoday2", 0x26, "uint16", .01, "kWh"),
    ("Etotal2", 0x28, "uint32", .01, "kWh"), ("EPS_Volt", 0x2A, "uint16", .1, "V"),
    ("EPS_Current", 0x2B, "uint16", .1, "A"), ("EPS_Power", 0x2C, "uint16", 1, "VA"),
    ("EPS_Frequency", 0x2D, "uint16", .01, "Hz"), ("EtodayEPS", 0x2E, "uint16", .1, "kWh"),
    ("EtotalEPS", 0x30, "uint32", .1, "kWh"), ("PowerLoad", 0x32, "uint16", 1, "W"),
    ("EtodayLoad", 0x33, "uint16", .1, "kWh"), ("EtotalLoad", 0x34, "uint32", .1, "kWh"),
    ("PvEnergyToday", 0x36, "uint16", .1, "kWh"), ("PvEnergyTotal", 0x38, "uint32", .1, "kWh"),
    ("wCanCommLost", 0x3A, "uint16", 1, ""), ("InvFaultMessage1", 0x40, "uint16", 1, ""),
    ("InvFaultMessage2", 0x41, "uint16", 1, ""), ("InvFaultMessage3", 0x42, "uint16", 1, ""),
    ("InvFaultMessage4", 0x43, "uint16", 1, ""), ("Mgr_FaultMessage", 0x44, "uint16", 1, ""),
    ("chargerNum", 0x45, "uint16", 1, ""),
]
for name, address, dtype, scale, unit in _INPUT:
    add_input(name, address, data_type=dtype, scale=scale, unit=unit)

for charger, base in enumerate((0x46, 0x5C, 0x72, 0x88), 1):
    suffix = f"_Charge{charger}"
    fields = [
        (f"BatVoltage{suffix}", 0, "int16", .01, "V"), (f"BatCurrent{suffix}", 1, "int16", .01, "A"),
        (f"Batpower{suffix}", 2, "int16", 1, "W"), (f"TemperatureBoard{suffix}", 3, "int16", 1, "°C"),
        (f"TemperatureBat{suffix}", 4, "int16", 1, "°C"), (f"TemperatureTransformer{suffix}", 5, "int16", 1, "°C"),
        (f"TemperatureBoost{suffix}", 5, "int16", 1, "°C"), (f"BatVoltageFaultValue{suffix}", 6, "uint16", .1, "V"),
        (f"BatCurrentFaultValue{suffix}", 7, "int16", .01, "A"), (f"BoostVoltageFaultValue{suffix}", 8, "uint16", .1, "V"),
        (f"BoostCurrentFaultValue{suffix}", 9, "int16", .01, "A"),
        (f"Capacity{suffix}", 10, "uint16", 1, "%"),
        (f"OutputEnergy{suffix}", 12, "uint32", .1, "kWh"),
        (f"BMS{charger}_warnings", 14, "uint16", 1, ""), (f"BMS{charger}_warnings_back", 15, "uint16", 1, ""),
    ]
    for name, offset, dtype, scale, unit in fields:
        if name not in REGISTERS:
            add_input(name, base + offset, length=2 if dtype == "uint32" else 1,
                      data_type=dtype, scale=scale, unit=unit)

ALIASES = {
    "Allow_GridCharge": "Allow_Grid_Charge", "BatteryHealth": "Battery_Health",
    "IPMethod": "IP_Method", "IP Method": "IP_Method", "MAC": "MAC_Address",
}


def resolve(name: str) -> Register:
    name = ALIASES.get(name.strip(), name.strip())
    if name not in REGISTERS:
        raise ValueError(f"Unknown register '{name}'. Use --list to see known registers.")
    return REGISTERS[name]


def decode_words(reg: Register, words: list[int]) -> Any:
    if reg.data_type == "text":
        raw = b"".join(struct.pack(">H", word) for word in words)
        return raw.rstrip(b"\x00 \xff").decode("ascii", errors="replace")
    if reg.data_type == "uint16": value = words[0]
    elif reg.data_type == "int16": value = struct.unpack(">h", struct.pack(">H", words[0]))[0]
    elif reg.data_type in ("uint32", "int32"):
        # Documentation specifies low word first for multi-register values.
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
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        return self

    def __exit__(self, *_):
        if self.sock: self.sock.close()

    def _recv_exact(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))  # type: ignore[union-attr]
            if not chunk: raise ConnectionError("Connection closed by inverter")
            data += chunk
        return data

    def exchange(self, function: int, payload: bytes) -> bytes:
        if not self.sock: raise RuntimeError("Not connected")
        self.transaction = (self.transaction + 1) & 0xFFFF
        pdu = bytes([UNIT_ID, function]) + payload
        frame = struct.pack(">HHH", self.transaction, 0, len(pdu)) + pdu
        if self.verbose: print(">> " + frame.hex(" "), file=sys.stderr)
        self.sock.sendall(frame)
        header = self._recv_exact(7)
        tid, proto, length, unit = struct.unpack(">HHHB", header)
        if tid != self.transaction or proto != 0 or unit != UNIT_ID:
            raise RuntimeError("Invalid Modbus/TCP response header")
        body = self._recv_exact(length - 1)
        if self.verbose: print("<< " + (header + body).hex(" "), file=sys.stderr)
        if body[0] & 0x80: raise RuntimeError(f"Modbus exception 0x{body[1]:02x}")
        return body[1:]

    def read(self, reg: Register) -> Any:
        response = self.exchange(reg.function, struct.pack(">HH", reg.address, reg.length))
        if response[0] != reg.length * 2: raise RuntimeError(f"Unexpected byte count for {reg.name}")
        words = list(struct.unpack(">" + "H" * reg.length, response[1:]))
        return decode_words(reg, words)

    def unlock(self, pin: int) -> None:
        if not 0 <= pin <= 0xFFFF: raise ValueError("PIN must be 0..65535")
        self.exchange(0x06, struct.pack(">HH", UNLOCK_REGISTER, pin))

    def write(self, reg: Register, value: int) -> None:
        if not reg.writable or reg.function != 0x03 or reg.length != 1:
            raise ValueError(f"Register '{reg.name}' is not a writable single holding register")
        if reg.data_type == "int16":
            if not -32768 <= value <= 32767: raise ValueError("Int16 value must be -32768..32767")
            wire_value = value & 0xFFFF  # Modbus two's-complement representation
        elif reg.data_type == "uint16":
            if not 0 <= value <= 0xFFFF: raise ValueError("Uint16 value must be 0..65535")
            wire_value = value
        else:
            raise ValueError(f"Unsupported write type: {reg.data_type}")
        self.exchange(0x06, struct.pack(">HH", reg.address, wire_value))


def list_registers(as_json: bool) -> None:
    rows = [{"name": r.name, "access": "read/write" if r.writable else "read",
             "function": f"0x{r.function:02X}", "address": f"0x{r.address:04X}",
             "length": r.length, "type": r.data_type, "scale": r.scale,
             "unit": r.unit, "description": r.description}
            for r in sorted(REGISTERS.values(), key=lambda x: (x.function, x.address, x.name))]
    if as_json: print(json.dumps(rows, indent=2)); return
    print(f"{'Name':<38} {'Access':<11} {'Function':<8} {'Address':<8} {'Len':<4} {'Type':<8} Unit")
    print("-" * 100)
    for r in rows:
        print(f"{r['name']:<38} {r['access']:<11} {r['function']:<8} {r['address']:<8} {r['length']:<4} {r['type']:<8} {r['unit']}")


def main() -> int:
    p = argparse.ArgumentParser(add_help=False, description=__doc__)
    p.add_argument("--help", action="help")
    p.add_argument("-r", metavar="X", help="Read register name(s), comma separated")
    p.add_argument("-w", nargs=2, metavar=("X", "Y"), help="Write value Y to register X")
    p.add_argument("-h", dest="host", help="Inverter IP address or hostname")
    p.add_argument("-P", type=int, default=DEFAULT_PORT, help="TCP port 502")
    p.add_argument("-p", type=int, default=None, help="Unlock PIN, default 1919")
    p.add_argument("-j", "--json", action="store_true", help="Output json formated")
    p.add_argument("--list", action="store_true", help="List known registers")
    p.add_argument("-v", "--verbose", action="store_true", help="Show raw modbus messages")
    p.add_argument("-t", type=float, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    args = p.parse_args()
    if args.list:
        list_registers(args.json); return 0
    if not args.host: p.error("-h HOST is required unless --list is used")
    if bool(args.r) == bool(args.w): p.error("Specify exactly one of -r or -w")
    try:
        with ModbusTCP(args.host, args.P, args.t, args.verbose) as client:
            if args.r:
                result = {}
                for requested in (x.strip() for x in args.r.split(",") if x.strip()):
                    result[requested] = client.read(resolve(requested))
                print(json.dumps(result, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in result.items()))
            else:
                requested, raw_value = args.w
                value = int(raw_value, 0)  # accepts decimal, hex, and negative decimal
                reg = resolve(requested)
                client.unlock(args.p if args.p is not None else DEFAULT_PIN)
                client.write(reg, value)
                print(json.dumps({requested: value}, indent=2) if args.json else f"{requested}: {value}")
        return 0
    except (OSError, ValueError, RuntimeError, ConnectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    sys.exit(main())
