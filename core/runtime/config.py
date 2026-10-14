"""Central configuration for MorningBriefAgent.

The project intentionally uses a tiny, dependency-free ``.env`` loader. Existing
process environment variables always win over values from the project ``.env``.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

def load_env_file(path: os.PathLike[str] | str = ENV_FILE) -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""
    env_path = Path(path)
    if not env_path.is_file():
        return
    try:
        with env_path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if value[:1] == value[-1:] and value.startswith(("'", '"')):
                    value = value[1:-1]
                if key:
                    os.environ.setdefault(key, value)
    except OSError as exc:
        print(f"⚠️ 加载 .env 异常: {exc}")


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default).replace(";", ",")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


load_env_file()

# Base paths
VAULT_ROOT = os.getenv("VAULT_ROOT", str(PROJECT_ROOT / "vault"))
WECHAT_TOOLS_DIR = os.getenv("WECHAT_TOOLS_DIR", "")
WECHAT_MSG_DB = os.getenv("WECHAT_MSG_DB", "")
WECHAT_CONTACT_DB = os.getenv("WECHAT_CONTACT_DB", "")
AGENTAPI_EXE = os.getenv("AGENTAPI_EXE", "")
AGY_BRAIN_DIR = os.getenv("AGY_BRAIN_DIR", "")
AGY_CONVERSATION_ID = os.getenv("AGY_CONVERSATION_ID", "")
LOCAL_PROXY = os.getenv("LOCAL_PROXY", "")
MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "https://hq.sinajs.cn")
PORTFOLIO_FILE = os.getenv("PORTFOLIO_FILE", str(PROJECT_ROOT / "data" / "portfolio.json"))
WECHAT_GROUP_KEYWORDS = _csv("WECHAT_GROUP_KEYWORDS")
WECHAT_EXCLUDED_USERNAMES = _csv("WECHAT_EXCLUDED_USERNAMES")
WECHAT_EXCLUDED_NAME_KEYWORDS = _csv("WECHAT_EXCLUDED_NAME_KEYWORDS")

# Configured local knowledge-base paths
EMAIL_INBOX_DIRS = _csv("EMAIL_INBOX_DIRS")
TECH_NEWS_DIR = os.getenv("TECH_NEWS_DIR", "")
NEWS_DOMESTIC_URLS = _csv("NEWS_DOMESTIC_URLS")
NEWS_WORLD_URLS = _csv("NEWS_WORLD_URLS")
NEWS_FALLBACK_LINK = os.getenv("NEWS_FALLBACK_LINK", "")
STUDY_TRACKER_PATH = os.getenv("STUDY_TRACKER_PATH", "")
TODAY_TODO_PATH = os.getenv("TODAY_TODO_PATH", "")
TODO_ARCHIVE_DIR = os.getenv("TODO_ARCHIVE_DIR", "")
REVIEW_DAILY_DIR = os.getenv("REVIEW_DAILY_DIR", "")
REVIEW_WEEKLY_DIR = os.getenv("REVIEW_WEEKLY_DIR", "")
REVIEW_MONTHLY_DIR = os.getenv("REVIEW_MONTHLY_DIR", "")
FITNESS_PLAN_PATH = os.getenv("FITNESS_PLAN_PATH", "")
FITNESS_LOG_PATH = os.getenv("FITNESS_LOG_PATH", "")
FITNESS_ARCHIVE_DIR = os.getenv("FITNESS_ARCHIVE_DIR", "")
CHAT_ARCHIVE_DIR = os.getenv("CHAT_ARCHIVE_DIR", "")
STAGED_PLAN_PATH = os.getenv(
    "STAGED_PLAN_PATH", str(PROJECT_ROOT / "data" / "staged_plan.json")
)
IDEMPOTENCY_STORE_PATH = os.getenv(
    "IDEMPOTENCY_STORE_PATH", str(PROJECT_ROOT / "data" / "idempotency.sqlite3")
)

# Feishu OpenAPI configuration. Credentials must never have source-code defaults.
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_USER_OPEN_ID = os.getenv("FEISHU_USER_OPEN_ID", "")
FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
FEISHU_ALLOWED_OPEN_IDS = _csv("FEISHU_ALLOWED_OPEN_IDS", FEISHU_USER_OPEN_ID)

EXAM_DATE_STR = os.getenv("EXAM_DATE_STR", "")
