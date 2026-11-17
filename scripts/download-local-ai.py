"""Download the pinned official Ollama archive in resumable HTTP ranges."""
import concurrent.futures
import hashlib
import pathlib
import subprocess
import time
import winreg

ROOT = pathlib.Path(__file__).resolve().parents[1]
URL = "https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-windows-amd64.zip"
SIZE = 1618244995
SHA256 = "50fcf5ad54277f2fa5d173ebfc93bcb017adbc0c9ef2314daabc96ca9e6aa64e"
OUTPUT = ROOT / "tools" / "ollama-windows-amd64-verified.zip"
PARTS = ROOT / "tools" / "ollama-download-parts"


def proxy_args():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
        try:
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            server = winreg.QueryValueEx(key, "ProxyServer")[0]
            if enabled and server == "127.0.0.1:7890":
                return ["--proxy", "http://127.0.0.1:7890"]
        except FileNotFoundError:
            pass
    return []


def download(part):
    start = SIZE * part // 12
    end = SIZE * (part + 1) // 12 - 1
    target = PARTS / f"{part:02d}.part"
    have = target.stat().st_size if target.exists() else 0
    if have == end - start + 1:
        return target
    legacy = target.with_suffix('.downloading')
    if legacy.exists() and legacy.stat().st_size == end-start+1:
        legacy.replace(target)
        return target
    segments = []
    for segment, first in enumerate(range(start, end + 1, 8 * 1024 * 1024)):
        last = min(first + 8 * 1024 * 1024 - 1, end)
        partial = PARTS / f"{part:02d}-{segment:02d}.segment"
        if not partial.exists() or partial.stat().st_size != last-first+1:
            for attempt in range(6):
                result = subprocess.run(["curl.exe", *(proxy_args() if attempt % 2 == 0 else []), "--silent", "--show-error", "--location", "--fail",
                    "--connect-timeout", "30", "--max-time", "90", "--range", f"{first}-{last}",
                    "--output", str(partial), f"{URL}?segment={part}-{segment}-{attempt}"])
                if result.returncode == 0 and partial.stat().st_size == last-first+1:
                    break
                time.sleep(2)
            else:
                raise RuntimeError(f"Official download failed for part {part}/{segment}")
        segments.append(partial)
    with target.open("wb") as output:
        for partial in segments:
            with partial.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    return target


def main():
    PARTS.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download, part) for part in range(12)]
        while not all(f.done() for f in futures):
            total = sum(min(p.stat().st_size, SIZE // 12 + 1) for p in PARTS.glob('*.part'))
            print(f"Official runtime download: {total / SIZE:.1%}", flush=True)
            time.sleep(10)
        paths = [future.result() for future in futures]
    digest = hashlib.sha256()
    with OUTPUT.open("wb") as output:
        for path in paths:
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError("Official archive SHA-256 mismatch; do not execute")
    print(f"Verified official archive: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
