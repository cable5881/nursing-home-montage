# 批次执行

用户说“所有配置好的数字人，每人3条”，智能体执行：

```bash
uv run --python 3.11 SCRIPT/batch.py prepare 机构素材目录 --people all --per-person 3 --out 作品/本批
```

SCRIPT为技能scripts绝对路径；有rtk时加rtk。若每人数量不同，将用户要求转换为内部counts.json（人物名称或ID映射整数），加 --counts <文件>。0表示不参与。prepare返回总片数、所选人物、尚未就绪名单；配置几十个人时不要求逐个填写同一凭据。

读取本批 inventory/source-text 并实际检查媒体。按[口播文案](narration.md)先从原始介绍提炼共同核心，再写同一家机构的各版综合介绍。每篇完整覆盖共同核心，主要调整切入、顺序、句式和衔接。只有用户明确要求专题时才切成独立专题。镜头优先跟随各版口播，共同卖点可复用对应实拍。

batch.json 列明每个 plan 的相对路径、人物和 job。智能体为每条写 plan，机构事实与素材必须来自本批输入。`batch.py start <批次>` 验证来源、字幕和片头，拦截整篇逐句文字完全相同的稿件，并冻结每条人物、配置和流程。共用核心卖点、术语或部分句子可以直接通过重复校验。仅在用户允许同一个完整脚本复用时加 `--reuse-scripts`。

`batch.py run <批次> --limit 4` 每次推进若干任务。max_active默认2，限制尚在云端生成的任务数；本地阶段顺序执行避免渲染争抢。根据账号实际并发可在batch.json调整。所有生成凭据取自项目连接，人物不保存Key。返回pending时继续run；避免忙轮询，按接口状态适当等待，在当前会话持续推进。

每条的阶段和错误独立保存，已完成阶段不重做；失败项需要检查lastResult，修正后run --retry-failed恢复同一记录。未知提交状态或明确拒绝不能用重建任务绕过，保留request_id/task_id，按实际授权处理。

run在provider_review与final_review返回需要智能体检查的任务，不要求用户逐条操作。原片从每个job/assets/avatar-*/generation-source.json读取visualReviewFrames；看过每个首尾人物后：

```bash
uv run --python 3.11 SCRIPT/batch.py review-provider <批次> --item <任务ID> --frames <实际原片帧绝对路径...> --note <具体观察>
```

随后继续run进行抠像、混音与渲染。final_review时读取job/verification.json，查看实际导出帧，再用 `batch.py review ...` 同样参数记录。几何、ASR和少量抽帧不能声称全片人工听审。

成片位于 `<批次>/people/<人物ID>/<序号>/final.mp4`。`batch.py status <批次>` 输出进度并更新交付清单.csv。交付时按人名展示链接/文件，清单含人物、编号、状态和实际成片路径；有失败就明确列出，不能把部分完成说成整批成功。批次数据在技能目录之外，更新后继续使用job绑定的旧版本。

## 默认封面与发布包

每条计划包含 cover 和 publication，整批 start 在付费前核对身份署名、封面素材与五个话题并解析 CTA。cutouts 后统一执行 cover，再检查与渲染。review 后逐条打包发布 ZIP；包失败不能把该条标为 complete。标题、标签与发布文案跟随本条正文，可共用机构名称和核心卖点。

交付清单增加封面、发布 ZIP 和钩子来源。旧引擎没有 cover 设置时跳过新阶段，继续旧流程；旧任务不会被新版强制补封面。

批次 start 创建各 job 后，智能体逐条查看 content-audit.json，对照[内容复核](content-review.md)核对核心覆盖和段落画面，再执行 montage.py review-content。未记录时 voice 会停止。批次 run 在每条 voice 前先执行 preflight。
