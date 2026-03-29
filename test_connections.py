#!/usr/bin/env python3
"""
Test that OBS WebSocket and Ableton OSC servers are reachable.
Run with: python test_connections.py
"""

import socket
import struct
import time
import pathlib
import yaml
from pythonosc.osc_message_builder import OscMessageBuilder

CONFIG_PATH = pathlib.Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

OBS_HOST     = config["obs"]["host"]
OBS_PORT     = config["obs"]["port"]
OBS_PASSWORD = config["obs"]["password"]
ABL_HOST     = config["ableton"]["host"]
ABL_PORT     = config["ableton"]["port"]


def test_obs():
    print("Testing OBS WebSocket...")
    try:
        import obsws_python as obs
        kwargs = dict(host=OBS_HOST, port=OBS_PORT, timeout=3)
        if OBS_PASSWORD:
            kwargs["password"] = OBS_PASSWORD
        client = obs.ReqClient(**kwargs)
        ver = client.get_version()
        print(f"  OK  OBS {ver.obs_version}, WebSocket {ver.obs_web_socket_version}")
    except Exception as e:
        print(f"  FAIL  {e}")
        print("  Make sure OBS is running and WebSocket server is enabled")
        print("  (Tools > WebSocket Server Settings)")


def test_ableton_osc():
    print("Testing Ableton OSC...")
    LISTEN_PORT = 11001

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    sock.settimeout(3)

    def send(addr):
        msg = OscMessageBuilder(address=addr).build()
        sock.sendto(msg.dgram, (ABL_HOST, ABL_PORT))

    try:
        send("/live/song/get/tempo")
        send("/live/application/get/version")

        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                data, _ = sock.recvfrom(4096)
                # Parse address from OSC packet
                addr_end = data.index(b"\x00")
                osc_addr = data[:addr_end].decode("utf-8")
                # Parse float value if present
                type_tag_start = (addr_end + 4) & ~3
                types = data[type_tag_start:].split(b"\x00", 1)[0].decode("utf-8")
                if "f" in types:
                    val_offset = (type_tag_start + len(types) + 5) & ~3
                    val = struct.unpack(">f", data[val_offset:val_offset + 4])[0]
                    if "tempo" in osc_addr:
                        print(f"  OK  AbletonOSC responding — tempo: {val:.1f} BPM")
                    else:
                        print(f"  OK  {osc_addr} = {val}")
                else:
                    print(f"  OK  AbletonOSC responding — {osc_addr}")
                break
            except socket.timeout:
                break
        else:
            print("  FAIL  No reply from AbletonOSC")
            print("  Make sure Ableton is open and AbletonOSC is set as a Control Surface")
            print("  (Preferences > Link/Tempo/MIDI > Control Surfaces)")
    finally:
        sock.close()


if __name__ == "__main__":
    test_obs()
    test_ableton_osc()
