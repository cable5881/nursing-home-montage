# 初始化与人物库

所有命令由智能体运行，用户通过对话提供资料和偏好，或在本地页面输入凭据。用工具workdir进入用户项目；技能可以位于任意路径，以下SCRIPT表示技能scripts目录。可为project.py/batch.py显式传全局参数 --project <项目根>；从已有任务恢复会读取runtime绑定项目。

## 一次配置

1. `python SCRIPT/project.py init` 幂等创建 `.montage/project.json`，不覆盖已有配置。
2. `python SCRIPT/project.py doctor` 只返回缺项布尔值、人物状态和工具可用性，不回显密钥。
3. `python SCRIPT/project.py setup-ui` 返回仅绑定127.0.0.1的临时设置页链接。让用户在本地页面填写一次：语音API Key、视频AK/SK、音频存储桶/区域/Endpoint。留空保留现有值。页面不访问外部脚本、不记录输入日志，30分钟无操作后停止。
4. 若用户已提供凭据文件，智能体读取其格式并转换为临时私有JSON，执行 `project.py credentials --file <文件> --connection main`。字段为api_key/ak/sk/bucket/region/endpoint；导入后清理临时副本，输出只报告成功和缺项。已有环境变量或macOS钥匙串可通过连接引用绑定；配置中保存引用，不把Key写入公开配置。Windows/Linux使用环境引用或项目私有文件。
5. 通过 `project.py configure --file <智能体生成的补丁JSON>` 保存settings、connections、default_person等用户偏好。未指定项保留原值。

当前原生适配器为火山语音V3 + OmniHuman2.0 + TOS，服务凭据每项目连接配置一次，几十个人物共享同一连接。不要假设任意一个Key能跨服务通用。当前用户的旧项目可以把已存在的凭据路径和钥匙串引用绑定到连接，不要求重新填写。

官方入口：[语音控制台](https://console.volcengine.com/speech/app)、[访问密钥](https://console.volcengine.com/iam/keymanage/)、[TOS](https://console.volcengine.com/tos)。根据接口实际权限提示定位服务开通/音色资源；不伪造权限检查通过，不为检查凭据偷偷生成几十段视频。

## 多人物导入

推荐但不强制：一个人物文件夹放一张正面图和一段干净单人录音，文件名任意。也支持同目录的同名图片+音频配对。

`uv run --python 3.11 SCRIPT/batch.py --help` 使用自动依赖；人物导入和训练命令用 `uv run --python 3.11 SCRIPT/project.py import-people <目录> --connection main`（project.py依赖均为标准库，媒体探测依赖ffmpeg/ffprobe）。

导入按名称和素材指纹去重，复制到.montage/people；图片规范为PNG，声音规范为单声道WAV，不改变语速。查看 `project.py people`。人物可先只有图片，随后绑定已有音色；缺音频且没有音色时保持needs_voice，不算就绪。

- 已有音色：`project.py bind <人物名或ID> --speaker <音色ID>`；自定义音色另加 --custom <ID>，speaker为custom_speaker_id。
- 默认人物：`project.py default <人物名或ID>`。
- 只有录音：`project.py train <人物名或ID>`。先在连接里选clone_mode：prepaid使用speaker_pool空闲槽位；postpaid创建独立自定义音色，首次正式合成会产生平台槽位费。服务模式未选择时只补问这一项。也可单次 --speaker 指定未占用槽位。
- 训练只执行一次并持久保存记录，后续相同命令查询。状态不明时不重训；状态成功后自动绑定，不重新训练已配置音色。不同人物不复用/覆盖同一预付费音色槽位。

声音样本不是未来每条视频的驱动音频。每条仍按新文案生成该人物的完整旁白，再只取首尾制作数字人。

## 用户配置示意（智能体维护）

connections.main包含speech_key/access_key/secret_key引用、storage、clone_mode、speaker_pool。people.<id>包含name、portrait、sample、speaker、custom_speaker_id、connection、speech_rate、status。所有相对资产路径均相对于.montage；用户在对话提供的外部路径应转换为绝对路径或复制到.montage/assets，避免依赖技能目录。

字体默认包内Noto，适配各系统。项目可用settings.typography.body_font和collection_index指定自己的字体；settings.music.enabled/resource指定自己的配乐。当前没有内置通用配乐，缺音乐时可询问用户提供或接受无BGM；不借用其他用户的商业授权曲目。
