"""Read-only companion to scripts/verify_live.py: process memory/FDs/children, disk, DB size, crash reports.
Usage: python -I resource_sampler.py SECONDS OUTPUT.json   (no network beyond nothing; uses ps/lsof/df only)"""
import json, os, subprocess, sys, time, glob
from datetime import datetime, timezone

ROOT = "/Users/qusaial-duaij/Desktop/Dira"
REPORTS = [os.path.expanduser("~/Library/Logs/DiagnosticReports"), os.path.expanduser("~/Library/Logs/DiagnosticReports/Retired")]

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def procs():
    rows = []
    for line in sh(["ps", "-axo", "pid=,ppid=,rss=,%cpu=,command="]).splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5: continue
        pid, ppid, rss, cpu, cmd = parts
        kind = ("api" if "uvicorn dira.api" in cmd else "asr" if "whisperlivekit.basic_server" in cmd
                else "ocr" if "dira.ocr_worker" in cmd else "ffmpeg" if cmd.startswith("ffmpeg") and "127.0.0.1:8554" in cmd else None)
        if kind: rows.append({"pid": int(pid), "ppid": int(ppid), "rss_mb": round(int(rss) / 1024), "cpu": float(cpu), "kind": kind})
    return rows

def crash_reports():
    return sorted(os.path.basename(p) for d in REPORTS for p in glob.glob(d + "/Python*.ips"))

def main(seconds, output):
    start, samples, baseline = time.monotonic(), [], crash_reports()
    while True:
        ps = procs()
        api = next((p for p in ps if p["kind"] == "api"), None)
        fds = len(sh(["lsof", "-p", str(api["pid"])]).splitlines()) - 1 if api else None
        st = os.statvfs(ROOT)
        db = sum(os.path.getsize(f) for f in glob.glob(ROOT + "/.data-live/evidence.db*"))
        samples.append({
            "at": datetime.now(timezone.utc).isoformat(), "elapsed": round(time.monotonic() - start),
            "disk_free_gb": round(st.f_bavail * st.f_frsize / 2**30, 2), "evidence_db_mb": round(db / 2**20, 1),
            "api_fds": fds, "processes": ps,
            "new_crash_reports": [r for r in crash_reports() if r not in baseline],
        })
        with open(output, "w") as f:
            json.dump({"baseline_crash_reports": baseline, "samples": samples}, f)
        if time.monotonic() - start >= seconds: break
        time.sleep(60)

if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
