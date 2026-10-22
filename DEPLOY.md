# 部署到阿里云 ECS

本文按 **Ubuntu 22.04/24.04 + Docker Compose + 宿主机 Nginx** 的路线写。整套东西（PostgreSQL、FastAPI 后端、Vue 前端）都跑在 Docker 里，只有 Nginx 装在宿主机上负责 80/443 和 HTTPS。

## 0. 前置条件

- 一台阿里云 ECS：建议 **2 核 2G 起**、系统盘 40G、Ubuntu 22.04 或 24.04；
- 一个已解析到这台 ECS 公网 IP 的域名（A 记录）；
- 中国大陆地域的 ECS，用 80/443 对外提供网站需要域名已完成 **ICP 备案**；没备案时只能先用 SSH 隧道访问（见第 8 节）。

## 1. 先推到 GitHub

本地项目根目录：

```powershell
git add -A
git commit -m "套装成品图与 BOM、上传体验和部署配置"
git push origin master
```

仓库地址：`git@github.com:gaoxinlin12138/Pricing-system.git`

服务器上拉代码有两种方式，选一种：

**A. Deploy Key（推荐，只读）**

```bash
# 在服务器上生成密钥
ssh-keygen -t ed25519 -C "pricing-deploy" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

把输出的公钥贴到 GitHub 仓库 → Settings → Deploy keys → Add deploy key（不要勾选写权限）。然后在 `~/.ssh/config` 里加：

```
Host github.com
  IdentityFile ~/.ssh/github_deploy
```

**B. HTTPS + Personal Access Token**：`git clone https://github.com/gaoxinlin12138/Pricing-system.git`，用户名填 GitHub 用户名，密码填 PAT。

## 2. 安全组与登录

- 安全组**只放行**：22（最好限制为你的出口 IP）、80、443；
- **不要**放行 5432、8080；
- 用 SSH 密钥登录，禁用密码登录（可选但强烈建议）。

## 3. 安装 Docker

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 重新登录一次让用户组生效
docker --version && docker compose version
```

如果拉镜像很慢，可以配置阿里云容器镜像加速（控制台 → 容器镜像服务 → 镜像加速器，把地址写进 `/etc/docker/daemon.json` 后 `sudo systemctl restart docker`）。

内存只有 1G 的话，先加 2G swap，否则前端构建可能被 OOM 杀掉：

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 4. 拉代码并写生产配置

```bash
sudo mkdir -p /opt/pricing && sudo chown $USER:$USER /opt/pricing
git clone git@github.com:gaoxinlin12138/Pricing-system.git /opt/pricing
cd /opt/pricing

cp .env.production.example .env
openssl rand -hex 32          # 生成 SESSION_SECRET
nano .env
```

`.env` 至少要改这些：

```env
POSTGRES_PASSWORD=<长密码，建议只用字母数字>
SESSION_SECRET=<上面生成的 64 位十六进制>
COOKIE_SECURE=false           # 先 false，配好 HTTPS 再改 true
INITIAL_ADMIN_PASSWORD=<管理员初始密码>
INITIAL_EMPLOYEE_PASSWORD=<员工初始密码>
```

`.env` 已在 `.gitignore` 里，不会被提交；数据库密码故意只用字母数字，避免 URL 编码问题。

## 5. 启动

```bash
cd /opt/pricing
docker compose up -d --build
docker compose ps
curl -I http://127.0.0.1:8080
```

第一次启动时后端会自动执行 `alembic upgrade head` 建表，并在空库时用 `INITIAL_*_PASSWORD` 创建账号。

看日志：

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

## 6. 宿主机 Nginx + HTTPS

```bash
sudo apt install -y nginx
sudo cp deploy/nginx-pricing.conf.example /etc/nginx/conf.d/pricing.conf
sudo nano /etc/nginx/conf.d/pricing.conf   # 把 pricing.example.com 换成你的域名
sudo nginx -t && sudo systemctl reload nginx
```

先确认 `http://你的域名` 能打开，再申请证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
```

证书生效后，把 `.env` 的 `COOKIE_SECURE` 改成 `true`，重启后端：

```bash
cd /opt/pricing
sed -i 's/^COOKIE_SECURE=.*/COOKIE_SECURE=true/' .env
docker compose up -d backend
```

> 反过来：如果 `COOKIE_SECURE=true` 但还用 http 访问，会登录不上（浏览器不保存 cookie）。

## 7. 上线后立刻做的事

1. 用 `admin` + `INITIAL_ADMIN_PASSWORD` 登录，进「账号」把密码改成新的强密码，删掉或停用演示用的 `employee` 账号（或改密码给员工用）；
2. 「计价参数」核对倍率、人工费、税率、运费、最低售价、最大折扣；
3. 建一个真实的套装并上传成品图，用员工账号走一遍搜索 → 替换 → 确认 → 保存；
4. 确认备份任务已配（第 9 节）。

## 8. 没有域名/备案时怎么先看效果

CORS 不用改（同源访问）。临时用 SSH 隧道即可，不要把 8080 暴露到公网：

```bash
# 在你自己的电脑上执行
ssh -L 8080:127.0.0.1:8080 root@ECS公网IP
# 然后本地浏览器打开 http://127.0.0.1:8080
```

## 9. 备份

数据库和图片是两份数据，都要备。建议放 `/opt/pricing-backup` 并定期拉到本地或 OSS。

```bash
mkdir -p /opt/pricing-backup

# 数据库
docker compose exec -T db pg_dump -U pricing pricing | gzip > /opt/pricing-backup/pricing-$(date +%F).sql.gz

# 图片（在 /opt/pricing 下执行，卷名是 pricing_pricing-data）
docker run --rm -v pricing_pricing-data:/data -v /opt/pricing-backup:/backup alpine \
  tar czf /backup/uploads-$(date +%F).tgz -C /data uploads
```

crontab 每天凌晨 3 点：

```cron
0 3 * * * cd /opt/pricing && docker compose exec -T db pg_dump -U pricing pricing | gzip > /opt/pricing-backup/pricing-$(date +\%F).sql.gz
10 3 * * * cd /opt/pricing && docker run --rm -v pricing_pricing-data:/data -v /opt/pricing-backup:/backup alpine tar czf /backup/uploads-$(date +\%F).tgz -C /data uploads
```

恢复：

```bash
gunzip -c /opt/pricing-backup/pricing-2026-10-22.sql.gz | docker compose exec -T db psql -U pricing -d pricing
docker run --rm -v pricing_pricing-data:/data -v /opt/pricing-backup:/backup alpine sh -c "cd /data && tar xzf /backup/uploads-2026-10-22.tgz"
```

## 10. 更新代码

```bash
cd /opt/pricing
git pull
docker compose up -d --build
docker compose ps
```

后端容器启动时会自动跑数据库迁移，不用手动执行 alembic。

## 11. 排障

| 现象 | 排查 |
|---|---|
| 502 Bad Gateway | `docker compose ps` 看 backend 是否起来、`logs backend` 是否有迁移错误 |
| 登录后马上又回登录页 | `COOKIE_SECURE` 与访问协议不一致（http 配了 true，或 https 配了 false） |
| 图片 404 | 检查 `docker compose logs frontend` 与容器内 nginx 是否代理了 `/uploads/`（本仓库的 `infra/nginx.conf` 已包含） |
| 构建卡住/被杀 | 内存不足，加 swap 或换 2G 以上实例 |
| 数据库连不上 | `.env` 的密码是否含特殊字符、是否与旧数据卷里的密码一致（改过密码要进容器 `ALTER USER`） |
| 页面能开但接口 404 | 宿主机 Nginx 是否整体反代到 `127.0.0.1:8080`（不要只代理 `/`） |

## 12. 可选升级

- **数据库换阿里云 RDS**：把 `.env` 里的连接串改成 RDS 地址即可（同时删掉 compose 里的 db 服务）；
- **图片放 OSS**：需要把上传接口改成 OSS SDK 或加一层反向代理，目前是本地卷 `pricing-data`；
- **HTTPS 用阿里云证书**：在控制台申请证书后把 `.pem/.key` 放到 `/etc/nginx/cert/`，手写 443 server 块，效果和 certbot 一样。
