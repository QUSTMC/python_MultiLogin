# MultiLogin Python

外置 Yggdrasil 认证服务，支持多个认证服务器共存。通过 [authlib-injector](https://github.com/yushijinhun/authlib-injector) 接入，Minecraft 服务器无需安装任何插件。

## 功能

- 多个 Yggdrasil 认证服务器共存（官方 Mojang、LittleSkin、自定义等）
- 回访玩家自动路由到上次认证源，新玩家按优先级顺序尝试
- **皮肤修复** — 通过 MineSkin API 重新签名皮肤，解决跨站皮肤显示问题
- Web 管理界面（中英文切换）
- 拖动排序认证服务器优先级
- 上游服务器连通性检测（在线/离线、延迟）
- 首次启动自动生成高强度 Access Key
- 配置文件与 Web UI 双向同步，热更新

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
  Access Key (first run): xK9...（你的 key）
  Admin URL: http://localhost:8080/admin/
============================================================
```

### 2. 配置认证服务器

浏览器打开 `http://你的IP:8080/admin/`，输入 Access Key 登录。

点击 **+ Add Server** 添加上游认证服务器：

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

## 皮肤修复

不同认证服务器的玩家之间可能无法看到对方的皮肤，这是因为部分皮肤站的皮肤纹理 URL 无效或使用了自定义签名机制。

本服务内置了基于 [MineSkin](https://mineskin.org/) 的皮肤修复功能，可以自动将非 Mojang 签名的皮肤重新签名。

### 配置方式

在 Web 管理界面的 **皮肤修复** 区域：

| 选项 | 说明 |
|------|------|
| 关闭 | 不修复皮肤 |
| 登录时（同步） | 阻塞登录直到修复完成，玩家立即看到正确皮肤 |
| 异步（后台） | 后台修复，本次登录可能看不到，下次登录可用缓存 |

| 方法 | 说明 |
|------|------|
| URL | MineSkin 直接从 URL 获取皮肤（快，但可能因网络问题失败） |
| 上传 | 先下载皮肤图片再上传到 MineSkin（可靠，推荐） |

已修复的皮肤会缓存到数据库，后续登录直接使用缓存，无需重复调用 API。

### 工作流程

```
玩家登录 → hasJoined 返回档案
  ↓
检查皮肤 URL 是否为非 Mojang 来源
  ↓
查询数据库缓存 → 有缓存则直接使用
  ↓
无缓存 → 调用 MineSkin API 修复
  ├─ URL 方式：MineSkin 从 URL 获取
  └─ 上传方式：先下载再上传（URL 方式失败时自动 fallback）
  ↓
缓存结果到数据库
  ↓
返回 Mojang 签名的皮肤数据
```

## 认证流程

```
客户端启动器
  │  authenticate (邮箱+密码)
  ▼
authlib-injector → 本服务 /authserver/authenticate
  │  并行查询所有上游服务器，返回第一个成功的结果
  │  记录 (玩家 → 认证源) 到数据库
  │
  │  join (加服)
  ▼
客户端 → 本服务 /sessionserver/session/minecraft/join
  │  根据缓存路由到正确的上游服务器
  │  记录 (serverId → 认证源) 到内存
  │
  │  hasJoined (服务端验证)
  ▼
MC 服务器 → 本服务 /sessionserver/session/minecraft/hasJoined
  │  根据缓存查询对应的上游服务器
  │  记录 (UUID → 认证源) 到数据库（用于皮肤查询）
  │  皮肤修复（如果启用）
  │
  │  profile (皮肤查询)
  ▼
MC 服务器 → 本服务 /sessionserver/session/minecraft/profile/<uuid>
  │  优先查数据库找到该 UUID 对应的上游服务器
  │  直接从正确的服务器获取皮肤数据
  │  皮肤修复（如果启用）
```

## 项目结构

```
python_MultiLogin/
├── app.py              # Flask 入口
├── config.py           # YAML 配置读写 + 热更新
├── database.py         # SQLite 数据库（玩家映射、UUID 映射、皮肤缓存）
├── auth_key.py         # Access Key 生成/验证
├── upstream.py         # 上游 Yggdrasil 异步调用 + URL 推导
├── skin_restorer.py    # 皮肤修复（MineSkin API 调用 + 缓存）
├── start.bat           # Windows 启动脚本
├── start.py            # 跨平台启动脚本
├── start.sh            # Linux/Mac 启动脚本
├── requirements.txt    # Python 依赖
├── .gitignore
├── routes/
│   ├── authserver.py   # /authserver/* 认证代理（authenticate/refresh/validate）
│   ├── session.py      # /sessionserver/* 会话路由（join/hasJoined/profile）
│   └── admin.py        # /admin/* 管理界面 API
└── templates/admin/
    ├── index.html      # 管理页面（拖动排序、状态检测、皮肤修复设置）
    └── login.html      # 登录页面
```

## 配置文件

`config.yml` 在首次运行时自动生成，也可手动编辑后重启：

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  access_key: "自动生成的 key"

skin_restorer: "off"        # off / login / async
skin_restorer_method: "url"  # url / upload

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

SQLite 自动创建于 `data/data.db`，包含四张表：

| 表 | 用途 |
|----|------|
| `player_service_map` | 玩家名 → 认证源映射（回访路由） |
| `uuid_service_map` | UUID → 认证源映射（跨站皮肤查询） |
| `in_game_profile` | 游戏内档案（UUID 策略） |
| `skin_cache` | 皮肤修复缓存（MineSkin 签名结果） |

## 依赖

- Python 3.10+
- Flask、aiohttp、PyYAML、ruamel.yaml

## 许可

MIT
