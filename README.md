# MultiLogin Python

外置 Yggdrasil 认证服务，支持多个认证服务器共存。通过 [authlib-injector](https://github.com/yushijinhun/authlib-injector) 接入，Minecraft 服务器无需安装任何插件。

## 功能

- 多个 Yggdrasil 认证服务器共存（官方 Mojang、LittleSkin、自定义等）
- 回访玩家自动路由到上次认证源，新玩家按优先级顺序尝试
- **皮肤修复** — 通过 MineSkin API 重新签名皮肤，解决跨站皮肤显示问题
- **重名处理** — 用户名永久绑定到首个 UUID，防止不同认证源的同名玩家冲突
- **玩家封禁** — 支持按用户名或 UUID 封禁，被封禁玩家无法登录
- Web 管理界面（中英文切换，顶部导航栏分 Tab）
- 拖动排序认证服务器优先级
- 上游服务器连通性检测（在线/离线、延迟）
- 首次启动自动生成高强度 Access Key
- 配置文件与 Web UI 双向同步，热更新
- 持久化事件循环 + 连接池，高性能异步请求

## 快速开始

### 1. 启动服务

```bash
# Windows
start.bat

# 跨平台
python start.py

# Linux/Mac
chmod +x start.sh && ./start.sh
```

首次启动会自动安装依赖并生成 Access Key，输出类似：

```
============================================================
  Access Key: xK9...（你的 key）
  Admin URL:  http://localhost:8080/admin/
============================================================
```

启动脚本自动检测 `waitress`（Windows/Linux/macOS）或 `gunicorn`（Linux/macOS），优先使用生产级服务器。

### 2. 配置认证服务器

浏览器打开 `http://你的IP:8080/admin/`，输入 Access Key 登录。

导航栏分为 5 个 Tab：

| Tab | 功能 |
|-----|------|
| **服务器设置** | 监听地址、端口 |
| **认证服务器** | 服务器列表管理、拖动排序、状态检测 |
| **皮肤修复** | MineSkin 皮肤修复模式和方法配置 |
| **重名管理** | 重名阻止开关、用户名-UUID 绑定管理 |
| **封禁管理** | 按用户名/UUID 封禁玩家 |
| **配置指南** | authlib-injector 配置说明 |

添加认证服务器时的参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| Name | 显示名称 | `LittleSkin` |
| hasJoined URL | 完整的 hasJoined 端点地址 | 见下方表格 |
| Priority | 优先级（数字越小越优先），支持拖动排序 | `1` |
| Timeout | HTTP 超时（毫秒） | `10000` |
| Track IP | 是否传递玩家 IP | `Yes` |
| UUID Strategy | 新玩家 UUID 策略 | `online` |

> **注意：** URL 必须包含完整的 `/sessionserver/session/minecraft/hasJoined` 路径。

### 3. 配置 Minecraft 服务器

下载 [authlib-injector](https://authlib-injector.yushi.moe/)，在服务器启动命令中添加：

```
-javaagent:authlib-injector.jar=http://你的服务IP:8080
```

重启服务器即可。

## 常见认证服务器 URL

| 服务 | hasJoined URL |
|------|---------------|
| Mojang 官方 | `https://sessionserver.mojang.com/session/minecraft/hasJoined` |
| LittleSkin | `https://littleskin.cn/api/yggdrasil/sessionserver/session/minecraft/hasJoined` |

其他 BlessingSkin 站点通常为：`https://站点地址/api/yggdrasil/sessionserver/session/minecraft/hasJoined`

## 认证流程

```
客户端启动器
  │  authenticate (邮箱+密码)
  ▼
authlib-injector → 本服务 /authserver/authenticate
  │  并行查询所有上游服务器，返回第一个成功的结果
  │  记录 (玩家 → 认证源) 到会话缓存
  │
  │  join (加服)
  ▼
客户端 → 本服务 /sessionserver/session/minecraft/join
  │  根据会话缓存路由到正确的上游服务器
  │  记录 (serverId → 认证源) 到内存
  │
  │  hasJoined (服务端验证)
  ▼
MC 服务器 → 本服务 /sessionserver/session/minecraft/hasJoined
  │  根据缓存查询对应的上游服务器
  │  检查封禁 → 检查重名绑定 → 创建绑定
  │  记录 (UUID → 认证源) 到数据库
  │  皮肤补充 + 皮肤修复（如果启用）
  │
  │  profile (皮肤查询)
  ▼
MC 服务器 → 本服务 /sessionserver/session/minecraft/profile/<uuid>
  │  优先查数据库找到该 UUID 对应的上游服务器
  │  直接从正确的服务器获取皮肤数据
  │  皮肤修复（如果启用）
```

## 已知问题：聊天签名错误

Minecraft 1.19+ 引入了聊天签名机制。当第三方验证服务器的玩家发送消息时，正版玩家可能看到"消息验证错误"。

**原因：** 第三方验证的玩家的聊天消息用非 Mojang 密钥签名，正版玩家客户端不信任该签名。

**解决方案（任选其一）：**

| 方案 | 说明 |
|------|------|
| 服务端配置 | `server.properties` 中设置 `enforce-secure-profile=false` |
| 服务端插件 | 安装 [NoChatReports](https://github.com/Aizistral-Studios/No-Chat-Reports) 插件 |
| 客户端 Mod | 玩家安装 NoChatReports 客户端 Mod |

推荐使用服务端配置方案，最简单且对所有玩家生效。

## 项目结构

```
python_MultiLogin/
├── app.py              # Flask 入口 + 事件循环启动
├── async_utils.py      # 持久事件循环 + run_async 封装
├── config.py           # YAML 配置读写 + 热更新
├── database.py         # SQLite 数据库（6 张表）
├── auth_key.py         # Access Key 生成/验证
├── session_store.py    # 会话缓存（token → 认证源）
├── upstream.py         # 上游 Yggdrasil 异步调用 + URL 推导 + 连接池
├── skin_restorer.py    # 皮肤修复（MineSkin API + 缓存）
├── start.bat           # Windows 启动脚本
├── start.py            # 跨平台启动脚本（自动检测 waitress/gunicorn）
├── start.sh            # Linux/Mac 启动脚本
├── requirements.txt    # Python 依赖
├── .gitignore
├── routes/
│   ├── authserver.py   # /authserver/* 认证代理
│   ├── session.py      # /sessionserver/* 会话路由
│   └── admin.py        # /admin/* 管理界面 API
└── templates/admin/
    ├── index.html      # 管理页面（Tab 导航）
    └── login.html      # 登录页面
```

## 配置文件

`config.yml` 在首次运行时自动生成，也可手动编辑后重启：

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  access_key: "自动生成的 key"

skin_restorer: "off"         # off / login / async
skin_restorer_method: "url"  # url / upload
allow_duplicate_names: false # true = 允许同名，false = 绑定用户名到首个 UUID

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

## 数据库

SQLite 自动创建于 `data/data.db`，包含六张表：

| 表 | 用途 |
|----|------|
| `player_service_map` | 玩家名 → 认证源映射（回访路由） |
| `uuid_service_map` | UUID → 认证源映射（皮肤查询） |
| `in_game_profile` | 游戏内档案（UUID 策略） |
| `skin_cache` | 皮肤修复缓存（MineSkin 签名结果） |
| `name_binding` | 用户名 → UUID 绑定（重名处理） |
| `bans` | 封禁列表（按用户名或 UUID） |

## 依赖

- Python 3.10+
- Flask、aiohttp、PyYAML、ruamel.yaml、waitress

## 许可

MIT
