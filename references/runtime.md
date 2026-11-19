# 制作与交付

开始制作先按[工作台入口](workbench.md)选择页面或用户明确指定的无页面模式；已派发的子 Agent 不再启动页面。

脚本以 skill 为基准：`uv run --python 3.11 scripts/montage.py <阶段> <job>`。有 rtk 时每条 shell 命令加 rtk。只读当前阶段需要的文档，不为执行通读源码。已有任务先看状态和冻结引擎；改稿见[另存](revisions.md)。

## 单条制作

1. `inventory <机构素材目录> --out <新job>`。阅读 source-text.txt，观察实际素材，按[口播文案](narration.md)写稿、按[计划格式](plan-schema.md)编写 plan；正文开头和结尾用真实运动视频。
2. `validate-plan` 生成 content-audit.json。按[内容复核](content-review.md)核对来源、口播、封面、发布文案和文画对应，处理警示后执行 `review-content --note <具体结论>`。
3. `setup --install → preflight`，在付费前验证锁定浏览器、页面加载与截图。失败只读[故障定位](troubleshooting.md)，不修改共享依赖缓存。然后 `voice → build`；ASR差异和数字映射失败分别定位，复用原音，不删数字绕过。
4. `avatars` 默认只生成开头。有 task_id 只续查，单次等待最多45秒。查看 generation-source.json 指定的原片首中尾帧，核对脸、嘴、眼、手和构图，再 `review-provider --frames <全部原片帧> --note <实际观察>`。
5. `cutouts → cover → carve → check → snapshot`。核对抠像边缘、逐镜内容、所有字幕、首帧封面和次帧正文；shot-audit.json提示重复片源与源时间重叠。封面图和标签单独逐槽核对，见[封面](covers.md)。
6. `render → verify`。查看 verification.json 的全部逐镜／字幕检查帧，再 `review --frames <全部实际检查帧> --note <具体观察>`。动态口型和听审分别检查，可用 `--motion-note`、`--listening-note`记录；没做就保留未核验，不能把音轨相关性当成视觉口型评分，也不能声称真人听审。
7. review 保存 final.mp4 并自动打包。发布包不完整或检查仍待处理时如实报告；完成不等于用户认可。

## 默认配乐

新任务默认开启包内 Tenderness，由 preset.json 的 `skill:assets/music/...`引用。任务创建时复制到工程 assets/music/source.mp3，后续沿副本恢复。音量和淡入淡出来自配置；carve 按本次旁白计算人声避让，不复用其他视频曲线。资源缺失时停止，不静默交付无配乐视频。

本次关闭用 settings.music.enabled=false；替换用 settings.music.resource。绝对路径直接使用，普通相对路径相对项目 .montage/，skill: 前缀相对安装目录。项目／任务显式覆盖优先。配乐长度不足则换足够长的音乐，不拉伸旁白。

## 发布包

工作台在实际视频通过技术核验后继续打包。数字人原片、排版、对比度和成片的画面意见在对应成片预览的「画面复核提醒」里查看。仅对比度提示保留浏览器的测量结果，画面复核未完整结束时也会留提醒。缺少成片、无法解码、时长或帧数异常仍需处理。

默认工作台模式每条发布包只含 MP4、封面 PNG、发布文案 TXT。封面编辑器嵌入工作台，不额外交付 HTML；用户明确要求离线编辑 HTML 时才沿用原生发布包。TXT含标题、描述和恰好五个不同话题；事实来源与计划一致。内部工程和核验记录不放入用户ZIP。

内部封面编辑 HTML 内嵌字体、人像、三张实地图，离线改标题、高亮、标签、完整院名和照片；人物与署名保持绑定。导出PNG不会自动改视频首帧，重新合入应由本流程处理。静态自包含检查不代替真实编辑、换图、导出验证。

服务参数、文件中转、缓存及冻结细节仅在需要时读[服务运行](service-runtime.md)。

制作完成报告后等待用户验收，不能立即删除工程。验收及中间文件清理见[工作台入口](workbench.md#验收与清理)。

工作台队列的打包直接生成一个含 MP4、封面 PNG 和发布文案的 ZIP，不额外复制交付目录或封面编辑 HTML。源字体与固定依赖可跨工程共享；计划、状态、可变字幕和输出仍属于单条工程。
