# 服务、缓存与冻结

## 服务适配、缓存和恢复

原生服务为火山语音V3、OmniHuman2.0，文件中转默认 tmpfile、TOS 选配；语音和数字人的服务开通与凭据由用户项目提供，skill不带可调用账号或默认人物。密钥通过project_config从连接引用加载，传给子进程环境，不写入CLI参数、公开配置或run日志。

中转只用于云端接口需要下载的输入文件，当前为数字人驱动 MP3；服务输出 MP4 仍从供应商链接直接下载到本地，用户交付包留在本地，不额外上传。tmpfile 使用匿名上传 API（单文件不超过100MB），不需安装 SDK/MCP、注册账号或 Key；持有链接可下载，文件7天后自动删除，不能提前删除。条款与接口见 [tmpfile](https://tmpfile.link/index-zh) 和 [服务条款](https://tmpfile.link/terms)。

上传后校验直链内容再提交数字人任务；私有 transfer-link.json 仅在本次运行目录保存链接供恢复复用，run.json 只保存服务、指纹和有效期。有效链接不重复上传；过期或明确404/410时重传，其他网络错误留待恢复，不自动改用收费 TOS。有 task_id 只续查，提交状态不明不重提。成功或明确拒绝后移除本地链接；tmpfile 远端仍自然到期，不报告已删除。TOS 仍在完成后删除远端对象。链接不写公开日志或用户发布包；已开始的任务沿冻结引擎及服务恢复。

## 可插拔生成器

连接的adapters可分别指定speech/avatar生成器目录，相对路径以.montage为基准。目录提供generate.py，使用与modules/digital-human/scripts/generate.py一致的CLI协议：generate（text/reuse-audio/audio-only/out/wait-seconds）、resume、review；退出码0成功、2待查询、3待音频复核、1故障。标准输出为JSON。

run.json至少保存text、config.tts、tts.file、qa_status、task_id；视频完成后verification包含output、sha256、alignment与visual_review_frames。替换服务时在适配器中映射这些字段，不改批次排队、文案选片和合成流程。适配器源码在freeze时复制到job，更新外部适配器不改变已开始任务；凭据仍使用同一个连接。原生适配器可通过连接tts/avatar/storage字段调整同协议服务参数。任意其他厂商Key并不能自动兼容，必须先提供对应协议适配器。

## 配音与视频

完整旁白先生成，再以本地medium做独立内容和词级核验。出现差异时读取runs/voice/audio-check.json与alignment-check.json，修正发音或取得实际独立核验依据；不能猜测略过漏字。声音复刻使用V3 voice_clone/get_voice，训练和每条语音合成是不同操作；新训练不会覆盖其他人物槽位。

provider-video.mp4是接口原片，digital-human.mp4是核验回传音频对齐后的视频。相关性须≥0.95、偏移≤80ms才换轨；叠加视频静音，完整旁白只播放一次。查看实际首中尾帧后记录provider review。抠像、描边与底缘渐隐是本地后处理，保持原声语速。正文人物用外扩的亮白虚线，头发和肩部留出间距，底部渐隐。

## 缓存与恢复

跨任务缓存位于项目作品/.montage-cache，语音按文案/音色/参数/连接/项目隔离，数字人按驱动PCM/人像/生成参数/连接隔离，后处理按原片与脚本指纹匹配。只有文件指纹及核验记录一致才能复用。图片、音频和文字变更须新版本；纯尺寸/排版或选片变化可复用匹配生成资产。

已有task_id只resume查询；提交中断状态不明只核查，不自动重复付费提交。明确失败保留日志和request_id；确实需要重提时依据用户已有授权决定，保留原记录。批次只重试失败项，其他成功项不重做。

check绑定HTML和实际引用资产的指纹，渲染输入变化重新检查。verify核对完整解码、1080×1920/30fps、语音哈希、字幕时长、中央实拍无黑帧、峰值和不足一帧的结尾补齐。固定CLI0.9.44，升级须随skill版本验证，不因安装到新电脑而自动换版本。

本机已安装相同版本CLI、但npm启动卡住时，可在项目 `settings.render.cli_path` 引用其实际JS入口。编排器检查该入口所在hyperframes包的version与锁定值相同，再用Node直接调用；不把开发者电脑路径写进preset或技能代码。换电脑没有此路径时清除这个用户覆盖值，继续使用锁定版本安装流程。

官方接口：[声音训练](https://docs.volcengine.com/docs/doubao-voice/tone-training-http?lang=zh)、[声音查询](https://docs.volcengine.com/docs/doubao-voice/tone-query-http?lang=zh)、[数字人生成](https://docs.volcengine.com/docs/jimeng-ai/omni-human20-video-generation-interface-documentation?lang=zh)。

## 封面缓存和任务冻结

运行快照冻结所选人物的社媒名、个人钩子、原头像和指定固定封面人像／图片。最终钩子及来源写入 plan，选择随 runtime 冻结；修改人物库不追溯改已开始任务。只改封面／正文排版时复用匹配声音与口型；改钩子必须生成新旁白并重新核验时间，音色模型继续复用。封面由文字、素材、人像、字体和模板脚本指纹匹配，PNG 和编辑 HTML 同时核验。

cover.json 记录输入、来源、布局、人物／字体哈希；delivery.json 记录四个用户文件和 ZIP 哈希。verify 增加第 0／1 帧、编码容差内的封面比较、帧数／时长与音轨起点检查。封面只占一帧，不改变自然音频时间线。
