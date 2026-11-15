# 可替换画面模板

`settings.template.id` 选择 `orange`（暖金虚化分栏）、`green`（荧绿全屏实拍）、`legacy-orange`（原黑底橙色笔刷）或 `fullscreen-orange`（全屏橙色笔刷）。换模板只重新排版，不重新生成相同驱动音频的数字人。`settings.template.overrides` 只保存用户覆盖值，包内 `assets/templates/*.json` 保存通用坐标。

默认是 `legacy-orange`（黑底橙色笔刷），自然语言“橙色模板”也指此款。`orange` 这个内部ID仅表示新增橙金模板，不能因其名称为orange就误认为默认。新增模板不改默认设置。

## 参考复刻

两套新模板以 916×1717 参考画布测量，独立映射到 1080×1920 成片；不把旧模板字号套入新模板。所有标题、机构名、章节和字幕保持为可编辑文字，截图不作为文字贴图。实际字体、画面区域、人物位置和字幕宽度写入任务的 `template-layout.json`；检查实际快照，不能只凭参数宣称像素完全一致。

- `orange`：清晰画面位于参考 y445–1252，上下以同镜头虚化填充。金色标题参考可见高度79，白色机构名48；字幕基础字号75、关键词101，保持同一基线；白色分隔线。人物默认成片坐标 x48、底缘1390、400×550，落在清晰画面下沿。
- `green`：全屏实拍，左上两行荧绿机构牌；白底黑色斜体标题；参考 y1114–1193 为绿底章节牌。字幕基础字号88，白字黑边，关键词保留白色并加绿色下划线。人物默认 x48、底缘1225、400×550，避让下方章节牌和字幕。
- `fullscreen-orange`：实拍铺满1080×1920，无上下模板黑底；可编辑白色斜体标题、橙色笔刷机构名、白/粉手写字幕与黄色放大重点词，全部带黑色描边。模板字体大小保持，逐行测量字形、描边和阴影余量，参考字幕宽750视频像素。超宽自动重分行，必要时从保存的字符时间或已核验配音对齐记录拆字幕；缺可靠时间就停止，不能按字数猜时长。只改变字幕分组，不改变配音、镜头时长或人物驱动。字体从项目typography.body_font读取，缺省用包内字体，不依赖本机系统字体。
- 首尾人物的存在与时间只读 `avatars.json`，模板不擅自添加人物；实际任务只要求开头人物时，结尾只有实拍、配音和CTA字幕。

字体覆盖示例（由智能体维护；路径是用户项目自己的字体，不放进通用技能）：

```json
{
  "template": {
    "id": "green",
    "overrides": {
      "fonts": {
        "title": {"file": "/absolute/title-font.ttc", "index": 2},
        "body": {"file": "/absolute/body-font.ttc", "index": 7},
        "subtitle": {"file": "/absolute/body-font.ttc", "index": 11}
      },
      "brand_lines": ["机构简称", "城市区域"],
      "avatar": {"x": 48, "bottom": 1225, "width": 400, "height": 550}
    }
  }
}
```

无覆盖字体时使用包内 Noto Sans SC Black；所有实际用字重新子集到任务 `assets/fonts/Template-*.woff2`，不依赖浏览器字体回退，也不复制他人项目字体。`brand_lines` 未指定时从当前机构 `displayName` 的 `·` 分为两行。机构字段来自本任务，不沿用参考图中的机构。

## 排版与验证

计划中的 `captions[].focus` 指定已有关键词；暖金版放大变金，绿色版加下划线。最多两行；每行固定字号，超出参考宽800会报错，需重新断字幕，不能为了塞字缩小整片字号。最后一条字幕按时间线要求保持到最后一帧。模板只读取时间线，不修改旁白速度和时长。

`build_job.compose` 根据任务配置调用渲染器。独立排版可执行：

```bash
uv run --python 3.11 scripts/compose_reference.py <job> --template green
```

独立脚本依赖 fonttools、brotli；正常经 montage.py 运行时已经声明依赖。`job/template.json` 可包含 `{ "id": "green", ...覆盖值 }`，也接受 `overrides` 嵌套。`avatar_overrides.<人物片段id>` 允许单片段位置覆盖，未指定沿用模板安全区；不能为排版复用不匹配的新旧口型。

已完成配音、时间线与人物的任务可离线创建另一个模板版本：`montage.py variant SOURCE --template green --out NEW`。此命令只复用已核验的本地资产并重新排版，付费生成调用为零；随后对新工程重新 check、snapshot、render、verify，不能把源工程的检查结论直接套给新版。

全屏版同样使用 `montage.py variant SOURCE --template fullscreen-orange --out NEW`。默认按项目配置做公共UI避让；`--platform douyin`等按已配置平台分别导出，`--platform common`明确通发模式。平台名称是项目配置键，不是写死的平台标准。新输出记录caption-fit.json、platform-ui-audit.json和template-layout.json。直接compose再次执行也保留全屏样式；旧job仍绑定旧引擎，需要新能力时另存variant，不修改旧runtime。

全屏字幕最低位置的计算、配置及限制见 [平台UI避让](platform-ui.md)。模板参考区域只用于没有测量配置时的排版，不替代实际设备验证。项目选用全屏款时将template.id写入项目配置，不重置其他用户默认模板。

暖金背景使用 HyperFrames 原生 `data-color-grading.effects.blur`（0–1）；不以CSS blur处理素材。检查、快照、成片核验仍按主流程执行。对一比一复刻需选同一房间画面和参考句，检查文字可见边界、分隔线、背景裁切和高亮；不同镜头的背景像素不能作为排版误差。

参考图金色描边文字在亮背景上可能触发只采样填充色的WCAG错误。先保留完整check报告并修复全部非contrast错误；实际查看本工程qc-layout对应帧，确认描边、阴影和文字可读后，才可用 `montage.py review-contrast <job> --frames ... --note ...` 记录限定的视觉复核。原始错误和fullCheckPassed=false仍保留；复核绑定全部输入指纹，修改画面后自动失效，不能将其描述为完整自动检查通过。
