[English](../EXTENDING.md) | **简体中文**

# 扩展

修改 `build_workflow.py`,运行 `python3 build_workflow.py` 重新生成 `workflow.json`,运行 `python3 test.py`,然后把新的 JSON 导入 n8n。不要手改 `workflow.json`;下次重新生成时会被覆盖。

## 新增一个客户
在 `build_workflow.py` 里 `Load client profile` 脚本的 `CLIENTS` 中加一项:
```js
'law-firm': { voice: 'precise and sober', audience: 'in-house counsel',
              max_chars: 800, banned: ['guaranteed outcome', 'best lawyers'] },
```
请求里的 `client` 必须与这个键一致。如果新档案的限制很重要,在 `test.py` 里为它加一个用例。

## 修改允许的修订轮数
`Interpret decision` 脚本里的 `MAX_ATTEMPTS`(目前是 3)。取 3 时,在第三版草稿上 `revise` 会以 `revision_limit_reached` 结束本次运行。

## 更换审核渠道
把 `NOTIFY_URL` 指向你的渠道。它收到的内容有 `request_id`、`client`、`topic`、`attempt`、`draft`、`checks`、`checks_passed`、`resume_url` 和一个 `reply_with` 提示。你的渠道只需要让人能向 `resume_url` 发回一个 POST,带上 `decision`、可选的 `feedback` 和 `reviewer`。`deploy/inbox.py` 里的审核页面就是一个例子。

## 更改"发布"的含义
把 `PUBLISH_URL` 指向 CMS 或排期工具。它会收到 `request_id`、`client`、`content`、`attempt` 和 `reviewer`。如果发布必须可靠,请在 `Publish` 节点周围加上重试和错误处理(见 `ARCHITECTURE.md` 里的已知缺口)。

## 使用别的模型
任何 OpenAI 兼容的聊天补全接口都可以:设置 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`。推理型模型每版草稿会多花几秒;审核人只需要等第一版,所以这里通常可以接受。

## 新增检查
见 `TESTING.md` 里的"新增检查或用例"。
