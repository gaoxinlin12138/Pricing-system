"""星瀑花洒计价平台一键启动器。

右键运行本文件后：
1. 自动选择已安装后端依赖的 Python（优先 backend/.venv）；
2. 隐藏输入 PostgreSQL 密码（可事先写进项目根目录 .env）；
3. 检查并创建数据库，执行 Alembic 数据库迁移；
4. 启动 FastAPI 后端（端口被占用时自动顺延）；
5. 首次运行自动安装前端依赖并启动 Vue 前端；
6. 按 Ctrl+C 同时停止前后端。

密码只在当前进程内存中使用，不会写入项目文件。
"""

from __future__ import annotations

import getpass
import os
import secrets
import socket
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
FRONTEND_PORT = 5173


ENSURE_DATABASE_SCRIPT = r"""
import os
import sys

from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

url = os.environ["DATABASE_URL"]
parts = urlsplit(url.replace("postgresql+psycopg", "postgresql", 1))
dbname = parts.path.lstrip("/") or "postgres"
admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, ""))

try:
    conn = psycopg.connect(admin_url, autocommit=True, connect_timeout=8)
except psycopg.Error as exc:
    print("无法连接 PostgreSQL：%s" % exc)
    sys.exit(2)

try:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            print("已自动创建数据库：%s" % dbname)
        else:
            print("数据库 %s 已存在。" % dbname)
except psycopg.Error as exc:
    print("检查数据库时出错：%s" % exc)
    sys.exit(3)
finally:
    conn.close()
"""


def enable_utf8_output() -> None:
    """统一控制台编码，避免 Windows 代码页把中文打成乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def venv_python() -> Path:
    if os.name == "nt":
        return BACKEND / ".venv" / "Scripts" / "python.exe"
    return BACKEND / ".venv" / "bin" / "python"


def choose_python() -> list[str]:
    """选择包含后端依赖的 Python；优先项目自带的 .venv。"""
    candidates: list[list[str]] = []
    if venv_python().exists():
        candidates.append([str(venv_python())])
    candidates.append([sys.executable])
    if os.name == "nt":
        candidates.append(["py", "-3"])
    candidates.append(["python"])

    probe = "import sqlalchemy, alembic, uvicorn, psycopg, fastapi"
    for command in candidates:
        try:
            result = subprocess.run(
                [*command, "-c", probe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            if result.returncode == 0:
                return command
        except (OSError, subprocess.SubprocessError):
            continue
    raise RuntimeError(
        "没有找到已安装后端依赖的 Python。\n"
        "请先执行：\n"
        "  cd backend\n"
        "  py -m venv .venv\n"
        "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    )


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


def apply_common_environment(env: dict[str, str]) -> dict[str, str]:
    # 未配置时为当前进程生成随机密钥，绝不使用源码中的固定密钥。
    if not env.get("SESSION_SECRET", "").strip():
        env["SESSION_SECRET"] = secrets.token_urlsafe(32)
    env.setdefault("COOKIE_SECURE", "false")

    upload_dir = Path(env.get("UPLOAD_DIR") or BACKEND / "uploads")
    if not upload_dir.is_absolute():
        upload_dir = ROOT / upload_dir
    env["UPLOAD_DIR"] = str(upload_dir)

    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def make_environment() -> dict[str, str]:
    env = load_local_environment()
    database_url = env.get("DATABASE_URL", "").strip()
    if database_url and "请填写" not in database_url and "在这里填写" not in database_url:
        env["DATABASE_URL"] = normalize_database_url(database_url)
        return apply_common_environment(env)

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
    return apply_common_environment(env)


def run_database_check(env: dict[str, str], python_command: list[str]) -> None:
    """数据库不存在时自动创建，避免首次启动卡在迁移失败。"""
    url = env.get("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        return
    print("正在检查数据库……", flush=True)
    result = subprocess.run(
        [*python_command, "-c", ENSURE_DATABASE_SCRIPT],
        env=env,
        cwd=BACKEND,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "数据库检查失败：请确认 PostgreSQL 服务已启动，且账号密码有权限访问。\n"
            "      也可以把连接串写进项目根目录的 .env，例如：\n"
            "      DATABASE_URL=postgresql+psycopg://postgres:你的密码@127.0.0.1:5432/pricing"
        )


def run_migrations(env: dict[str, str], python_command: list[str]) -> None:
    print("正在检查并执行数据库迁移……", flush=True)
    result = subprocess.run(
        [*python_command, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError("数据库迁移失败，具体原因见上方 alembic 输出的错误信息。")


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(host: str, preferred: int, attempts: int = 20) -> int:
    for port in range(preferred, preferred + attempts):
        if port_is_free(host, port):
            return port
    raise RuntimeError(f"{preferred} 起连续 {attempts} 个端口都被占用，请先关闭占用端口的程序。")


def start_backend(env: dict[str, str], python_command: list[str], port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            *python_command,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(port),
        ],
        cwd=BACKEND,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def find_npm() -> str:
    npm = which("npm.cmd") or which("npm")
    if not npm:
        raise RuntimeError("没有找到 npm，请先安装 Node.js（https://nodejs.org）后重试。")
    return npm


def ensure_frontend_dependencies(env: dict[str, str]) -> None:
    if (FRONTEND / "node_modules").exists():
        return
    print("首次运行：正在安装前端依赖（npm install），可能需要几分钟……", flush=True)
    result = subprocess.run(
        [find_npm(), "install", "--no-fund", "--no-audit"],
        cwd=FRONTEND,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError("前端依赖安装失败，请检查网络后重新运行。")


def start_frontend(env: dict[str, str], port: int) -> subprocess.Popen:
    frontend_env = env.copy()
    # 前端只需要 API 地址，不应继承数据库连接密码。
    for secret_key in ("DATABASE_URL", "PRICING_DB_PASSWORD"):
        frontend_env.pop(secret_key, None)
    frontend_env["VITE_API_TARGET"] = f"http://{BACKEND_HOST}:{env['BACKEND_PORT']}"
    return subprocess.Popen(
        [find_npm(), "run", "dev", "--", "--host", BACKEND_HOST, "--port", str(port), "--strictPort"],
        cwd=FRONTEND,
        env=frontend_env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def wait_for_url(process: subprocess.Popen, url: str, label: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label}启动失败，退出码：{process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.4)
    raise TimeoutError(f"{label}启动超时，请查看窗口中的错误信息。")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        # npm / uvicorn 都会再启动子进程，只结束父进程会留下占用端口的孤儿进程。
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
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
    enable_utf8_output()
    backend = None
    frontend = None
    try:
        print("正在检查 Python 依赖……", flush=True)
        python_command = choose_python()
        print(f"使用 Python：{python_command[0]}", flush=True)

        print("正在读取 .env 配置……", flush=True)
        env = make_environment()

        run_database_check(env, python_command)
        run_migrations(env, python_command)

        backend_port = pick_port(BACKEND_HOST, BACKEND_PORT)
        if backend_port != BACKEND_PORT:
            print(f"端口 {BACKEND_PORT} 已被占用，后端改用 {backend_port}。", flush=True)
        env["BACKEND_PORT"] = str(backend_port)
        backend = start_backend(env, python_command, backend_port)
        wait_for_url(
            backend,
            f"http://{BACKEND_HOST}:{backend_port}/api/auth/me",
            "后端",
            timeout=20,
        )

        frontend_port = pick_port(BACKEND_HOST, FRONTEND_PORT)
        if frontend_port != FRONTEND_PORT:
            print(f"端口 {FRONTEND_PORT} 已被占用，前端改用 {frontend_port}。", flush=True)
        ensure_frontend_dependencies(env)
        frontend = start_frontend(env, frontend_port)
        wait_for_url(frontend, f"http://{BACKEND_HOST}:{frontend_port}/", "前端", timeout=60)

        print("\n项目已启动：")
        print(f"网页地址：http://{BACKEND_HOST}:{frontend_port}/")
        if env.get("APP_ENV", "").strip().lower() in {"production", "prod"}:
            print("后端生产文档已关闭。")
        else:
            print(f"后端文档：http://{BACKEND_HOST}:{backend_port}/docs")
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
