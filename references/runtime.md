# 制作与交付

脚本以 skill 为基准：`uv run --python 3.11 scripts/montage.py <阶段> <job>`。有 rtk 时每条 shell 命令加 rtk。只读当前阶段需要的文档，不为执行通读源码。已有任务先看状态和冻结引擎；改稿见[另存](revisions.md)。

## 单条制作

1. `inventory <机构素材目录> --out <新job>`。阅读 source-text.txt，观察实际素材，按[计划格式](plan-schema.md)编写 plan。先确定封面承诺、主体段落、结尾咨询动作；正文开头和结尾用真实运动视频。
2. `validate-plan` 生成 content-audit.json。逐项查看事实原文、封面标签、发布文案和文画对应；按[内容复核](content-review.md)处理警示，再 `review-content --note <具体结论>`。引用存在不代表改写语义成立。
3. `setup --install → preflight`，在付费前验证锁定浏览器、页面加载与截图。失败只读[故障定位](troubleshooting.md)，不修改共享依赖缓存。然后 `voice → build`；ASR差异和数字映射失败分别定位，复用原音，不删数字绕过。
4. `avatars` 默认只生成开头。有 task_id 只续查，单次等待最多45秒。查看 generation-source.json 指定的原片首中尾帧，核对脸、嘴、眼、手和构图，再 `review-provider --frames <全部原片帧> --note <实际观察>`。
5. `cutouts → cover → carve → check → snapshot`。核对抠像边缘、逐镜内容、所有字幕、首帧封面和次帧正文；shot-audit.json提示重复片源与源时间重叠。封面图和标签单独逐槽核对，见[封面](covers.md)。
6. `render → verify`。查看 verification.json 的全部逐镜／字幕检查帧，再 `review --frames <全部实际检查帧> --note <具体观察>`。动态口型和听审分别检查，可用 `--motion-note`、`--listening-note`记录；没做就保留未核验，不能把音轨相关性当成视觉口型评分，也不能声称真人听审。
7. review 保存 final.mp4 并自动打包。发布包不完整或检查仍待处理时如实报告；完成不等于用户认可。

## 默认配乐

新任务默认开启包内 Tenderness，由 preset.json 的 `skill:assets/music/...`引用。任务创建时复制到工程 assets/music/source.mp3，后续沿副本恢复。音量和淡入淡出来自配置；carve 按本次旁白计算人声避让，不复用其他视频曲线。资源缺失时停止，不静默交付无配乐视频。

本次关闭用 settings.music.enabled=false；替换用 settings.music.resource。绝对路径直接使用，普通相对路径相对项目 .montage/，skill: 前缀相对安装目录。项目／任务显式覆盖优先。配乐长度不足则换足够长的音乐，不拉伸旁白。

## 发布包

每条一个“数字人名_封面主标题.zip”，只含同基名 MP4、_封面.png、_发布文案.txt、_更换封面.html。TXT含标题、描述和恰好五个不同话题；事实来源与计划一致。内部工程和核验记录不放入用户ZIP。

HTML内嵌字体、人像、三张实地图，离线改标题、高亮、标签、完整院名和照片；人物与署名保持绑定。导出PNG不会自动改视频首帧，重新合入应由本流程处理。静态自包含检查不代替真实编辑、换图、导出验证。

服务参数、文件中转、缓存及冻结细节仅在需要时读[服务运行](service-runtime.md)。
