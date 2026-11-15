# GitHub安装、更新与发布

仓库根就是技能目录。用户只需把GitHub链接发给智能体，说“安装到我的项目并初始化”或“更新混剪skill”；以下命令由智能体执行。

首次可先clone仓库到项目的 `.agents/skills/nursing-home-montage`，再用 `python <skill>/scripts/install.py --project <项目根>` 选择最新稳定tag。日常更新运行同一命令。--version可指定vX.Y.Z。只接受GitHub HTTPS仓库地址，稳定版本按数字语义版本排序，不跟随未发布的main或预发布tag。

install.py在替换前验证release.json的配置格式版本与必备文件，把旧代码移入.montage/install-backups后安装；复制失败恢复旧代码。已有Git工作区有代码修改时停止覆盖，先由维护者保存/发布，只有明确要求丢弃技能本地代码改动才用--replace-local。用户自定义不应该写在技能目录。

`.montage/project.json`、secrets、人物、模板覆盖、engines、批次和素材均不在更新范围。初始化幂等，不重置已有配置。未知/更高配置格式停止并保留原文件；未来新增格式必须随版本提供备份与迁移逻辑，不能直接用新版默认JSON覆盖。普通新增可选参数由默认配置补齐，用户已覆盖的字段继续优先。

新job冻结模板、脚本、默认参数与人物图到流程快照/任务；runtime.json保存版本和引擎位置。安装新版后，montage.py自动转交旧引擎继续旧job；批次调用各job绑定引擎。不能删除旧engines来清理空间，直到对应批次都完成且无需恢复。完成视频不重新生成。

## 发布者

仅将技能目录提交到独立仓库，不从用户项目根git add。公开仓库不得含.montage、机构素材、个人头像/录音、账号音色ID、密钥、临时签名URL、成片、node_modules或本机绝对路径。字体/第三方脚本附其许可说明。

更新VERSION与release.json，运行test_portable.py、skill结构检查，并在本地私有夹具上做离线回归。通过后提交main并创建对应vX.Y.Z稳定tag。用户的更新器取tag，配置格式兼容性由release.json声明。外部API训练/生成使用模拟接口测试；只有实际运行过云端才能称云端实测通过。

```bash
uv run --python 3.11 scripts/test_portable.py
```

本地离线回归：`uv run --python 3.11 scripts/regression.py --baseline <认可工程> --reference-video <认可视频> --out <新目录>`，不调用voice/avatars。baseline媒体只读引用，字体使用私有副本；比对关键帧、音轨及完整文件指纹。参考机构标题从用户项目配置读取，不将客户夹具打进仓库。
