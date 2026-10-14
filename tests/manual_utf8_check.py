import subprocess
import sys
import json

if __name__ == "__main__":
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from core.runtime import config

    if not config.AGENTAPI_EXE:
        raise SystemExit("请先在 .env 配置 AGENTAPI_EXE")
    prompt = "你好，请确认你的名字并用中文回答"
    res = subprocess.run([config.AGENTAPI_EXE, "agentapi", "new-conversation", "--model=flash", prompt], capture_output=True)
    print("RC:", res.returncode)
    try:
        data = json.loads(res.stdout.decode("utf-8"))
        print("Parsed JSON:", data)
    except Exception as e:
        print("Failed to parse:", e)
        print("Raw bytes:", res.stdout)
