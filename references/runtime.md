# 服务适配、缓存和恢复

原生服务为火山语音V3、OmniHuman2.0和TOS；服务开通和凭据由用户项目提供，skill不带可调用账号或默认人物。密钥通过project_config从连接引用加载，传给子进程环境，不写入CLI参数、公开配置或run日志。运行记录不保存临时签名URL。

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

官方接口：[声音训练](https://docs.volcengine.com/docs/doubao-voice/tone-training-http?lang=zh)、[声音查询](https://docs.volcengine.com/docs/doubao-voice/tone-query-http?lang=zh)、[数字人生成](https://docs.volcengine.com/docs/jimeng-ai/omni-human20-video-generation-interface-documentation?lang=zh)。
