"""Advertising observations and optional Wireshark RF metadata.

OS discovery reports are deliberately kept distinct from over-the-air packets:
BlueZ can merge scan responses, cache data, and suppress duplicates.
"""

from collections import OrderedDict, deque
import csv
import time

ADVERTISING_CHANNELS = {37: 2402, 38: 2426, 39: 2480}
ADV_TYPES = {0: "ADV_IND", 1: "ADV_DIRECT_IND", 2: "ADV_NONCONN_IND",
             6: "ADV_SCAN_IND", 7: "ADV_EXT_IND"}
RF_FIELDS = (
    "frame.time_epoch", "btle.advertising_header.pdu_type", "btle.advertising_address",
    "btcommon.eir_ad.entry.device_name", "nordic_ble.channel", "nordic_ble.rssi",
    "nordic_ble.crcok", "btle_rf.channel", "btle_rf.signal_dbm",
    "btle_rf.flags.signal_dbm_valid", "btle_rf.flags.channel_aliased",
    "btle_rf.flags.crc_checked", "btle_rf.flags.crc_valid", "_ws.col.Info",
)


def advertising_report(device, adv):
    """Preserve decoded data without pretending it is a raw PDU."""
    parts = [f"MFG {company:04x}:{bytes(data).hex()}"
             for company, data in adv.manufacturer_data.items()]
    parts += [f"SVC {uuid}:{bytes(data).hex()}" for uuid, data in adv.service_data.items()]
    parts += [f"UUID {uuid}" for uuid in adv.service_uuids]
    return dict(kind="advertisement", source="adapter", timestamp=time.time(),
                address=device.address, name=adv.local_name or device.name or "(unnamed)",
                rssi=adv.rssi if adv.rssi != 127 else None, tx_power=adv.tx_power,
                channel=None, crc=None, pdu="OS report", payload=" / ".join(parts) or "No decoded payload fields")


def tshark_command(target, replay=False):
    command = ["tshark", "-l", "-n", "-r" if replay else "-i", target,
               "-Y", "btle.advertising_header.pdu_type in {0 1 2 6 7}",
               "-T", "fields", "-E", "separator=/t", "-E", "quote=d", "-E", "occurrence=f"]
    for field in RF_FIELDS:
        command += ["-e", field]
    return command


def rf_report(line):
    """Read TShark fields; RF frequency indices differ from BLE channel indices."""
    values = next(csv.reader([line], delimiter="\t"))
    if len(values) != len(RF_FIELDS):
        raise ValueError("Incomplete TShark RF report")
    stamp, pdu, address, name, nc, nr, crc, rc, rr, rv, alias, checked, valid, info = values
    pdu = int(pdu, 0)
    if pdu not in ADV_TYPES:
        return None  # Scan requests/responses and connections are not advertisements.
    channel = rssi = crc_ok = None
    if nc:
        channel = int(nc)
        rssi = int(nr) if nr else None
        crc_ok = crc == "1" if crc else None
    elif rc:
        # LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR numbers RF channels by frequency.
        rf = int(rc)
        if alias != "1" and 0 <= rf <= 39:
            channel = {0: 37, 12: 38, 39: 39}.get(rf, rf - (1 if rf < 12 else 2))
        rssi = int(rr) if rv == "1" and rr else None
        crc_ok = valid == "1" if checked == "1" else None
    return dict(kind="advertisement", source="rf", timestamp=float(stamp),
                address=address or "(no AdvA)", name=name or "(unnamed)",
                channel=channel, rssi=rssi, crc=crc_ok, pdu=ADV_TYPES[pdu], payload=info)


class AdvertisingMonitor:
    def __init__(self):
        self.source = "adapter"
        self.count = self.unknown = self.bad_crc = 0
        self.last = None
        self.offset = 0
        self.devices = OrderedDict()
        self.packets = deque(maxlen=120)
        self.channels = {channel: dict(count=0, bad=0, rssi=None, peak=None, last=None)
                         for channel in ADVERTISING_CHANNELS}

    def ingest(self, event):
        now = time.monotonic()
        self.source = event["source"]
        self.count += 1
        self.last = now
        self.bad_crc += event.get("crc") is False
        packet = dict(event, seen=now)
        self.packets.append(packet)
        channel, rssi = event.get("channel"), event.get("rssi")
        if channel in self.channels:
            stats = self.channels[channel]
            stats["count"] += 1
            stats["bad"] += event.get("crc") is False
            stats["last"], stats["rssi"] = now, rssi
            if rssi is not None:
                stats["peak"] = rssi if stats["peak"] is None else max(stats["peak"], rssi)
        else:
            self.unknown += 1
        address = event["address"]
        previous = self.devices.pop(address, {})
        packet["count"] = previous.get("count", 0) + 1
        packet["peak"] = previous.get("peak")
        if rssi is not None:
            packet["peak"] = rssi if packet["peak"] is None else max(packet["peak"], rssi)
        self.devices[address] = packet
        if len(self.devices) > 256:
            self.devices.popitem(last=False)
