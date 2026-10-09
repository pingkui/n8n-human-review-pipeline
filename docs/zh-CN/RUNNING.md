[English](../RUNNING.md) | **简体中文**

# 运行

已用 Docker 里的 n8n 2.42.5 测试。

## 1. 运行测试(只需要 Docker 和 Python 3)
```bash
python3 test.py
```
它会在 8089 端口启动 mock 服务,在 5678 端口启动一个 n8n 容器,导入并发布工作流,运行 12 项检查,最后删除容器和数据卷。mock 服务充当模型、审核渠道、CMS 和审计日志,所以不需要密钥。见 `TESTING.md`。

## 2. 在你自己的 n8n 里使用这个工作流
1. 在 n8n 里选 Workflows,然后 Import from file,选择 `workflow.json`。
2. 在 **n8n 进程上**设置这些环境变量:

| 变量 | 含义 |
|---|---|
| `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | 任意 OpenAI 兼容的聊天补全接口 |
| `NOTIFY_URL` | 草稿和恢复链接发到哪里(Slack 或 Teams 的 webhook、邮件网关、工单系统) |
| `PUBLISH_URL` | 批准的文章发到哪里(CMS、排期工具) |
| `AUDIT_URL` | 审计记录发到哪里(日志存储、表格) |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | n8n 2.x 默认禁止节点内使用 `$env`,而本工作流从中读取各个地址;也可以改放进 n8n 凭据 |
| `WEBHOOK_URL` | 审核人收到的链接所用的基础地址;必须是回复审核的人能访问到的 |

3. 发布工作流。在 n8n 2.x 里,已发布的工作流会在启动几秒之后才注册它的 webhook;更早发出的请求会得到 404。
4. 发送一个请求并回复它:
```bash
curl -X POST $N8N/webhook/content-request -H 'Content-Type: application/json' \
  -d '{"client":"startup-coach","topic":"Launch week lessons","facts":["We shipped in 6 weeks"]}'
# 审核人收到草稿和 resume_url,然后这样回复:
curl -X POST "$RESUME_URL" -H 'Content-Type: application/json' \
  -d '{"decision":"revise","feedback":"shorter, one concrete example","reviewer":"Sam"}'
```
请求字段:`client`(档案名之一)、`topic`(至少 5 个字符)、`facts`(可选,文章可以使用的字符串列表)。

## 3. 本地部署并带上审核页面
`deploy/` 里有一个 compose 文件,包含 n8n 和一个小网页(`inbox.py`),它接收三个对外调用,并让人提交请求、批准、要求修改或拒绝草稿。
```bash
cp deploy/.env.example deploy/.env      # 填写 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL
deploy/deploy.sh                        # 导入并发布工作流,启动两个服务
```
- 审核页面:**http://127.0.0.1:8089**。n8n 编辑器:http://127.0.0.1:5678(第一次访问会要求创建管理员账号)。
- 两个端口都绑定在 `127.0.0.1`。页面**没有登录**;请通过 SSH 隧道访问(`ssh -L 8089:127.0.0.1:8089 user@server`),或者在前面加上认证。
- 在页面上:选一个客户,写主题和可选的事实,点发送。会出现一张"Drafting"卡片,然后是草稿和它的四项检查;点 Approve、Revise(必须填意见)或 Reject。有变化时页面会自己刷新,你正在输入时不会重新加载。批准的文章显示在 Published 里,审计日志在最下面。
- 这个部署会在每次草稿和每次修改时调用你的模型服务商,所以会花钱。
- 停止:`cd deploy && docker compose down`(数据留在数据卷里;`down -v` 会删除)。

## 故障排查
| 现象 | 原因 |
|---|---|
| 刚启动就得到 404 "webhook is not registered" | n8n 在变为健康之后几秒才注册已发布的工作流;重试 |
| 工作流在 `Draft with LLM` 报环境变量错误 | `N8N_BLOCK_ENV_ACCESS_IN_NODE` 不是 `false`,或者 `LLM_*` 没有设置在 n8n 进程上 |
| 请求返回 202,但审核人什么也没收到 | `NOTIFY_URL` 不对,或 n8n 访问不到;在编辑器里查看这次执行 |
| 恢复链接在另一台机器上不能用 | `WEBHOOK_URL` 指向的地址,审核人访问不到 |
| n8n 日志里有 "Failed to start Python task runner" | 这里无害:工作流只用 JavaScript 的 Code 节点 |
