"""星瀑花洒计价平台一键启动器。

右键运行本文件后：
1. 隐藏输入 PostgreSQL 密码；
2. 执行 Alembic 数据库迁移；
3. 启动 FastAPI 后端；
4. 启动 Vue 前端；
5. 按 Ctrl+C 同时停止前后端。

密码只在当前进程内存中使用，不会写入项目文件。
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from shutil import which
from urllib.parse import quote, unquote


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
CONFIG_FILE = ROOT / ".env"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8001


def choose_python() -> list[str]:
    """选择包含后端依赖的 Python；兼容 PyCharm 使用未安装依赖的 .venv。"""
    candidates: list[list[str]] = [[sys.executable]]
    if os.name == "nt":
        candidates.append(["py", "-3"])
    candidates.append(["python"])
    probe = "import sqlalchemy, alembic, uvicorn"
    for command in candidates:
        try:
            result = subprocess.run(
                [*command, "-c", probe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if result.returncode == 0:
                return command
        except (OSError, subprocess.SubprocessError):
            continue
    raise RuntimeError("没有找到已安装 SQLAlchemy、Alembic 和 Uvicorn 的 Python。请先安装 backend/requirements.txt。")


def load_local_environment() -> dict[str, str]:
    """读取项目根目录的可编辑配置，不依赖第三方 dotenv 包。"""
    env = os.environ.copy()
    if not CONFIG_FILE.exists():
        return env
    for raw_line in CONFIG_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            env[key] = value
    return env


def normalize_database_url(value: str) -> str:
    """允许 .env 中直接填写原始密码，并自动编码 URL 特殊字符。"""
    if "://" not in value or "@" not in value:
        return value
    scheme, remainder = value.split("://", 1)
    user_info, endpoint = remainder.rsplit("@", 1)
    if ":" not in user_info:
        return value
    user, raw_password = user_info.split(":", 1)
    password = unquote(raw_password)
    return f"{scheme}://{user}:{quote(password, safe='')}@{endpoint}"


def make_environment() -> dict[str, str]:
    env = load_local_environment()
    database_url = env.get("DATABASE_URL", "").strip()
    if database_url and "请填写" not in database_url and "在这里填写" not in database_url:
        env["DATABASE_URL"] = normalize_database_url(database_url)
        env.setdefault("SESSION_SECRET", "local-development-change-me")
        env.setdefault("COOKIE_SECURE", "false")
        env.setdefault("UPLOAD_DIR", str(BACKEND / "uploads"))
        return env

    password = env.get("PRICING_DB_PASSWORD", "").strip()
    if not password or password.startswith("请在这里"):
        password = getpass.getpass("请输入 PostgreSQL 密码（输入不会显示）：")
    if not password:
        raise RuntimeError("密码不能为空。")

    user = env.get("PRICING_DB_USER", "postgres")
    host = env.get("PRICING_DB_HOST", "127.0.0.1")
    port = env.get("PRICING_DB_PORT", "5432")
    database = env.get("PRICING_DB_NAME", "pricing")
    encoded_password = quote(password, safe="")

    env["DATABASE_URL"] = (
        f"postgresql+psycopg://{user}:{encoded_password}@{host}:{port}/{database}"
    )
    env.setdefault("SESSION_SECRET", "local-development-change-me")
    env.setdefault("COOKIE_SECURE", "false")
    env.setdefault("UPLOAD_DIR", str(BACKEND / "uploads"))
    return env


def run_migrations(env: dict[str, str], python_command: list[str]) -> None:
    print("正在检查并执行数据库迁移……", flush=True)
    subprocess.run(
        [*python_command, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=True,
    )


def start_backend(env: dict[str, str], python_command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [
            *python_command,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=BACKEND,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def start_frontend(env: dict[str, str]) -> subprocess.Popen:
    npm = which("npm.cmd") or which("npm") or "npm.cmd"
    frontend_env = env.copy()
    # 前端只需要 API 地址，不应继承数据库连接密码。
    frontend_env.pop("DATABASE_URL", None)
    frontend_env["VITE_API_TARGET"] = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
    return subprocess.Popen(
        [npm, "run", "dev", "--", "--host", BACKEND_HOST],
        cwd=FRONTEND,
        env=frontend_env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def wait_for_backend(process: subprocess.Popen, timeout: float = 20) -> None:
    url = f"http://{BACKEND_HOST}:{BACKEND_PORT}/openapi.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"后端启动失败，退出码：{process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.4)
    raise TimeoutError("后端启动超时，请查看后端窗口中的错误信息。")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def pause_after_error() -> None:
    try:
        input("\n按 Enter 键关闭窗口……")
    except EOFError:
        pass


def main() -> None:
    backend = None
    frontend = None
    try:
        print("正在读取 .env 配置……", flush=True)
        env = make_environment()
        python_command = choose_python()
        print("Python 依赖检查通过，准备启动后端……", flush=True)
        run_migrations(env, python_command)
        backend = start_backend(env, python_command)
        wait_for_backend(backend)
        frontend = start_frontend(env)

        print("\n项目已启动：")
        print("网页地址：http://127.0.0.1:5173/")
        print("后端文档：http://127.0.0.1:8001/docs")
        print("保持此窗口打开；按 Ctrl+C 可停止全部服务。\n")

        while True:
            if backend.poll() is not None:
                raise RuntimeError(f"后端已退出，退出码：{backend.returncode}")
            if frontend.poll() is not None:
                raise RuntimeError(f"前端已退出，退出码：{frontend.returncode}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止项目……")
    except Exception as exc:
        print(f"\n启动失败：{exc}")
        pause_after_error()
    finally:
        stop_process(frontend)
        stop_process(backend)


if __name__ == "__main__":
    main()
