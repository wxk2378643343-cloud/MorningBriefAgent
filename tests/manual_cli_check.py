"""Manual Antigravity CLI smoke check. Run this file directly."""
import tempfile
import subprocess
import os

if __name__ == "__main__":
    prompt = "你好，请回复'AGY指令执行成功'"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as f:
        f.write(prompt)
        tmp_path = f.name.replace("\\", "/")

    script = f"""
$p = (Get-Content -Raw -Encoding UTF8 -Path '{tmp_path}').Trim()
agentapi new-conversation --model=flash $p
"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".ps1") as f:
        f.write(script)
        ps1_path = f.name.replace("\\", "/")

    res = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1_path], capture_output=True, text=True)
    print("RC:", res.returncode)
    print("OUT:", res.stdout)
    print("ERR:", res.stderr)
