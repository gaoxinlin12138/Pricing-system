# 星瀑花洒内部计价平台

一个面向公司内部的花洒组合计价 MVP。员工只能看到最终对外售价，管理员维护产品、配件和统一计价参数。

## 本地运行

### 后端（开发模式）

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

演示账号：

- 员工：`employee` / `employee123`
- 管理员：`admin` / `admin123`

## Docker 部署

```powershell
docker compose up -d --build
```

打开 `http://localhost:8080`。生产环境应在 Nginx 或云负载均衡器前配置 HTTPS，并替换演示密码。

Docker 部署使用 PostgreSQL，后端容器启动时执行 Alembic 迁移。正式环境请通过环境变量替换数据库密码、`SESSION_SECRET` 和 `COOKIE_SECURE`。

项目运行必须显式设置 `DATABASE_URL`；当前运行链路统一使用 PostgreSQL，不再自动回退到本地 SQLite 文件。测试会在测试环境中显式注入临时 SQLite 地址。

管理员后台包含计价参数、主体、配件、兼容规则、账号、报价和审计日志页；员工端支持报价详情、复制报价和过期状态。

配件类别字段已经内置到后台录入表单：杆子、中叉+墙座、喷头（手喷+顶喷）、电话线、手喷软管、喷枪、弯角角阀。选择类别后会显示对应的颜色、长度、形状、材质、档位等字段；属性值以结构化 JSON 保存，不参与员工端成本展示。

数据库迁移：

```powershell
cd backend
$env:DATABASE_URL="postgresql+psycopg://pricing:pricing@localhost:5432/pricing"
alembic upgrade head
```

本机已安装 PostgreSQL 时，推荐使用脚本自动创建 `pricing` 数据库并迁移：

```powershell
.\scripts\setup_local_postgres.ps1
```

脚本会隐藏式读取密码，只在当前进程使用，不会写入项目文件。

以后可以直接在项目根目录编辑标准 `.env` 文件，把 `DATABASE_URL` 改成你的 PostgreSQL 连接地址，然后右键运行 `启动.py`（也可以双击 `启动项目.bat`）。例如：

```env
DATABASE_URL=postgresql+psycopg://postgres:你的密码@127.0.0.1:5432/pricing
```

脚本会自动迁移数据库并启动前后端，不再每次询问密码。

启动后访问 `http://127.0.0.1:5173/`。启动窗口保持打开，按 `Ctrl+C` 可以停止对应服务。

备份脚本位于 `scripts/backup_postgres.ps1`。正式环境请将 `SESSION_SECRET` 替换为随机长密钥。

## 计价规则

```text
成本小计 = 主体成本 + 配件成本 × 数量 + 统一人工费
未税商品价 = 成本小计 × 统一倍率
折后未税商品价 = 未税商品价 - 折扣
税额 = 折后未税商品价 × 税率
最终售价 = 折后未税商品价 + 税额 + 运费
```

金额在后端使用 Decimal 计算并在最后保留两位小数。报价保存时写入价格快照，因此价格调整不会影响历史报价。

