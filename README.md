# Boss AI Jobs

用你自己浏览器里已登录的 Boss 直聘会话，请求搜索接口，保存 AI 相关岗位列表，并做薪资与技术关键词分析。

## 安装

```powershell
pip install -r requirements.txt
```

## 获取 Cookie

1. 浏览器登录 Boss 直聘。
2. 打开开发者工具，进入 Network。
3. 在岗位搜索页搜索一次关键词。
4. 找到 `joblist.json` 请求，复制 Request Headers 里的 `cookie`。

脚本不处理验证码、登录、风控绕过；如果接口返回 `401/403/429`，需要刷新 Cookie 或降低频率。

## 运行

```powershell
$env:BOSS_COOKIE='你的 Cookie'
python .\boss_ai_jobs.py --city 101020100 --pages 3 --analyze
```

指定关键词：

```powershell
python .\boss_ai_jobs.py -k 大模型 -k RAG -k AI产品经理 --city 101020100 --pages 5 --analyze
```

补充抓详情接口：

```powershell
python .\boss_ai_jobs.py -k 大模型 --detail-api-url "https://你的详情接口?jobId={encryptJobId}" --analyze
```

`--detail-api-url` 需要从 Network 里复制详情接口，并把岗位 ID 替换成 `{encryptJobId}`；不同时间和账号看到的接口字段可能不同，脚本会递归寻找 `postDescription/jobDescription/description/jobDesc/content` 作为工作内容。

输出：

- `boss_ai_jobs.csv`：岗位、薪资、公司、地点、经验、学历、技能标签、工作内容。
- `boss_ai_jobs.jsonl`：接口原始数据，便于后续补字段。

常见城市码：

- 北京：`101010100`
- 上海：`101020100`
- 深圳：`101280600`
- 广州：`101280100`
- 杭州：`101210100`
- 成都：`101270100`
