# 另存版本与恢复

已有任务继续使用runtime.json记录的冻结引擎。有task_id只resume，提交不明时先查记录，不因重开窗口重复提交。声音／口型与文案指纹不一致时停止，不删除runtime.json、voice.json解锁。

## 改排版或升级样式

`montage.py revise SOURCE --out NEW` 在新目录复用已核验声音、口型、素材和时间线，切到唯一全屏样式，不调用付费服务。可用--platform common或项目测量配置键另存平台版本。重新preflight、核对内容、cover/carve/check/snapshot/render/verify/review，不能沿用旧版布局验收结果。

## 改文案或分镜

智能体编写新的plan文件，然后执行 `montage.py revise SOURCE --out NEW --plan NEW_PLAN`。旁白和声音设置完全相同才复用时间资产；文案变化不复制旧语音、旧口型和旧时间线，重新validate-plan、review-content、preflight、voice/build/avatars。相同文案但改镜头或字幕时复用匹配声音，重新build。

另存保留人物／服务绑定及用户素材，原工程和原冻结引擎不变。缓存可能复用其他已核验的同输入资产，但不得把新旧驱动混用。实现仍保留variant命令作同义入口，不再支持--template多模板选项。

更换人物、生成提示或驱动边界时新建任务，不通过revise继承旧口型记录；纯位置、尺寸、字幕、选片及配乐调整可另存复用匹配旁白。
