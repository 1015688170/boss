# Boss AI Jobs

用途：用你自己的 Boss 直聘登录 Cookie 调搜索/详情接口，抓 AI 岗位信息，重点保存“岗位职责/任职要求”，并统计这些文本里重复出现的技能点。

脚本不处理验证码、登录、风控绕过；如果接口返回 `401/403/429`，需要刷新 Cookie 或降低频率。

## 安装

Linux：

```bash
python3 -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
pip install -r requirements.txt
```

## 最常用运行方式

Linux：

```bash
export BOSS_COOKIE='你的 Cookie'
python3 boss_ai_jobs.py -k 大模型 -k RAG -k AI运维 --city 101020100 --pages 5 --analyze
```

Windows PowerShell：

```powershell
$env:BOSS_COOKIE='你的 Cookie'
python .\boss_ai_jobs.py -k 大模型 -k RAG -k AI运维 --city 101020100 --pages 5 --analyze
```

这条命令的意思：用你的 Cookie 登录态，在上海搜索“大模型/RAG/AI运维”，每个关键词抓 5 页，抓完后打印薪资统计和岗位职责里的重复技能点。

## 抓“岗位职责”详情

列表接口不一定返回完整的岗位职责。要抓你截图里红框那块内容，需要加 `--detail-api-url`。

步骤：

1. 浏览器登录 Boss。
2. 打开开发者工具 `Network`，勾选 `Preserve log`。
3. 点开一个岗位详情。
4. 在 Network 里找详情接口，一般 Response 里能看到 `岗位职责/任职要求` 文本。
5. 复制这个接口 URL，把岗位 ID 那段替换成 `{encryptJobId}`。

示例：

```bash
export BOSS_COOKIE='你的 Cookie'
python3 boss_ai_jobs.py -k AI运维 --city 101020100 --pages 3 \
  --detail-api-url 'https://你的详情接口?jobId={encryptJobId}' \
  --analyze
```

`{encryptJobId}` 是占位符，脚本会自动替换成每个岗位自己的 ID。

## 输出文件

| 文件 | 内容 |
| --- | --- |
| `boss_ai_jobs.csv` | 整理后的岗位数据，包含薪资、公司、地点、技能标签、`responsibilities`、`requirements`、`description`。 |
| `boss_skill_stats.csv` | 从岗位职责/任职要求里统计出的重复技能点，包含技能名、出现岗位数、占比、示例岗位。 |
| `boss_ai_jobs.jsonl` | 接口原始数据，一行一个岗位，方便后续排查字段。 |

字段说明：

| 字段 | 含义 |
| --- | --- |
| `responsibilities` | 岗位职责，对应截图里“岗位职责”下面的内容。 |
| `requirements` | 任职要求，对应截图里“任职要求”下面的内容。 |
| `description` | 完整岗位描述；如果无法拆分职责/要求，就主要看这一列。 |

## 参数说明

| 参数 | 含义 | 示例 |
| --- | --- | --- |
| `-k`, `--keyword` | 搜索关键词；可重复传多个。不传时默认搜索一组 AI 相关词。 | `-k 大模型 -k RAG` |
| `--city`, `-c` | Boss 城市码；默认上海 `101020100`。 | `--city 101010100` |
| `--pages`, `-p` | 每个关键词抓多少页；默认 `3`。 | `--pages 5` |
| `--page-size` | 每页请求多少条；默认 `30`。 | `--page-size 30` |
| `--analyze` | 抓完后在终端打印薪资、重复技能点、技术相似岗位组。 | `--analyze` |
| `--out` | 岗位 CSV 输出路径。 | `--out jobs.csv` |
| `--skill-stats-out` | 技能点统计 CSV 输出路径。 | `--skill-stats-out skill_stats.csv` |
| `--jsonl` | 原始数据输出路径。 | `--jsonl raw.jsonl` |
| `--cookie` | 直接传 Cookie；也可以用环境变量 `BOSS_COOKIE`。 | `--cookie 'xxx'` |
| `--headers` | 从 JSON 文件读取完整请求头。 | `--headers headers.json` |
| `--search-url` | 搜索列表接口地址；通常不用改。 | `--search-url 'https://...'` |
| `--detail-api-url` | 详情接口模板，用来抓完整岗位职责。 | `--detail-api-url 'https://...?jobId={encryptJobId}'` |
| `--delay-min` | 两次请求之间的最小等待秒数。 | `--delay-min 3` |
| `--delay-max` | 两次请求之间的最大等待秒数。 | `--delay-max 8` |

## 常见城市码

| 城市 | 城市码 |
| --- | --- |
| 北京 | `101010100` |
| 上海 | `101020100` |
| 深圳 | `101280600` |
| 广州 | `101280100` |
| 杭州 | `101210100` |
| 成都 | `101270100` |
