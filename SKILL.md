---
name: douyin-tiktok-download
description: 下载抖音（Douyin）或 TikTok 的无水印视频、图集、音频到本地。当用户提供抖音或 TikTok 链接、短链（如 v.douyin.com、vt.tiktok.com）、或含有链接的 App 分享文案，并要求下载、保存到本地时触发此 skill。通过 Douyin_TikTok_Download_API REST API 解析并流式保存资源。
---

# 抖音 / TikTok 视频与图集下载技能

通过 `Douyin_TikTok_Download_API` 服务的 REST API 将抖音和 TikTok 的无水印视频、图集相册或背景音乐下载并持久化保存到本地文件系统。

## 前置环境要求

**本技能严格通过环境变量获取 API 地址与密钥，绝不预置任何默认请求地址或 Key：**

| 环境变量名 | 描述 | 示例 |
|---|---|---|
| `DTK_BASE_URL` | 部署的 API 服务基础地址（末尾斜杠自动忽略） | `http://192.168.1.100:8000` |
| `DTK_API_KEY` | 拥有 `douyin:read` / `tiktok:read` 或 `admin` 范围的 API Key | `dtk_0a1b2c3d4e5f_...` |

*(注：亦可使用别名 `DOUYIN_TIKTOK_API_BASE` 与 `DOUYIN_TIKTOK_API_KEY`)*

若调用时缺少任一变量，脚本将直接退出并提示配置方法。

---

## 定位技能目录

本文件所在的目录即为技能根目录 `$SKILL_DIR`：

```bash
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

执行脚本完全采用 Python 3 标准库，**无需 `pip install` 任何额外依赖**。

---

## 常用命令

### 1. 基础下载（视频或图集）

自动解析链接（支持短链、原始长链接、或 App 复制的一整段分享文字），将无水印媒体保存到 `./downloads` 目录：

```bash
python3 "$SKILL_DIR/scripts/download.py" "https://v.douyin.com/xxxxxx/"
```

### 2. 指定下载输出目录

```bash
python3 "$SKILL_DIR/scripts/download.py" "https://v.douyin.com/xxxxxx/" -o "/path/to/save"
```

### 3. 同时保存封面、原声音频与元数据

```bash
python3 "$SKILL_DIR/scripts/download.py" "https://v.douyin.com/xxxxxx/" \
  -o "./downloads" \
  --save-cover \
  --save-music \
  --save-meta
```

### 4. JSON 格式输出（供自动化工具解析）

```bash
python3 "$SKILL_DIR/scripts/download.py" "https://v.douyin.com/xxxxxx/" --json
```

---

## 命令行参数一览

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `url` | - | *(必填)* | 视频链接或包含链接的分享文本 |
| `--output-dir` | `-o` | `./downloads` | 文件保存目录 |
| `--save-cover` | - | `False` | 是否同时下载高清封面图 |
| `--save-music` | - | `False` | 是否同时下载背景音乐/音频（MP3） |
| `--save-meta` | - | `False` | 是否保存作品的完整 JSON 元数据文件 |
| `--json` | - | `False` | 控制台以标准 JSON 结构输出下载结果 |

---

## Agent 执行指引

在代表用户执行下载任务时，请遵循以下流程：

1. **检查环境变量**：
   优先检查当前环境是否已设置 `DTK_BASE_URL` 与 `DTK_API_KEY`。
   若未配置，**主动向用户提示**：
   ```bash
   export DTK_BASE_URL="http://<你的服务地址>:8000"
   export DTK_API_KEY="dtk_<你的密钥>"
   ```
2. **提取与过滤输入**：
   从用户的输入内容中提取分享链接或直接将整段文案传给脚本（脚本内置 URL 提取器）。
3. **执行下载**：
   运行 `python3 "$SKILL_DIR/scripts/download.py" "<URL>" [选项]`。
4. **汇报结果**：
   向用户简洁呈现下载结果，包含：
   - 平台与作者名
   - 视频/作品标题
   - 本地保存的绝对路径与文件大小

---

## 常见错误排查

| 错误码 | 原因 | 解决方法 |
|---|---|---|
| `Missing required environment variables` | 未配置 `DTK_BASE_URL` 或 `DTK_API_KEY` | 设置对应环境变量后再执行 |
| `UNAUTHENTICATED` | API Key 错误或在服务端已被撤销 | 检查 API Key 是否正确，或重新生成 Key |
| `FORBIDDEN_SCOPE` | API Key 缺少对应平台的只读权限 | 在控制台生成具备 `douyin:read` / `tiktok:read` 的 Key |
| `INVALID_URL` | 链接格式不受支持，或域名不在白名单内 | 确认提供的是合法的抖音/TikTok 分享链接 |
| `CONTENT_PRIVATE` | 视频已被作者删除或设为私密 | 无法公开访问 |
| `IDENTITY_POOL_EXHAUSTED` | 部署服务端当前无可用身份且自动铸造未就绪 | 检查服务端 `browser-rpc` 容器或手动导入有效 Cookie |
| `HTTP 502 / 504 (TikTok)` | 部署服务端直连海外受限 | 在服务端为 TikTok 配置可用代理 |
