# 养老院素材混剪 Skill

提供养老机构的视频、图片与事实文本，用自然语言制作包含开头数字人和结尾引导的竖版混剪。支持多个数字人、共享服务连接、每人若干条、批量排队与断点续跑。

## 怎么使用

把本仓库链接发给支持本地技能和命令执行的智能体：

> 从 https://github.com/cable5881/nursing-home-montage 安装混剪skill到我的项目，并引导我完成首次配置。

智能体只收集缺少的信息、整理人物库并保存配置。服务Key可在本地设置页填写一次；有配置后不用重复填写，用户不需要编辑JSON。

日常可以直接说：

> 用这个机构的素材，全部已配置数字人，每人做3条不同的混剪。

> 用王老师做2条、李老师做5条。

> 更新混剪skill，保留我的人物和项目配置。

## 配置不会随更新丢失

仓库目录只放生产代码和通用模板；用户配置保存在项目根.montage，素材和作品也在技能目录之外。GitHub更新使用稳定版本tag，保留用户配置与旧任务引擎。人物、音色和服务凭据不随仓库分发。

默认1080×1920/30fps、黑底橙色笔刷模板（legacy-orange），另可切换橙金和绿色模板；仅开头左下角描边数字人，结尾为引导口播与真实混剪画面，口播结束即收片。通用字体随包；用户可提供自己的字体、配乐和人物。首次使用需要自己的语音/数字人服务及音色资源；原生接入火山语音、OmniHuman2.0与TOS。音频样本可复刻为各自音色，多个人物共用连接。API生成和音色资源费用由用户自己的服务账号结算。

v2.2.0新增全屏橙色模板（fullscreen-orange）：无上下模板黑底、描边字幕、固定字号自动重断句。可依据用户截图测量抖音/小红书/视频号等UI，选择公共低位字幕或分平台导出；机构、字体、人物和平台测量配置均来自用户项目。新增“替你看100家养老院＋评论参观预约”可选结尾钩子。详见[模板](references/templates.md)、[UI避让](references/platform-ui.md)和[结尾引导](references/closing-hooks.md)。

入口：[SKILL.md](SKILL.md)。初始化：[onboarding](references/onboarding.md)；批次：[batch](references/batch.md)；更新：[updates](references/updates.md)。本仓库不包含任何用户的凭据或客户素材。

## 默认发布包

新片默认生成 C 款青绿自适应封面，并只合入视频首帧。每个数字人与一个社媒名绑定，新增人物可自填或选择咨询钩子。用自然语言提供机构素材、人物和数量即可；数字人／服务配置在项目内保存。

每条交付“数字人名_封面标题.zip”，包含同名 MP4、封面 PNG、发布标题／描述／五个话题 TXT，以及可离线换图改字并导出 PNG 的 HTML。内部生产记录保留在作品目录。详见 [运行与交付](references/runtime.md)、[封面](references/covers.md)、[咨询钩子](references/closing-hooks.md)。

## 开发验证

需要Python 3.11、uv、Node/npm、FFmpeg。技能执行时自动声明Python依赖，渲染固定HyperFrames0.9.44。已进行macOS本地验证；Windows/Linux路径与凭据采用通用实现，尚无完整平台实机验收记录。

```bash
uv run --python 3.11 scripts/test_portable.py
```

代码许可见LICENSE；第三方资源见THIRD_PARTY_NOTICES.md。
