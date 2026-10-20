#!/usr/bin/env python3
"""Tap, swipe and type on an Android phone through Pocket Link's HID interface, from a PC over adb.

The Pocket app must be installed on the phone with Pocket Link on; it turns these commands into HID reports
(see PROTOCOL.md, packet 0x04) and the adapter presents them as a touch screen and keyboard.

  python3 tools/link_input_bench.py <adb serial> size
  python3 tools/link_input_bench.py <adb serial> tap x=600 y=1300
  python3 tools/link_input_bench.py <adb serial> swipe x=610 y=2200 x2=610 y2=900 ms=350 [fling=true]
  python3 tools/link_input_bench.py <adb serial> hold x=610 y=1600 ms=900
  python3 tools/link_input_bench.py <adb serial> type "text=hello नमस्ते"
  python3 tools/link_input_bench.py <adb serial> key name=home      # home back recents enter tab ctrl+a ...
  python3 tools/link_input_bench.py <adb serial> raw hex=0300000     # a report as the adapter sees it

Coordinates are screenshot pixels. The phone's window focus before and after is printed with each result.
Only adb (or the system) can send these: the app's receiver requires the DUMP permission.
"""
import re, shlex, subprocess, sys, time

SERIAL = sys.argv[1]
ACTION = "expo.modules.pocketphone.LINK_BENCH"


def adb(*args, timeout=30):
    return subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout).stdout


def bench(op, **kw):
    cmd = ["shell", "am", "broadcast", "-a", ACTION, "--es", "op", op]
    for k, v in kw.items():
        if isinstance(v, bool):
            cmd += ["--ez", k, "true" if v else "false"]
        elif isinstance(v, int):
            cmd += ["--ei", k, str(v)]
        else:
            cmd += ["--es", k, str(v)]
    t0 = time.time()
    out = adb("shell", " ".join(shlex.quote(c) for c in cmd[1:]), timeout=90)
    m = re.search(r'data="([^"]*)"', out)
    return (m.group(1) if m else out.strip()), int((time.time() - t0) * 1000)


def focus():
    out = adb("shell", "dumpsys", "window", "windows")
    m = re.search(r"mCurrentFocus=Window\{[^ ]+ u0 ([^}]+)\}", out)
    return m.group(1) if m else "?"


if __name__ == "__main__":
    op = sys.argv[2]
    args = {}
    for a in sys.argv[3:]:
        k, _, v = a.partition("=")
        args[k] = v if not re.fullmatch(r"-?\d+", v) else int(v)
        if v in ("true", "false"):
            args[k] = v == "true"
    before = focus()
    r, ms = bench(op, **args)
    time.sleep(0.8)
    print(f"{r} ({ms} ms round trip); focus {before} -> {focus()}")
