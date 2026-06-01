# Python MultiLogin 外置认证服务 — 项目规划

## 概述

基于 MultiLogin（Java/Velocity 插件）的设计理念，开发一套 Python 语言的外置 Yggdrasil 认证服务。
通过 authlib-injector 接入，Minecraft 服务器仅需配置连接到此服务的 IP，即可实现多个 Yggdrasil 认证服务器共存。
带有 Web 管理界面，首次启动随机生成高强度 access key 输出到控制台。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 架构模式 | 自定义 Yggdrasil 认证服务器（authlib-injector 兼容） | 不需要实现 MC 协议代理，复杂度低 |
| 认证路由 | 回访玩家查库路由，新玩家按优先级顺序 | 回访玩家体验好，新玩家也能找到正确源 |
| 数据库 | SQLite | 零配置，适合小型/单机部署 |
| Web 框架 | Flask | 轻量成熟，简单直接 |
| 配置方式 | YAML 文件 + Web UI 双向同步 | 灵活，支持手动编辑和运行时修改 |
| 每服务器参数 | name, url, priority, enabled, timeout, track_ip, init_uuid | 覆盖常见场景 |
| API 端点 | 全部 Yggdrasil（auth server + session server） | authlib-injector 需要完整端点 |
| 会话跟踪 | 内存缓存 | 快速，重启丢失可接受 |
| 登录路由 | 并行尝试所有上游 | 简单直接 |
| Web UI 功能 | 仅管理上游认证服务器配置 | 保持简单 |
| 端口设计 | 同端口，不同路径 | 部署简单 |
| 配置热更新 | 立即生效（写 YAML + 更新内存） | 用户体验最好 |

## 项目目录结构

```
python_MultiLogin/
├── app.py                  # Flask 入口，启动服务
├── config.py               # YAML 配置读写 + 热更新
├── database.py             # SQLite 初始化 + 表操作
├── auth_key.py             # access key 生成/验证
├── upstream.py             # 上游 Yggdrasil 调用逻辑
├── requirements.txt        # 依赖清单
├── config.yml              # 配置文件（首次运行自动生成）
├── data.db                 # SQLite 数据库（自动创建）
├── PLAN.md                 # 本文件
├── routes/
│   ├── __init__.py
│   ├── authserver.py       # /authserver/* 路由（代理到上游）
│   ├── session.py          # /session/* 路由（join/hasJoined/profile）
│   └── admin.py            # /admin/* 路由（Web 管理界面）
└── templates/
    └── admin/
        └── index.html      # 管理界面模板
```

## 启动流程

1. 检查 `config.yml`，不存在则生成默认模板
2. 检查 access key，首次启动随机生成 32 字符高强度 key（`secrets.token_urlsafe(32)`），输出到控制台
3. 初始化 SQLite 数据库（创建表）
4. 加载配置到内存
5. 启动 Flask 服务（默认端口 `8080`）

## 认证流程

```
客户端 launcher
  │
  │ authenticate (邮箱+密码)
  ▼
authlib-injector → 你的服务(:8080)/authserver/authenticate
  │                    │
  │                    ├─ 并行发送到所有启用的上游服务器
  │                    ├─ 第一个成功的返回
  │                    └─ 记录 (username → service_id, accessToken) 到内存
  │
  │ 加入服务器
  ▼
MC 客户端 → MC 服务器 → 你的服务(:8080)/session/minecraft/hasJoined
                              │
                              ├─ 查内存 (serverId → service_id)
                              └─ 转发到对应上游服务器验证
```

### authenticate（登录）

1. 收到 `POST /authserver/authenticate`
2. 并行发送到所有启用的上游服务器
3. 第一个成功的返回，记录 `(username → service_id, accessToken)` 到内存
4. 同时更新数据库中的 `player_service_map`（回访路由用）

### join（加服）

1. 收到 `POST /session/minecraft/join`
2. 从内存查 `(username → service_id)`，转发到对应上游
3. 未找到则按优先级顺序尝试所有上游
4. 成功后记录 `(serverId → service_id)` 到内存

### hasJoined（服务端验证）

1. 收到 `GET /session/minecraft/hasJoined`
2. 从内存查 `(serverId → service_id)`，转发到对应上游
3. 返回验证结果

### profile（皮肤查询）

1. 收到 `GET /session/minecraft/profile/:uuid`
2. 并行查询所有上游，返回第一个有效结果

## Yggdrasil API 端点

### Auth Server（代理到上游）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/authserver/authenticate` | POST | 玩家登录 |
| `/authserver/refresh` | POST | 刷新会话 |
| `/authserver/validate` | POST | 验证会话 |
| `/authserver/invalidate` | POST | 注销会话 |
| `/authserver/signout` | POST | 登出 |

### Session Server（核心路由逻辑）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/session/minecraft/join` | POST | 客户端加入服务器 |
| `/session/minecraft/hasJoined` | GET | 服务端验证玩家 |
| `/session/minecraft/profile/:uuid` | GET | 皮肤档案查询 |

### Web 管理界面

| 路径 | 方法 | 说明 |
|------|------|------|
| `/admin/` | GET | 管理首页（需 access key） |
| `/admin/api/servers` | GET | 获取所有认证服务器 |
| `/admin/api/servers` | POST | 添加认证服务器 |
| `/admin/api/servers/<id>` | PUT | 修改认证服务器 |
| `/admin/api/servers/<id>` | DELETE | 删除认证服务器 |
| `/admin/api/servers/<id>/toggle` | POST | 启用/禁用 |

## 数据库设计

```sql
-- 玩家 → 认证源映射（回访路由）
CREATE TABLE player_service_map (
    username TEXT PRIMARY KEY,
    service_id INTEGER NOT NULL,
    online_uuid TEXT,
    last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 游戏内档案（UUID 策略）
CREATE TABLE in_game_profile (
    online_uuid TEXT NOT NULL,
    service_id INTEGER NOT NULL,
    in_game_uuid TEXT NOT NULL,
    in_game_name TEXT,
    PRIMARY KEY (online_uuid, service_id)
);
```

## 每个上游认证服务器的可配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | 显示名称 |
| `url` | string | hasJoined 端点完整 URL（必须包含 `/sessionserver/session/minecraft/hasJoined`） |
| `priority` | int | 优先级（数字越小越优先） |
| `enabled` | bool | 是否启用 |
| `timeout` | int | HTTP 请求超时（毫秒） |
| `track_ip` | bool | hasJoined 是否传递玩家 IP |
| `init_uuid` | enum | 新玩家 UUID 策略：`online` / `offline` / `random` |

## 配置文件示例（config.yml）

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  access_key: ""  # 首次启动自动生成

auth_servers:
  - name: "LittleSkin"
    url: "https://littleskin.cn/api/yggdrasil/sessionserver/session/minecraft/hasJoined"
    priority: 1
    enabled: true
    timeout: 10000
    track_ip: true
    init_uuid: "online"

  - name: "Mojang Official"
    url: "https://sessionserver.mojang.com/session/minecraft/hasJoined"
    priority: 2
    enabled: true
    timeout: 10000
    track_ip: true
    init_uuid: "online"
```

## 依赖清单

```
flask>=3.0
aiohttp>=3.9
pyyaml>=6.0
ruamel.yaml>=0.18
```

## 安全设计

- Access key 首次启动随机生成（`secrets.token_urlsafe(32)`），持久化到 `config.yml`
- 仅 `/admin/*` 路径需要 access key 认证
- Yggdrasil API 路径无额外认证（由 authlib-injector 协议本身保证）
- 生产环境建议放在反向代理（nginx）后面，限制管理端口访问

## 参考资料

- 原项目：`F:\WORKSPACE\MultiLogin`（Java/Velocity 实现）
- authlib-injector：https://github.com/yushijinhun/authlib-injector
- Yggdrasil 协议：https://github.com/yushijinhun/authlib-injector/wiki
