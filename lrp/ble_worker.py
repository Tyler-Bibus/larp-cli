"""Optional BLE transport. JSON lines keep Bluetooth work out of the curses loop."""

import asyncio
from collections import deque
import csv
import json
import signal
import sys
import time

from .ble_music import MIDI_SERVICE, MIDI_IO, Synth, decode_midi, note_name
from .ble_advertising import advertising_report, rf_report, tshark_command
from .ble_adv_midi import BUMBLE_ADDRESS, COMPANY_ID, AdvertisingMidiPlayer, midi_address

NAME = "SeniorDesign BLE"
SERVICE = "12345678-1234-5678-1234-56789abcdef0"
HEART = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
CLOCK = "00002a2b-0000-1000-8000-00805f9b34fb"


def emit(kind, **fields):
    print(json.dumps(dict(kind=kind, **fields)), flush=True)


def decode_sample(uuid, data):
    raw = bytes(data)
    if uuid == HEART:
        count = 3 if raw and raw[0] & 1 else 2
        if len(raw) < count:
            raise ValueError("Truncated heart-rate packet")
        return "heart", int.from_bytes(raw[1:count], "little"), "bpm"
    if uuid == BATTERY:
        if len(raw) != 1 or raw[0] > 100:
            raise ValueError("Invalid battery packet")
        return "battery", raw[0], "%"
    if uuid == CLOCK:
        if len(raw) != 10:
            raise ValueError("Invalid current-time packet")
        year = int.from_bytes(raw[:2], "little")
        return "clock", f"{year:04}-{raw[2]:02}-{raw[3]:02} {raw[4]:02}:{raw[5]:02}:{raw[6]:02}", ""
    raise ValueError("Unknown notification channel")


async def scan(scanner):
    emit("state", state="scanning", message="Sweeping for SeniorDesign BLE carriers...")
    found = await scanner.discover(timeout=7, return_adv=True)
    devices = []
    for device, adv in found.values():
        name = adv.local_name or device.name or "Unnamed ESP32"
        if name == NAME or SERVICE in adv.service_uuids or MIDI_SERVICE in adv.service_uuids:
            devices.append(dict(name=name[:65], address=device.address, rssi=adv.rssi))
    devices.sort(key=lambda item: item["rssi"], reverse=True)
    emit("devices", devices=devices[:24])
    emit("state", state="idle", message=(f"{len(devices)} carrier(s) acquired. Select one, then connect."
         if devices else "No carrier found. Disconnect the phone, keep ESP32 powered, then scan again."))


async def advertise(scanner):
    emit("state", state="starting", message="Starting unfiltered BLE discovery...")

    def received(device, adv):
        report = advertising_report(device, adv)
        emit(report.pop("kind"), **report)

    # Request repeated reports on Linux. The controller/OS can still merge or
    # suppress packets, so these callbacks must never be called RF packet counts.
    async with scanner(detection_callback=received,
                       bluez={"filters": {"DuplicateData": True}}):
        emit("state", state="sniffing", message="All advertisers / RSSI dBm / channel and CRC unavailable from adapter")
        await asyncio.Event().wait()


async def advertising_midi(scanner, target=BUMBLE_ADDRESS):
    target = midi_address(target or BUMBLE_ADDRESS)
    emit("state", state="starting", message=f"Listening for Bumble at {target}; no connection needed")
    player = AdvertisingMidiPlayer(Synth())
    last_event = {}
    playback_errors = []

    def received(device, adv):
        if device.address.upper() != target:
            return
        report = advertising_report(device, adv)
        emit(report.pop("kind"), **report)
        data = adv.manufacturer_data.get(COMPANY_ID)
        if data is None:
            return
        try:
            event = player.receive(data)
        except (RuntimeError, OSError) as exc:
            # Bleak logs callback exceptions rather than propagating them to
            # the scanner task. Surface missing SoundFonts/audio failures here.
            if not playback_errors:
                playback_errors.append(str(exc))
            return
        if event is not None:
            last_event.clear()
            last_event.update(event)

    def status(enabled=True):
        emit("adv_midi", enabled=enabled, address=target, played=player.played,
             duplicates=player.duplicates, invalid=player.invalid,
             current_note=(" ".join(f"{k}:{note_name(n)}" for k, (n, v, _) in enumerate(player.voices) if v)
                           if player.version == 2 else note_name(player.note) if player.note is not None else "--") or "--",
             programs=player.programs, strikes=player.strikes, watchdog=player.watchdog,
             protocol=player.version, voice_states=player.voices,
             watchdog_count=player.watchdog_count,
             error=player.last_error, **last_event)

    try:
        async with scanner(detection_callback=received,
                           bluez={"filters": {"DuplicateData": True}}):
            emit("state", state="sniffing", message=f"Bumble ADV MIDI / {target} / manufacturer 0xFFFF / BM v1 + v2")
            emit("music", enabled=True, message="Bumble advertisement MIDI listening; d stops playback")
            status()
            last_status = time.monotonic()
            while True:
                await asyncio.sleep(.01)
                player.tick()
                if playback_errors:
                    raise RuntimeError(playback_errors[0])
                if player.synth.error:
                    raise RuntimeError(player.synth.error)
                if time.monotonic() - last_status >= .1:
                    status()
                    last_status = time.monotonic()
    finally:
        try:
            player.close()
        finally:
            status(enabled=False)
            emit("music", enabled=False, message="Bumble advertisement MIDI stopped")


async def sniff_rf(target, replay=False):
    if not target:
        raise ValueError("Specify a BLE RF sniffer interface from tshark -D, or a capture file for replay.")
    try:
        process = await asyncio.create_subprocess_exec(
            *tshark_command(target, replay), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=1024 * 1024)
    except FileNotFoundError:
        raise RuntimeError("RF mode needs tshark plus a configured BLE RF sniffer. Use :ble sniff for the Bluetooth adapter.") from None
    errors = deque(maxlen=8)

    async def read_errors():
        async for line in process.stderr:
            errors.append(line.decode(errors="replace").strip()[:300])

    reader = asyncio.create_task(read_errors())
    try:
        emit("state", state="sniffing", message=("Replaying " if replay else "RF capture: ") + target)
        async for line in process.stdout:
            try:
                report = rf_report(line.decode(errors="replace"))
            except (ValueError, csv.Error):
                emit("notice", message="Could not decode TShark RF report; check the sniffer format.")
                continue
            if report is not None:
                emit(report.pop("kind"), **report)
        code = await process.wait()
        await reader
        if code:
            raise RuntimeError("TShark: " + (" / ".join(errors) or f"exit {code}") + "; check tshark -D and capture permissions.")
        emit("state", state="disconnected", message="Capture complete. Results retained; a to restart adapter discovery.")
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        await reader


async def connect(scanner, client_class, target):
    emit("state", state="connecting", message=f"Acquiring {target}...")
    device = await scanner.find_device_by_filter(
        lambda dev, adv: dev.address.upper() == target.upper() or adv.local_name == target,
        timeout=18,
    )
    if device is None:
        raise RuntimeError("ESP32 not found. Disconnect the phone and scan again; it accepts one client.")
    disconnected = asyncio.Event()
    async with client_class(device, timeout=25, pair=False,
                            disconnected_callback=lambda _: disconnected.set()) as client:
        channels = [uuid for uuid in (HEART, BATTERY, CLOCK)
                    if client.services.get_characteristic(uuid) is not None]
        if not channels:
            raise RuntimeError("Connected device has no supported telemetry channels.")
        model = "ESP32"
        model_char = client.services.get_characteristic("00002a24-0000-1000-8000-00805f9b34fb")
        if model_char is not None:
            model = bytes(await client.read_gatt_char(model_char)).decode(errors="replace")[:65]
        emit("device", name=device.name or NAME, address=device.address,
             services=len(list(client.services)), model=model, channels=len(channels))

        def notification(uuid):
            def received(_characteristic, data):
                try:
                    metric, value, unit = decode_sample(uuid, data)
                    emit("sample", metric=metric, value=value, unit=unit,
                         raw=bytes(data).hex(), timestamp=time.time())
                except ValueError as exc:
                    emit("notice", message=str(exc))
            return received

        battery = client.services.get_characteristic(BATTERY)
        if battery is not None and "read" in battery.properties:
            value = await client.read_gatt_char(battery)
            metric, number, unit = decode_sample(BATTERY, value)
            emit("reading", metric=metric, value=number, unit=unit)
        for uuid in channels:
            await client.start_notify(uuid, notification(uuid))
        emit("state", state="connected", message="Carrier locked. Real BLE packets / device-simulated payload.")
        controls = asyncio.Queue()
        loop = asyncio.get_running_loop()
        synth = None
        subscribed = False

        def control_ready():
            line = sys.stdin.readline()
            if not line:
                loop.remove_reader(sys.stdin.fileno())
                disconnected.set()
                return
            try:
                controls.put_nowait(json.loads(line))
            except ValueError:
                emit("notice", message="Invalid music command")

        def midi_received(_characteristic, data):
            # BlueZ may report the empty readable value when notifications start.
            if not data:
                return
            try:
                _, status, note, velocity = decode_midi(data)
                if synth is not None:
                    synth.message(status, note, velocity)
                on = status & 0xf0 == 0x90 and velocity > 0
                emit("sample", metric="midi", value=note_name(note),
                     unit="ON" if on else "OFF", raw=bytes(data).hex(), timestamp=time.time())
            except ValueError as exc:
                emit("notice", message=str(exc))

        loop.add_reader(sys.stdin.fileno(), control_ready)
        try:
            while not disconnected.is_set():
                if synth is not None and synth.error:
                    error = synth.error
                    try:
                        if subscribed and client.is_connected:
                            await client.stop_notify(MIDI_IO)
                    finally:
                        subscribed = False
                        synth.close()
                        synth = None
                    emit("music", enabled=False, message=error)
                try:
                    command = await asyncio.wait_for(controls.get(), timeout=.2)
                except asyncio.TimeoutError:
                    continue
                if not isinstance(command, dict) or command.get("action") != "music":
                    continue
                enable = bool(command.get("enabled"))
                if enable and synth is None:
                    if client.services.get_characteristic(MIDI_IO) is None:
                        emit("music", enabled=False, message="Flash the music firmware first.")
                        continue
                    try:
                        synth = Synth()
                        await client.start_notify(MIDI_IO, midi_received)
                        subscribed = True
                    except Exception as exc:
                        if synth is not None:
                            synth.close()
                            synth = None
                        emit("music", enabled=False, message=f"Could not start music: {exc}")
                        continue
                elif not enable and synth is not None:
                    try:
                        await client.stop_notify(MIDI_IO)
                    finally:
                        subscribed = False
                        synth.close()
                        synth = None
                emit("music", enabled=enable, message="FUNK TRANSMISSION ON" if enable else "Music muted.")
        finally:
            loop.remove_reader(sys.stdin.fileno())
            if synth is not None:
                synth.close()
            if subscribed and client.is_connected:
                await client.stop_notify(MIDI_IO)
            emit("music", enabled=False, message="Music stopped.")
    emit("state", state="disconnected", message="Carrier released. Connect again when ready.")


async def run(action, target):
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        if action in ("sniff-rf", "replay"):
            await sniff_rf(target, replay=action == "replay")
        else:
            try:
                from bleak import BleakClient, BleakScanner
            except ImportError:
                raise RuntimeError("BLE needs Bleak: install ble-requirements.txt in larp/.venv, or set LRP_BLE_PYTHON to a Python with Bleak.") from None
            if action == "scan":
                await scan(BleakScanner)
            elif action == "connect":
                await connect(BleakScanner, BleakClient, target)
            elif action == "sniff":
                await advertise(BleakScanner)
            elif action == "adv-midi":
                await advertising_midi(BleakScanner, target)
            else:
                raise ValueError("Unknown BLE action")
    except asyncio.CancelledError:
        emit("state", state="disconnected", message="Radio goblin contained. Link closed.")
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def main():
    try:
        asyncio.run(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else NAME))
        return 0
    except Exception as exc:
        emit("state", state="error", message=f"Bluetooth: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
