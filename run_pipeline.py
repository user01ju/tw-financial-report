# -*- coding: utf-8 -*-
"""一次跑完 backfill + metrics，給 detached 背景行程用。

由 Start-Process 啟動，獨立於 Claude session 存活。
backfill 可續跑(看實際檔案)，故就算中途被砍，重啟此腳本會自動接續。
"""
import subprocess
import sys
import time

PY = sys.executable


def run(args):
    print(f">>> {' '.join(args)}  @ {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    subprocess.run([PY, "-u", *args], check=True)


if __name__ == "__main__":
    run(["backfill_finmind.py", "--start", "2015-01-01"])
    run(["metrics.py"])
    print(f"=== PIPELINE DONE @ {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
