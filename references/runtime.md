# 运行、交付与恢复

## 单条制作

脚本路径以 skill 为基准；由智能体执行 `uv run --python 3.11 scripts/montage.py <阶段> <job>`。使用完整脚本路径也可；项目有 rtk 时每条 shell 命令加 rtk。只有修改脚本时才需要读源码。

1. 新任务执行 `inventory <机构素材目录> --out <新 job>`，阅读素材文字并观察视频和图片，按 [计划格式](plan-schema.md) 编写计划。事实句引用原文且核对改写语义；正文首镜头必须是真实运动视频，中段可少量照片。包含封面内容和 publication 发布文案。
2. `validate-plan` 确定末句咨询钩子，检查事实、人物署名、封面来源和五个话题；再 `setup --install → voice`。完整旁白用本地 medium 独立核验音节和词级时间；发音疑点核验或修正，不能猜测放行。自动 ASR 不等于人工听审，不用后期变速、变调或裁停顿贴旧时长。
3. `build → avatars`。默认只为开头生成数字人；驱动音频只从本次完整旁白提取。已有 task_id 续查，不重复提交；pending 在当前任务中继续，单次等待最多 45 秒。
4. 查看 generation-source.json 列出的实际原片帧，检查脸、嘴、眼、手和构图；以 `review-provider --frames <实际看过的路径...> --note <具体观察>` 记录。随后 `cutouts → cover → carve → check → snapshot`。cover 关闭时跳过；封面生成后公共 compose 层自动接入首帧。
5. 查看布局快照，核对字幕避让与封面首帧／正文次帧；`render → verify` 完整解码和音画时序检查。查看 verification.json 列出的实际成片帧，再 `review --frames ... --note ...`。启用封面时复核证据包含首帧和次帧，不能只交几何检查。
6. review 保存 final.mp4，并自动运行发布包步骤。补打包可执行 `package <job>`。发布包不完整时不能称为交付完成。

## 用户交付

每条一个 `数字人名_封面主标题.zip`，MP4 使用相同基名；去掉换行及文件系统不支持的字符，页面标题原文不改。ZIP 内只包含四个用户文件：`基名.mp4`、`基名_封面.png`、`基名_发布文案.txt`、`基名_更换封面.html`。

TXT 使用 UTF-8，包含一个发布标题、一段描述和恰好五个不同话题，来自 plan.publication。文案结合本条真实主题与完整机构名，邀请老人或子女咨询，不编造价格、照护条件或承诺；话题不含空格。用户不用填写 JSON，由智能体编写计划。

HTML 自包含字体、人像和图片，离线修改主标题、高亮、三枚标签、完整机构名及三张实地图，导出 PNG。人物及社媒署名不可在编辑器中随意改绑。修改只作用于新 PNG，不自动修改包内视频；若要重新合入首帧，交由本制作流程处理。指定原封面先展示原图，编辑后按当前模板重排。

内部 plan、runtime、cover.json、verification 和 delivery.json 留在作品目录，不塞进用户发布包。保存内容来源、身份、布局与文件哈希，批次 CSV 另见 [批次](batch.md)。

## 服务适配、缓存和恢复

原生服务为火山语音V3、OmniHuman2.0，文件中转默认 tmpfile、TOS 选配；语音和数字人的服务开通与凭据由用户项目提供，skill不带可调用账号或默认人物。密钥通过project_config从连接引用加载，传给子进程环境，不写入CLI参数、公开配置或run日志。

中转只用于云端接口需要下载的输入文件，当前为数字人驱动 MP3；服务输出 MP4 仍从供应商链接直接下载到本地，用户交付包留在本地，不额外上传。tmpfile 使用匿名上传 API（单文件不超过100MB），不需安装 SDK/MCP、注册账号或 Key；持有链接可下载，文件7天后自动删除，不能提前删除。条款与接口见 [tmpfile](https://tmpfile.link/index-zh) 和 [服务条款](https://tmpfile.link/terms)。

上传后校验直链内容再提交数字人任务；私有 transfer-link.json 仅在本次运行目录保存链接供恢复复用，run.json 只保存服务、指纹和有效期。有效链接不重复上传；过期或明确404/410时重传，其他网络错误留待恢复，不自动改用收费 TOS。有 task_id 只续查，提交状态不明不重提。成功或明确拒绝后移除本地链接；tmpfile 远端仍自然到期，不报告已删除。TOS 仍在完成后删除远端对象。链接不写公开日志或用户发布包；已开始的任务沿冻结引擎及服务恢复。

## 可插拔生成器

连接的adapters可分别指定speech/avatar生成器目录，相对路径以.montage为基准。目录提供generate.py，使用与modules/digital-human/scripts/generate.py一致的CLI协议：generate（text/reuse-audio/audio-only/out/wait-seconds）、resume、review；退出码0成功、2待查询、3待音频复核、1故障。标准输出为JSON。

run.json至少保存text、config.tts、tts.file、qa_status、task_id；视频完成后verification包含output、sha256、alignment与visual_review_frames。替换服务时在适配器中映射这些字段，不改批次排队、文案选片和合成流程。适配器源码在freeze时复制到job，更新外部适配器不改变已开始任务；凭据仍使用同一个连接。原生适配器可通过连接tts/avatar/storage字段调整同协议服务参数。任意其他厂商Key并不能自动兼容，必须先提供对应协议适配器。

## 配音与视频

完整旁白先生成，再以本地medium做独立内容和词级核验。出现差异时读取runs/voice/audio-check.json与alignment-check.json，修正发音或取得实际独立核验依据；不能猜测略过漏字。声音复刻使用V3 voice_clone/get_voice，训练和每条语音合成是不同操作；新训练不会覆盖其他人物槽位。

provider-video.mp4是接口原片，digital-human.mp4是核验回传音频对齐后的视频。相关性须≥0.95、偏移≤80ms才换轨；叠加视频静音，完整旁白只播放一次。查看实际首中尾帧后记录provider review。抠像、描边与底缘渐隐是本地后处理，保持原声语速。

## 缓存与恢复

跨任务缓存位于项目作品/.montage-cache，语音按文案/音色/参数/连接/项目隔离，数字人按驱动PCM/人像/生成参数/连接隔离，后处理按原片与脚本指纹匹配。只有文件指纹及核验记录一致才能复用。图片、音频和文字变更须新版本；纯尺寸/排版或选片变化可复用匹配生成资产。

已有task_id只resume查询；提交中断状态不明只核查，不自动重复付费提交。明确失败保留日志和request_id；确实需要重提时依据用户已有授权决定，保留原记录。批次只重试失败项，其他成功项不重做。

check绑定HTML和实际引用资产的指纹，渲染输入变化重新检查。verify核对完整解码、1080×1920/30fps、语音哈希、字幕时长、中央实拍无黑帧、峰值和不足一帧的结尾补齐。固定CLI0.9.44，升级须随skill版本验证，不因安装到新电脑而自动换版本。

本机已安装相同版本CLI、但npm启动卡住时，可在项目 `settings.render.cli_path` 引用其实际JS入口。编排器检查该入口所在hyperframes包的version与锁定值相同，再用Node直接调用；不把开发者电脑路径写进preset或技能代码。换电脑没有此路径时清除这个用户覆盖值，继续使用锁定版本安装流程。

官方接口：[声音训练](https://docs.volcengine.com/docs/doubao-voice/tone-training-http?lang=zh)、[声音查询](https://docs.volcengine.com/docs/doubao-voice/tone-query-http?lang=zh)、[数字人生成](https://docs.volcengine.com/docs/jimeng-ai/omni-human20-video-generation-interface-documentation?lang=zh)。

## 封面缓存和任务冻结

运行快照冻结所选人物的社媒名、个人钩子、原头像和指定固定封面人像／图片。最终钩子及来源写入 plan，选择随 runtime 冻结；修改人物库不追溯改已开始任务。只改封面／正文排版时复用匹配声音与口型；改钩子必须生成新旁白并重新核验时间，音色模型继续复用。封面由文字、素材、人像、字体和模板脚本指纹匹配，PNG 和编辑 HTML 同时核验。

cover.json 记录输入、来源、布局、人物／字体哈希；delivery.json 记录四个用户文件和 ZIP 哈希。verify 增加第 0／1 帧、编码容差内的封面比较、帧数／时长与音轨起点检查。封面只占一帧，不改变自然音频时间线。
