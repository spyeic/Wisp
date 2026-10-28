# Wisp

私人图片解题 Bot：在 iPhone 上直接发送照片、截图或图片文件，自动用所选 AI 服务（OpenAI / DeepSeek）分析，每题先写答案、紧接必要步骤，合并为一份回复。默认英文，保留 Watch Mode 的简短段落与纯文本格式。普通文字自动作为追问，不需要 `/analyze`、`/solve`、菜单或确认。

Python 3.11+，异步 python-telegram-bot + OpenAI Python SDK + Responses API。使用 Long Polling；Mac 能访问 Telegram 和所选 AI 服务即可，不需要数据库、域名、公网 IP 或入站端口。

## 日常使用

1. 打开自己的 Telegram Bot 私聊，发送一张题目图片。
2. Bot 自动处理。等待期间可能显示 typing，不会先发猜测答案。
3. 整份答案和必要步骤合并在一条消息中，每题只出现一次。
4. 只有超过 Telegram 的 4096 长度限制时才拆分（程序保守按 UTF-16 单位计算），优先保持题目完整。
5. 直接发送 `Explain question 3.`、`Why is the answer B?`、`请用中文解释第二步` 等文字继续提问。

单题示例（仅示意排版，不代表实际求解结果）：

```text
Answer: x = 5
1. 2x + 3 = 13
2. 2x = 10
3. x = 5
```

多题按题号组织，每题的答案与解释紧挨在一起。简单题可以只给答案：

```text
Answers:
1. A
2. C
3. B
4. D
5. A
```

不再发送“汇总一遍、解释再一遍”的两轮内容，也不再按 250 / 600 字符拆分。超出 Telegram 上限时才拆消息，不丢弃内容。使用纯文本、`x^2`、`sqrt(x)`、`(a+b)/(c+d)` 和 `dy/dx`；无需 Telegram Markdown 或 LaTeX 渲染。

## macOS 安装

### 1. Python 环境

如果已安装 Homebrew：

```bash
brew install python@3.11
```

也可以使用 [Python 官方 macOS 安装包](https://www.python.org/downloads/macos/)。确认执行的是 Python 3.11 或以上；部分 Mac 的 `python3` 仍是旧版。

在项目目录中运行：

```bash
cd /Users/eric/Projects/others/Wisp
python3.11 --version
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

本项目在这台 Mac 中已经建立 `.venv` 并安装依赖；可直接激活后配置。复制或移动项目到另一台电脑时重新建立虚拟环境，不要复制 `.venv`。如果 `.env` 已存在，不要再次运行 `cp` 覆盖密钥。

### 2. 创建 Telegram Bot 和获取 Token

1. 在 Telegram 打开官方 [@BotFather](https://t.me/BotFather)，核对账号。
2. 发送 `/newbot`，按提示设置显示名称和以 `bot` 结尾的用户名。
3. BotFather 返回 Bot Token。将它填写到本地 `.env` 的 `TELEGRAM_BOT_TOKEN=` 后面。
4. 打开新 Bot 的链接，首次点一次 Start，以建立私聊。之后日常直接发图片或文字即可。

创建流程见 [Telegram 官方教程](https://core.telegram.org/bots/tutorial)。Token 只填入本地 `.env`，不要发到聊天、截图、Git 仓库或公开日志。如果泄露，通过 BotFather 撤销并更新。

### 3. 获取自己的 Telegram User ID（一次性）

填好 Telegram Token 后，在项目目录运行：

```bash
source .venv/bin/activate
python bot.py --show-user-id
```

向自己的 Bot 私聊发送任意文字。Bot 会回复数字 User ID，终端也只输出这个 ID。按 Ctrl+C 停止此模式，将你的 ID 填入 `.env`：

```dotenv
ALLOWED_USER_IDS=123456789
```

允许多人时用逗号分隔，例如 `123456789,987654321`。这是数字 User ID，不能填写 `@username`。此设置模式只调用 Telegram，不读取题目做分析，也不需要 OpenAI Key。正常运行时，非白名单用户不能调用 AI；非白名单用户点 Start 只会收到自己的 ID 和访问受限提示。

### 4. 获取 AI API Key（默认 OpenAI）

在 [OpenAI API 平台](https://platform.openai.com/) 登录，为项目创建 [API Key](https://platform.openai.com/api-keys)，确认项目具备 API 额度和所选模型访问权限，填入 `.env` 的 `OPENAI_API_KEY=`。设置步骤参见 [官方 Quickstart](https://developers.openai.com/api/docs/quickstart)。本地配置检查不能验证额度或模型权限。

默认 OpenAI 的最小 `.env` 配置（DeepSeek 配置见下方“切换 AI 服务”）：

```dotenv
TELEGRAM_BOT_TOKEN=你的真实TelegramToken
AI_PROVIDER=openai
OPENAI_API_KEY=你的真实OpenAIKey
OPENAI_MODEL=gpt-5.4-2026-03-05
ALLOWED_USER_IDS=你的数字UserID
MAX_HISTORY_MESSAGES=10
DEFAULT_LANGUAGE=en
DEFAULT_MODE=watch
```

请替换示意值。`.env` 已被 `.gitignore` 排除。程序总是从 `bot.py` 所在目录读取 `.env`；已导出的同名环境变量优先于 `.env`。

### 5. 启动

```bash
source .venv/bin/activate
python bot.py --check-config
python bot.py
```

`--check-config` 只验证本地配置，不联网，不证明密钥有效。正常启动后保持终端和 Mac 运行。按 Ctrl+C 停止。同一 Token 只运行一个 polling 进程；先关闭 User ID 设置进程或其他 Bot 实例，再运行正常服务。

### 6. iPhone 验收

- 场景 A：直接发送一张清楚的英文数学题截图，不带 Caption，确认自动收到一条包含英文答案和必要步骤的完整回复。
- 场景 B：发送含 5 道选择题的单张图片，确认每题只出现一次，答案后紧接该题必要解释；答案必须以实际图片为准。
- 场景 C：紧接着发送 `Explain question 3.`，确认无需再次上传图片就能追问。
- 场景 D：在 iPhone 发送后锁屏，在 Apple Watch 查看答案通知。
- 文件测试：通过 Telegram 附件入口把 PNG、JPEG 或 WebP 作为 File / Document 发送，同样会自动处理。界面名称随 Telegram 版本可能不同。
- Caption 测试：图片附带 `Please answer in Chinese.`，确认语言跟随本次要求。
- 失败测试：模糊或裁掉条件的图片应指出缺失信息；损坏文件、动画、超限图片在调用 AI 前拒绝。

## Apple Watch 设置与实际限制

本项目发送普通 Telegram 文本消息，手表端使用 iPhone 通知镜像，不需要本项目安装 watchOS App，也不依赖第三方手表 Telegram 客户端。

1. 在 iPhone「设置 → 通知 → Telegram」开启通知和合适的预览权限。
2. 在 Telegram 中确认该 Bot 私聊没有被静音。
3. 打开 iPhone 的 Watch App →「我的手表 → 通知」，在镜像 iPhone 提醒的列表中启用 Telegram（若列出）。
4. 确认 Apple Watch 已佩戴、解锁、连接正常，iPhone 联网，专注模式没有屏蔽 Telegram。
5. 发送题目后锁定 iPhone，再观察手表通知；需要时点开通知或打开通知中心查看后续步骤。

Apple 官方说明：通知通常出现在 iPhone 或 Watch 其中之一；iPhone 解锁时通常显示在手机，手机锁屏且手表解锁时通常显示在手表。第三方 App 的通知需要配对 iPhone 联网。参见 [Apple Watch 通知说明](https://support.apple.com/en-us/108369)。

**实际可读范围由系统通知决定。** Telegram / watchOS 可能折叠多条通知、隐藏预览或仅突出最新一条，Bot 无法保证每个片段都自动完整展开，也无法提供原生手表聊天记录浏览。可在手表通知中心查看，完整记录始终在 iPhone Telegram。程序保持答案优先并将消息间隔设为至少 1 秒，不能控制操作系统的展示策略。

## 切换 AI 服务：OpenAI / DeepSeek

修改 `.env` 中的 `AI_PROVIDER`，重启 Bot 即可切换。只要求所选服务的 Key，另一家的 Key 可以留空，也可以保留以便切回。当前默认仍是 `openai`；添加支持不会自动把消息发给 DeepSeek。

使用 DeepSeek：

```dotenv
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeekAPIKey
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_REASONING_EFFORT=high
```

在 [DeepSeek API 平台](https://platform.deepseek.com/) 创建 Key，填写本地 `.env`。不要把 OpenAI Key 填入 `DEEPSEEK_API_KEY`。当前官方文档中 `deepseek-flash` 对应 DeepSeek V4.1 Flash，支持图片、Responses API 和结构化输出，适用于本项目的图片解题及连续追问。见 [DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/) 与 [Responses API 文档](https://api-docs.deepseek.com/api/create-response/)。图片直接发送给所选服务，不经过另一家识图，也不增加 OCR 调用。

`DEEPSEEK_REASONING_EFFORT` 可设 `none`、`low`、`high`、`max`；留空使用服务默认行为。默认 `high` 保留认真解题的倾向，但未做真实题库对比，不能保证与 GPT-5.4 一样准确。两个服务共用 `MAX_OUTPUT_TOKENS=16000`、`REQUEST_TIMEOUT_SECONDS=240` 等限额。

还可选择 `DEEPSEEK_MODEL=deepseek-v4-pro` 处理纯文字，但官方列为不支持图片。若当前消息或保留的历史有图片，程序会在 API 调用前明确拒绝，不丢图强行回答，也不自动转发给 OpenAI。图片题请用 `deepseek-flash`。不使用已停用的 `deepseek-chat` / `deepseek-reasoner` 名称。能力与价格见 [DeepSeek 模型文档](https://api-docs.deepseek.com/quick_start/pricing/)。

切回 OpenAI 只需要改为：

```dotenv
AI_PROVIDER=openai
```

已有 `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_REASONING_EFFORT` 会重新生效。两家独立计费，OpenAI 的数据共享免费额度不适用于 DeepSeek。

修改保存后，在运行终端按 Ctrl+C，再执行：

```bash
python bot.py --check-config
python bot.py
```

配置检查和启动日志会显示当前 provider / model，不显示密钥。重启会清空内存上下文；切换后请重新发送需要追问的原图。`.env` 是启动时读取，修改后不会热切换。若终端已经导出同名变量，它们仍优先于 `.env`。

服务地址在程序中固定为 OpenAI 官方 `https://api.openai.com/v1` 和 DeepSeek 官方 `https://api.deepseek.com`，不读取 `OPENAI_BASE_URL` 来改变路由。DeepSeek 请求不继承 OpenAI 的组织和项目请求头；任何服务调用失败都不会自动转发给另一家。

两家共用异步 `responses.parse` 和相同输出格式，不增加依赖。OpenAI 显式传 `store=False`；DeepSeek 官方 Responses API 本身无状态，因此省略不支持的 `store` 参数。上下文仍由本地内存管理。见 [DeepSeek Responses 兼容说明](https://api-docs.deepseek.com/guides/responses_api/)。

本次接入使用 Mock 验证，没有调用真实 DeepSeek API。实际可用性仍取决于你的账户、额度与网络。

## OpenAI 模型、API 与费用

默认 `gpt-5.4-2026-03-05`（GPT-5.4 固定版本）。按正确率优先，在用户提供的免费额度模型列表中选用 GPT-5.4，启用 `reasoning.effort=high`，生成预算 16000 token、请求超时 240 秒。相比原配置，复杂题可能需要更长等待和更多 token。这是工程选型，不代表已在实际题库上证明它优于列表中的每个模型。该模型支持图片输入、Responses API 和 Structured Outputs，见 [官方模型页面](https://developers.openai.com/api/docs/models/gpt-5.4)。

截图中的优惠是“符合条件的数据共享流量免费”，不是模型本身永久免费。截图所示 GPT-5.4 所在组共享每日 250000 token 额度；第二组的 2500000 token 不能拿来抵扣 GPT-5.4 的超额使用。需要在平台为 Wisp 项目启用输入/输出共享并确认已加入优惠，且账户需有正余额。共享数据可能用于模型改进与训练；程序不会替用户更改这个隐私选项。超过额度或不符合条件的请求仍会按标准价格计费。固定版本在官方优惠列表中，但账户实际资格与使用情况必须在平台核实。见 [官方数据共享优惠说明](https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai)。

本程序没有跨账户的每日免费额度计数或用尽自动停机功能，也不会自动降级到 mini / nano；不要把它当作零费用保证。`store=False` 不是加入数据共享优惠的开关。此次改动仅进行了离线配置与 Mock 测试，没有发起真实 API 请求。

要更换模型，修改 `OPENAI_MODEL` 后重启。选择同时支持图像输入、Responses API 和结构化输出的模型；查阅 [当前模型目录](https://developers.openai.com/api/docs/models)。复杂题可以试用更强模型，并增加超时和输出预算。若模型不支持 `reasoning` 参数，设置 `OPENAI_REASONING_EFFORT=` 留空以省略；否则填写该模型支持的级别。项目不会在失败时自动切换模型或重复计费调用。

实现使用 `AsyncOpenAI.responses.parse(..., text_format=Solution)`，图像通过内存中的 Base64 data URL 作为 `input_image` 输入，`detail=high`。一次调用返回所有答案及必要解释，再在本地拆分；不额外做 OCR 调用，不使用旧式 ChatCompletion 接口。依据：[图片输入文档](https://developers.openai.com/api/docs/guides/images-vision)、[Structured Outputs 文档](https://developers.openai.com/api/docs/guides/structured-outputs)。

程序不启用额外工具、不执行图片中的代码、不浏览外部网页。AI 可能误读图片或算错，结构化输出仅约束数据格式，不能证明答案正确。精细图表、超长证明、复杂代码或很多题可能超出一次调用的预算；应裁剪清晰、按题分批发送。`MAX_OUTPUT_TOKENS` 包含模型的推理预算，过低可能导致无完整答案；程序不会发送被截断的结果。

每次追问都会重发保留的文字和图片上下文，因此也消耗输入额度。裁剪无关背景、减少保留图片、合理缩短上下文可控制费用。最新价格以 [官方定价页](https://developers.openai.com/api/docs/pricing) 为准。

## 配置参考

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 必填 | Telegram Token |
| `AI_PROVIDER` | `openai` | `openai` / `deepseek`，重启生效 |
| `OPENAI_API_KEY` | 条件必填 | 选择 OpenAI 时必填 |
| `DEEPSEEK_API_KEY` | 条件必填 | 选择 DeepSeek 时必填 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 图片 + 文字；另支持纯文字 `deepseek-v4-pro` |
| `DEEPSEEK_REASONING_EFFORT` | `high` | `none` / `low` / `high` / `max`，留空使用服务默认 |
| `ALLOWED_USER_IDS` | 必填 | 数字 ID 白名单；空值拒绝启动 |
| `OPENAI_MODEL` | `gpt-5.4-2026-03-05` | 图片输入 + 结构化输出模型 |
| `MAX_HISTORY_MESSAGES` | `10` | 历史 user + assistant 消息数，不含当前请求；按完整问答对淘汰，奇数向下取偶数 |
| `MAX_HISTORY_CHARS` | `48000` | 历史文字字符上限，不计算 Base64；超限删除最老问答对 |
| `MAX_HISTORY_IMAGES` | `1` | 历史中保留的最近图片数；另加当前请求图片，设 0 则不保留旧图 |
| `HISTORY_TTL_SECONDS` | `1800` | 每条问答的最长保留时间，默认 30 分钟 |
| `DEFAULT_LANGUAGE` | `en` | 无附加说明时默认语言，可选 `en` / `zh` |
| `DEFAULT_MODE` | `watch` | 始终启用 Watch Mode |
| `MAX_IMAGE_MB` | `10` | 单张图片字节上限，允许 1–20 MiB |
| `MAX_IMAGE_PIXELS` | `25000000` | 防止超大尺寸图片占用过多解码内存 |
| `MAX_TEXT_CHARS` | `6000` | 单条文字 / Caption 字符上限 |
| `REQUESTS_PER_MINUTE` | `6` | 每人 60 秒滑动窗口限额，失败尝试也计入 |
| `REQUEST_TIMEOUT_SECONDS` | `240` | 单次 AI 请求总超时 |
| `MAX_OUTPUT_TOKENS` | `16000` | 单次生成预算（包含推理 token） |
| `OPENAI_REASONING_EFFORT` | `high` | 可留空以省略 reasoning 参数 |
| `MESSAGE_INTERVAL_MS` | `1100` | 后续消息的发送间隔；至少 1000 毫秒 |

语言由系统提示词约束：英文题 / 无 Caption 图片默认英文；中文题允许中文；本次明确要求的语言优先；英文追问用英文，中文追问用中文。可自动测试请求中的语言规则和输出格式，但没有真实模型调用时无法证明模型每次都会遵守。

## 隐私、上下文和可靠性

- 只处理白名单用户的私聊，不在群组、频道调用 AI；每个用户的记忆、速率限制和处理锁独立。
- 普通照片取最高分辨率；Document 同时检查 MIME / 扩展名候选和真实图像内容。支持 PNG、JPEG、WebP、非动画 GIF；HEIC 需先转为 JPEG，不接受 PDF。
- 图片仅在进程内存中下载、验证、传给所选 AI 服务，程序不写原图到磁盘。iPhone EXIF 旋转信息会正确应用。
- 默认保留最近 5 轮问答和最近 1 张图片；轮数、字数、图片数、TTL 中任一限制都可能提前淘汰内容。不额外调用模型总结历史。
- 超限图片会从旧轮次中删除并替换为缺失标记。淘汰问答时整对删除，避免截断公式；单个问答大于字数预算时可能无法保留。长时间或很多轮后追问，可能需要重发原图。
- 每次读取 / 写入清理过期历史；空闲时每 60 秒清理，清理精度最多约一分钟。重启丢失全部内存上下文。可选 `/reset` 立即清理本人的记忆；日常不需要任何命令。
- OpenAI 使用 `store=False`，DeepSeek 使用无状态 Responses API；请求仍会发送到所选服务，这不等于承诺供应商零保留。Telegram 本身也会处理并保存消息。
- 同一用户顺序处理，追问会等待前一个答案完成；每人最多 3 个进行中 / 等待中的请求，多余请求提示稍后重发。不同用户可并发，整体最多 8 个 update handler。
- 已见消息按 `(chat_id, message_id)` 去重，忽略编辑消息；最多记录 10000 条 / 24 小时。故意重新发送同一张图视为新请求。去重是进程内机制，不能承诺跨重启严格一次执行。
- 启动时丢弃停机期间积压的 Telegram updates，避免重启后意外集中计费。**Bot 未运行时发的图片可能不会处理，启动后请重新发送。** 多图相册按每张图片独立处理，不合并为一次模型调用；连续页或高频相册可能触发限流，建议逐张发送并等待。
- 网络、超时、拒答、无有效输出、截断结果都有简短错误提示。AI SDK 自动重试关闭；超时不代表服务端没有发生费用。需要重试时由用户重新发送。
- Telegram 明确返回 RetryAfter 时只重试消息发送一次；不重新生成 AI 答案。不确定的网络发送失败不会盲目重发，避免重复通知，可能留下部分已发送答案。
- 每条到达 Bot 的私聊消息都会记录 `Message received from_id=... chat_id=... message_id=... type=... allowed=...`，在白名单检查与消息处理之前记录；未授权用户、命令和不支持的消息也可看到接收记录。`allowed=False` 表示不允许调用 AI，收到消息不等于已完成解题。完成日志会带同一发送者 ID 和消息 ID。日志不打印正文、Caption、文件名、图片、HTTP URL、Token 或 API Key。不应自行打开 SDK / HTTP 调试日志。

Telegram 的标准 Bot 文件下载上限是 20 MB；本项目默认再限制为 10 MiB。下载前检查 Telegram 文件大小，下载后检查真实大小并限制接收缓冲区；PTB 的 HTTP 层可能先在内存中接收响应，不能将应用层限制理解为零瞬时额外内存。见 [python-telegram-bot File 文档](https://docs.python-telegram-bot.org/en/stable/telegram.file.html)。

## 持续运行

本地测试期间可阻止 Mac 因空闲进入睡眠：

```bash
cd /Users/eric/Projects/others/Wisp
caffeinate -i .venv/bin/python bot.py
```

关闭终端会停止；合上笔记本盖、断网、断电或主动睡眠仍可能中断服务。可接电并保持 Mac 唤醒。需要关闭终端后继续运行时：

```bash
cd /Users/eric/Projects/others/Wisp
nohup caffeinate -i .venv/bin/python bot.py > bot.log 2>&1 &
echo $!
```

记下输出的 PID，停止时运行 `kill 该PID`。查看日志用 `tail -f bot.log`。后台方式不会在重启后自动恢复；长期使用可自行配置 macOS LaunchAgent 启动同一虚拟环境中的 `bot.py`。不要同时运行前台和后台实例。

以后迁移到常开的 Linux / Docker 主机时仍可用同样的 Long Polling 程序和环境变量，不需要公网入站端口。容器本身不会让已睡眠的 Mac 保持在线。

## 自动化测试

```bash
cd /Users/eric/Projects/others/Wisp
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
```

测试用假 Token / Key，主动阻断 socket 外网连接，不消耗 API 额度，覆盖：

- 真实 Telegram Update 对象的普通照片 / Document 识别和处理器路由。
- PNG / JPEG / WebP / GIF 内容验证、大小与尺寸限制、EXIF 方向、动画和损坏图片。
- 默认英文请求、Caption 透传和中英文追问规则。
- 单条合并回复、每题答案紧接解释、中文输出、仅超 Telegram 上限拆分、emoji 和代码缩进保留。
- 按用户隔离、完整问答淘汰、图片保留和 TTL 清理。
- 白名单、私聊限制、重复消息、编辑消息、速率与待处理队列限制。
- 同一用户的图片与后续文字顺序处理。
- API 超时、HTTP 401 / 429 / 500、网络失败、拒答、无效 / 未完成输出，及 Telegram 下载 / 发送失败。
- 实际安装的 OpenAI SDK 经 `httpx.MockTransport` 验证两家服务的请求地址、独立密钥、JSON Schema、图像 data URL、store 参数差异与结果解析。
- DeepSeek 图片历史追问、纯文字模型拒绝图片、推理内容不显示、缺少所选服务密钥时拒绝启动。
- 图片 → 多题答案 → 第三题追问的完整模拟流程。

**验证范围：本项目已完成离线自动化测试；本地密钥配置已通过格式检查，但本次改动没有执行真实 Telegram ↔ AI 服务端到端测试，也没有在实体 Apple Watch 上验证通知。** 填好密钥后按上面的 iPhone 验收步骤验证实际效果。

## 排错

| 现象 | 检查 |
| --- | --- |
| 发图完全没回复 | 是否私聊、ID 是否在白名单、Mac 是否唤醒、进程是否运行；重启前发送的图请重发 |
| `Conflict` / 409 | 是否有同一个 Token 的另一个 polling 进程、设置模式或 webhook；停掉冲突实例 |
| `InvalidToken` / 401 | 检查 Telegram Token 是否复制完整；AI 服务错误则检查所选 provider 对应的 API Key |
| AI 服务拒绝请求 | 检查模型访问权限、API 额度、模型是否支持 reasoning / Structured Outputs |
| 回复未完成或超时 | 单次少发几题，必要时调高输出预算 / 超时，不会自动发送部分答案 |
| 图片字体看不清 | 裁剪题目，发送清晰原图，或以 Document 发送以减少 Telegram 压缩 |
| 追问忘记图片 | 超过轮数、字数、图片数或时间限制，或服务重启；重新发送图片 |
| Watch 没有通知 | 先锁 iPhone，再检查 Watch 解锁、Telegram 私聊静音、通知镜像、预览和专注模式 |

## 文件结构

```text
Wisp/
  bot.py                  # Telegram 私聊处理、异步调度、错误处理、启动入口
  ai_client.py            # OpenAI / DeepSeek Responses API、语言和解题提示词
  config.py               # .env 配置验证
  conversation.py         # 有限内存上下文与 TTL
  formatting.py           # 结构化结果、答案优先和文本拆分
  images.py               # 图片识别、下载、内容验证
  guards.py               # 去重与速率限制
  requirements.txt
  requirements-dev.txt
  .env.example
  .gitignore
  pytest.ini
  README.md
  tests/
```
