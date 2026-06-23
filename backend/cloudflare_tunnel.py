import re
import subprocess
import sys
import threading
from pathlib import Path

CLOUDFLARED_PATH = str(Path(__file__).parent / "tools" / "cloudflared-windows-amd64.exe")
LOCAL_URL = "http://localhost"

def _drain_stdout(process: subprocess.Popen):
    """URL 탐지 후에도 stdout을 계속 소비하여 cloudflared 프로세스가 블록되지 않도록 함."""
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
    except Exception:
        pass

def start_cloudflare_tunnel():
    cmd = [
        CLOUDFLARED_PATH,
        "tunnel",
        "--url",
        LOCAL_URL,
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    public_url = None

    # URL이 나타날 때까지 stdout을 읽음 (최대 60줄)
    for _, line in zip(range(60), process.stdout):
        print(line, end="", flush=True)

        match = re.search(r"https://[-a-zA-Z0-9]+\.trycloudflare\.com", line)
        if match:
            public_url = match.group(0)
            print("\nCloudflare Tunnel URL:", public_url, flush=True)
            break

    if not public_url:
        process.terminate()
        raise RuntimeError("Cloudflare Tunnel URL을 찾지 못했습니다.")

    # URL 발견 후 stdout을 백그라운드 스레드에서 계속 소비
    # (버퍼가 차서 cloudflared 프로세스가 멈추는 현상 방지)
    drain_thread = threading.Thread(target=_drain_stdout, args=(process,), daemon=True)
    drain_thread.start()

    return process, public_url


if __name__ == "__main__":
    process, url = start_cloudflare_tunnel()

    print("\nColab BACKEND_URL 에 아래 주소를 넣으세요:")
    print(url)

    try:
        process.wait()
    except KeyboardInterrupt:
        print("\nCloudflare Tunnel 종료")
        process.terminate()
        sys.exit(0)
