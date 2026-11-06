---
name: douyin-tiktok-download
description: 下载抖音（Douyin）或 TikTok 的无水印视频、图集、音频到本地。当用户提供抖音或 TikTok 链接、短链（如 v.douyin.com、vt.tiktok.com）、或含有链接的 App 分享文案，并要求下载、保存到本地时触发此 skill。通过 Douyin_TikTok_Download_API REST API 解析并流式保存资源。首次使用时会向用户询问服务地址与 API Key 并自动生成配置。
---

# 抖音 / TikTok 视频与图集下载技能

通过 `Douyin_TikTok_Download_API` 服务的 REST API 将抖音和 TikTok 的无水印视频、图集相册或背景音乐下载并持久化保存到本地文件系统。

## 可移植性约定（务必遵守）

- **唯一配置源是技能根目录下的 `config.json`**，不读取任何环境变量，不依赖用户主目录、注册表或系统级路径。
- **技能文件与代码中禁止出现任何硬编码绝对路径**。技能根目录是「本 `SKILL.md` 所在的目录」；脚本内部由自身位置推导该目录，与当前工作目录、盘符、安装位置无关。技能目录整体搬到任何路径下都可直接运行。
- 命令示例中的脚本路径一律是相对路径，执行前把工作目录切到技能根目录，或从当前目录用相对路径指向 `scripts/download.py`。
- 支持 Windows / Linux / macOS：脚本只用 Python 3 标准库，路径用 `pathlib` 处理，文件名按 Windows 规则净化，配置文件读取兼容 UTF-8 BOM。

执行脚本**无需 `pip install` 任何依赖**。Python 解释器命令按系统选择：Linux / macOS 用 `python3`，Windows 用 `python` 或 `py -3`（下例统一写 `python3`）。

---

## 配置文件

技能根目录下的 `config.example.json` 是模板，会随技能分发；技能根目录下的 `config.json` 是真实配置，**已被 `.gitignore` 忽略，禁止加入版本管理**。

```json
{
  "base_url": "http://192.168.1.100:8000",
  "api_key": "dtk_xxxxx"
}
```

| 字段 | 说明 |
|---|---|
| `base_url` | API 服务基础地址，必须是 `http://` 或 `https://` 开头，末尾斜杠自动忽略 |
| `api_key` | 拥有 `douyin:read` / `tiktok:read` 或 `admin` 范围的 API Key |

- 文件必须是合法 JSON 对象（UTF-8），不支持注释；包含密钥，Linux / macOS 下生成后应 `chmod 600 config.json`，Windows 下依赖用户目录 ACL，不要把技能目录放在公共可写位置。
- **分发或复制技能目录给别人时必须排除 `config.json`**，否则会把密钥一起带出去。用 rsync 时通过 `--exclude-from` 指定排除清单。
- 本技能绝不预置任何默认请求地址或 Key。

---

## 常用命令

以下路径均相对技能根目录。

### 0. 检查配置是否有效（Agent 每次执行下载前先做这一步）

```bash
python3 scripts/download.py --check-config
```

返回 `{"configured": true, "config_file": "config.json"}` 表示配置有效；`configured` 为 `false` 时会附带 `reason`。此命令**只报告状态，不输出 API Key**。

### 1. 基础下载（视频或图集）

自动解析链接（支持短链、原始长链接、或 App 复制的一整段分享文字），将无水印媒体保存到 `./downloads`：

```bash
python3 scripts/download.py "https://v.douyin.com/xxxxxx/"
```

### 2. 指定下载输出目录

```bash
python3 scripts/download.py "https://v.douyin.com/xxxxxx/" -o ./my-videos
```

### 3. 同时保存封面、原声音频与元数据

```bash
python3 scripts/download.py "https://v.douyin.com/xxxxxx/" \
  -o ./downloads --save-cover --save-music --save-meta
```

### 4. JSON 格式输出（供自动化工具解析）

```bash
python3 scripts/download.py "https://v.douyin.com/xxxxxx/" --json
```

---

## 命令行参数一览

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `url` | - | *(下载时必填)* | 视频链接或包含链接的分享文本 |
| `--check-config` | - | `False` | 只检查配置是否有效并输出 JSON 状态，不下载、不泄露密钥 |
| `--output-dir` | `-o` | `./downloads` | 文件保存目录 |
| `--save-cover` | - | `False` | 是否同时下载高清封面图 |
| `--save-music` | - | `False` | 是否同时下载背景音乐/音频（MP3） |
| `--save-meta` | - | `False` | 是否保存作品的完整 JSON 元数据文件 |
| `--json` | - | `False` | 控制台以标准 JSON 结构输出下载结果 |

---

## Agent 执行指引

在代表用户执行下载任务时，**严格按以下顺序执行**：

1. **定位技能根目录**：本 `SKILL.md` 所在目录即技能根目录。用相对路径调用脚本，不要写死绝对路径。
2. **先检查有没有有效的配置文件**：运行 `python3 scripts/download.py --check-config`。
   - `configured: true` → 直接进入第 5 步，**不要再向用户索要配置**。
   - `configured: false` → 进入第 3 步。
   - 若 `reason` 提示 JSON 解析失败或文件损坏，先向用户确认是否覆盖现有 `config.json`，避免丢失已有内容；得到许可后再重写。
3. **向用户提问**：一次问清两项，不要猜、不要填模板里的示例值、不要引导用户去设置环境变量：
   - API 服务地址（`base_url`，例如 `http://<主机>:8000`）
   - API Key（`api_key`）
   
   同时告知用户：这两个值会明文保存在技能根目录的 `config.json` 中，该文件已被 `.gitignore` 忽略。
4. **根据用户的回答自动生成并写入配置文件**：在技能根目录写入 `config.json`，内容为合法 JSON 对象，仅含 `base_url` 与 `api_key` 两个字段，UTF-8 编码、缩进 2 空格，不加注释。例如：
   ```json
   {
     "base_url": "<用户提供的地址>",
     "api_key": "<用户提供的 Key>"
   }
   ```
   写入后确认该文件已被 `.gitignore` 忽略；Linux / macOS 下执行 `chmod 600 config.json`。再次运行 `--check-config` 确认 `configured: true` 后再继续。
5. **提取与过滤输入**：从用户输入中提取分享链接，或直接将整段文案传给脚本（脚本内置 URL 提取器）。
6. **执行下载**：运行 `python3 scripts/download.py "<URL>" [选项]`（Windows 换用 `python` / `py -3`）。
7. **汇报结果**：简洁呈现平台与作者名、作品标题、本地保存路径与文件大小。**不要把 API Key 回显到对话中**。

---

## 常见错误排查

| 错误 | 原因 | 解决方法 |
|---|---|---|
| `未找到配置文件 config.json` | 首次使用或配置文件被删除 | 按 Agent 执行指引第 3~4 步，向用户收集信息后生成配置文件 |
| `配置项无效: base_url / api_key 缺失` | 字段缺失、为空或地址格式不对 | 向用户重新确认两个值并重写 `config.json` |
| `config.json 不是合法 JSON` | 手改时写了注释、尾逗号或用了全角引号 | 向用户确认后按标准 JSON 重写，可参考 `config.example.json` |
| `Warning: config.json 对其他用户可读` | POSIX 权限过宽 | 在技能根目录执行 `chmod 600 config.json` |
| `UNAUTHENTICATED` | API Key 错误或在服务端已被撤销 | 检查 Key，必要时重新生成并更新 `config.json` |
| `FORBIDDEN_SCOPE` | API Key 缺少对应平台的只读权限 | 在控制台生成具备 `douyin:read` / `tiktok:read` 的 Key |
| `INVALID_URL` | 链接格式不受支持，或域名不在白名单内 | 确认提供的是合法的抖音/TikTok 分享链接 |
| `CONTENT_PRIVATE` | 视频已被作者删除或设为私密 | 无法公开访问 |
| `IDENTITY_POOL_EXHAUSTED` | 部署服务端当前无可用身份且自动铸造未就绪 | 检查服务端 `browser-rpc` 容器或手动导入有效 Cookie |
| `HTTP 502 / 504 (TikTok)` | 部署服务端直连海外受限 | 在服务端为 TikTok 配置可用代理 |
