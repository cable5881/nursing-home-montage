# 原生文件接单通道

主 Agent、策划子 Agent、视频子 Agent 使用宿主原生 Read/Write 工具收发 JSON；不需要执行 Bash。执行服务在当前宿主官方后台会话或用户独立系统会话运行，负责固定阶段脚本；不调用另一套模型，不复制登录凭据，也不改变宿主权限。

## 请求与回执

项目路径为 PROJECT，每次请求使用新的随机标识。写 `PROJECT/.montage/workbench/agent-inbox/标识.request.json`，读取同名 `.result.json`。必须先收到 `ok=true` 再继续。正在写入的 JSON 会等下一次完整读取；同一个标识重读回执不会重复执行。不要改 queue.json。一次只写一个完整的小请求，长计划写工程文件。

主 Agent 第一次连接：

```json
{"version":2,"op":"connect","clientId":"当前主对话的唯一标识","host":"workbuddy"}
```

保存回执中的 connectionToken，仅主 Agent 持有，不写给制作子 Agent，不展示在网页或最终回复。此后主 Agent 发送：

```json
{"version":2,"op":"poll","connectionToken":"连接回执的值"}
```

返回 waiting 时保持当前主对话接单；有队列时继续读，避免同时开启多个监听。健康的命令通道可用 bridge wait 前台阻塞等待；返回派发时作业已领取，不能再 poll 领取第二条。不能与原生文件通道并行领取，也不能把 wait 放在后台后结束协调轮次。若 Bash/命令代理失联，继续用原生 Read/Write 收发，不反复执行失败命令。

收到子 Agent 的 needs_input 时，先等它退出并 settle，再继续接单。waitingFor=workbench-answer 表示任务页在等用户答复，worker-exit 表示页面已保存答复、旧执行者尚未结束。保持原生文件 poll 或前台 wait，工作台任务无需在宿主聊天里再打开提问弹窗。页面答复后按原序号派发，新的策划或视频子 Agent 在 request.json 里读取 answerQuestion 和 answer。

返回 dispatch 时，使用宿主原生 Task/子 Agent 工具新建上下文，仅传 prompt 路径。kind=planning 负责整批；kind=video 只负责一条。若原生工具支持后台派发，取得真实 agentId 后立即发送 op=attach，携带 connectionToken、id、lease、agentId，保存执行者身份，便于主对话恢复后核查。严格等待本次原生子 Agent 结束后，用宿主实际返回的 agentId 登记：

```json
{"version":2,"op":"settle","connectionToken":"仅主 Agent 持有","id":"派发 id","lease":"派发 lease","agentId":"真实原生子 Agent 标识"}
```

无论成功、待补充或失败，确认子 Agent 已退出后都要登记，再 poll。不伪造 agentId，不凭心跳过期释放租约。明确断开用 op=disconnect 并带 connectionToken。恢复连接沿用当前主对话 clientId；过期连接不能覆盖一个仍在接单的新主对话。

## 子 Agent

先领取：

```json
{"version":2,"op":"accept","id":"本条 id","lease":"本条 lease","workerId":"PROMPT 中的 workerId"}
```

普通进度：op=report，增加 phase（0–5）、status（running/needs_input/failed/completed）、message。needs_input 必须带完整 question，选项直接写在问题里。收到 needs_input、failed 或 completed 的终态回执后退出子 Agent，由主 Agent settle。

固定阶段执行：

```json
{"version":2,"op":"run","id":"本条 id","lease":"本条 lease","action":"advance"}
```

立即返回 runId。发送 op=run-status，携带相同 id、lease、runId 查看记录；不要在上一次尚在执行时重发新的 run 请求。服务自行连续执行与轮询接口并回传事实进度，不需要模型逐步敲命令。

- 视频首次准备：action=prepare-video，建立共享缓存支持的素材索引。单条重做先在派发文件夹写 revised-plan.json，再准备；已存在 runtime.json 的工程返回恢复状态，不重建。策划已准备好的视频直接读取本条 plan.json。
- 策划准备：action=prepare-planning，之后读取共享 inventory.json / source-text.txt。
- 策划校验：action=planning-check，校验整批草稿并生成 approved.json。
- 视频推进：action=advance。返回 needs_review 时，根据 gate 实际查看内容或画面，再请求审核。
- 审核：action=review，reviewKind=content/provider/layout/final/contrast，note 是具体观察，frames 是实际看过的当前工程文件路径。content 不需要 frames；其他审核必须提供对应真实帧。审核后再 advance。contrast 只用于原有规范允许的对比度复核，不能绕过其他错误。
- 定位排版错误：可单独 action=snapshot 或 check。修改计划时先报告问题或另存重做，不让执行器悄悄跳过失败步骤。

advance 返回 completed 已完成核验及队列 report；立即结束子 Agent，不重复 report completed。返回 pending/checkpoint 时再次 advance 会查询已有任务，不重提付费生成。返回 failed 时查看日志、修正可修复问题；权限拒绝或不可恢复问题报告 failed 并退出。

## 通道故障

如果本地执行服务或命令代理报 ECONNREFUSED，保留云端任务 ID、当前工程和租约，不用更换目录重提生成。让主 Agent 确认原生子 Agent 退出后登记失败。主 Agent 继续原生文件通道接单；用户重试保留原序号。若原生文件工具本身也不可用，准确说明具体限制，等待宿主恢复，不能宣称自动接单成功。

## 用户指定无页面

没有 HTTP 服务时，不向无人接收的文件收件箱提交 run。主 Agent 使用 bridge.py wait，派发真实新子 Agent；子 Agent 先 accept，再执行 `bridge.py --project PROJECT run ID --lease LEASE --action ACTION`。ACTION 使用相同的 prepare-planning/planning-check/prepare-video/advance/review/snapshot/check。run 等本次步骤实际退出后返回结构化结果，不启动 HTTP，不生成独立的另一套队列。

review 额外提供 `--review-kind KIND --note-file 具体观察.txt --frames 实际帧路径...`。报告和结束登记沿用带租约 report/settle 命令；待补充或失败也必须结束并由主 Agent 登记。无页面模式依赖用户选择的本地命令执行能力，命令代理自身不可用时应报告该限制，保留现场。
