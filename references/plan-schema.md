# 内部计划数据

用户只提供机构素材。由智能体阅读 inventory.json/source-text.txt、观察视频图片后编写 job/plan.json，不把填 JSON 的工作交给用户。

编写或修改 `sentences` 前按[口播文案](narration.md)完成整篇口语稿，再拆分计划字段和字幕。

```json
{
  "version": 1,
  "person": "人物ID（可省略以使用默认人物）",
  "institution": {
    "name": "材料中的完整机构名称",
    "displayName": "真实简称·真实城市",
    "headline": "真实城市养老院实地看"
  },
  "facts": [
    {"id":"f1","source":"机构介绍.txt","quote":"从该文档复制的一段真实原文"}
  ],
  "sentences": [
    {
      "text":"爸妈住进养老院，平时在哪儿休息、活动？",
      "kind":"hook",
      "factIds":[],
      "label":"居住空间",
      "captions":[
        {"text":"爸妈住进养老院","lines":["爸妈住进养老院"],"focus":""},
        {"text":"平时在哪儿休息、活动","lines":["平时在哪儿","休息、活动"],"focus":"休息、活动"}
      ],
      "shots":[
        {"path":"公共空间.mp4","sourceStart":1.9,"weight":1.5,"positionY":62,"description":"实拍移动镜头中的公共休息区"},
        {"path":"居室.mp4","sourceStart":2.0,"weight":2.3,"positionY":60,"description":"居室床铺与沙发"}
      ]
    },
    {
      "text":"根据机构原文写出的真实介绍句。",
      "kind":"fact",
      "factIds":["f1"],
      "label":"日常服务",
      "captions":[{"text":"根据机构原文写出的真实介绍句","lines":["根据机构原文","写出的真实介绍句"],"focus":""}],
      "shots":[{"path":"服务空间.jpg","weight":1,"positionY":50,"description":"材料中的实际服务空间"}]
    },
    {
      "text":"想咨询参观，欢迎评论区留言。",
      "kind":"cta",
      "factIds":[],
      "label":"咨询参观",
      "captions":[{"text":"想咨询参观","lines":["想咨询参观"],"focus":"咨询参观"},{"text":"欢迎评论区留言","lines":["欢迎评论区留言"],"focus":"留言"}],
      "shots":[{"path":"公共空间.mp4","sourceStart":2,"weight":1,"positionY":50,"description":"结尾继续播放实际公共空间移动镜头"}]
    }
  ],
  "asrPrompt":"仅提供机构专名、地名等识别提示，不粘贴整篇原稿",
  "settings": {
    "closing_hook":{"enabled":true},
    "avatar":{"mode":"opening","x":48,"bottom":1500,"width":400,"height":550},
    "voice":{"speech_rate":-3}
  }
}
```

例子用于解释字段，事实与素材名必须替换为当前输入中的真实内容。照片只允许中段；首句 shots 全部是实际视频且观察到运动。`sourceStart` 是原片秒数；`weight` 是分配当前实测句长的相对权重，不是预先承诺秒数。源片剩余长度不够时构建报错，增加真实镜头或调整起点，不变速、不虚构动态。

`captions.text` 按原稿完整顺序覆盖整句；`lines` 保持同义同字，可把十号、二十四小时显示为10号、24小时，最多两行；focus 只高亮已有词。数字会先按中文读法归一化。超过既定字号可容纳宽度时重新断句，不能擅自缩小全片字幕。缺省 captions 会产生短句草稿，仍须审阅。

`facts.quote` 必须是当前输入文本的原文片段；每个 factual sentence 引用至少一条。validate-plan 只能验证来源存在、字幕覆盖与片源，不会证明所有改写关系都正确。机构名、城市、服务条件、数字与疗效等由智能体逐句核验；不把同一家包装成多家。泛化建议型开场可用 kind=hook，不能用它绕过事实核验。

时长由完整配音及词级对齐计算。默认只为开头完整句生成数字人，中间和结尾没有人物；出镜窗口留少量音频边界，结束只补齐不足一个视频帧。`mode` 可显式选择 off/opening/closing/both，缺省opening。只有一句时不会为同一句重复生成两个数字人。最后一条默认必须kind=cta并配真实视频，见[结尾引导](closing-hooks.md)。

可选设置依次继承 preset.json和用户项目settings；选择人物优先使用plan.person；更换人物用 settings.avatar.portrait（本地路径），表情用 settings.avatar.prompt。新任务默认配乐及替换／关闭方式见[默认配乐](runtime.md#默认配乐)。语音发音规则使用 settings.voice.pronunciation_dict.tone。模板当前固定1080×1920/30fps；其他画幅须明确改编模板。

正文只有 fullscreen-orange，无需选择模板。完整UI测量见[平台UI避让](platform-ui.md)，字形和断句规则见[排版](templates.md)。build保存 caption-characters.json；数字拆词按完整数值归一化，数字组只保留实际时间区间，不能从组内切 cue。自动断句仍需结合实际帧核对语义。

## 封面与发布字段

智能体在计划顶层填写：

```json
{
  "cover": {
    "main_title": {"text":"养老生活能有多丰富？","lines":["养老生活","能有多丰富？"],"highlights":["丰富"]},
    "labels": [
      {"text":"居住环境","source":"居室.mp4","time":2},
      {"text":"活动空间","source":"公共区域.jpg"},
      {"text":"院区环境","source":"门头.jpg","match":"同机构实图"}
    ]
  },
  "publication": {
    "title":"结合本条内容的发布标题",
    "description":"结合已核验事实及咨询动作的一段发布描述。",
    "topics":["养老院","养老生活","养老选择","养老院探访","养老咨询"]
  },
  "settings": {"cover":{"enabled":true},"closing_hook":{"enabled":true}}
}
```

封面 main_title 可直接给字符串，或提供 text、可选 lines 与 highlights；lines 必须保留 text 原字。labels 恰好三个，text/source 必填；time 为视频提帧秒数，图片不填。可选 crop 为 [左,上,右,下] 归一化裁切，focus 为 [水平,垂直] 归一化焦点。详细语义见 [封面](covers.md)。首帧静态例外只适用于独立封面层，正文首句仍全为真实视频。

settings.cover.image 可指定现成封面（本机绝对路径或 .montage 相对路径）；enabled=false 关闭首帧封面。头标继承项目设置。完整院名必须来自 institution.name；人物与社媒署名从绑定人物读取，不能在封面内容中另传其他署名。

本次钩子覆盖可用 settings.closing_hook.text 或 hook_id（二者择一），或直接写末句 CTA；留空 CTA text 时可选人物默认或项目咨询兜底，分镜仍必填。选择与来源保存 closingHookSelection，并随 runtime 冻结，不另增钩子清单文件。

publication 由智能体根据本条内容撰写，不要求用户填写。topics 恰好五个不同话题，包含或不含开头 # 均可，不能有空格。发布包需要封面和编辑 HTML；用户明确只要视频时可本次 settings.delivery.enabled=false，避免强制打包。

## 标题与发布事实复核

封面数字标签可加 `factIds:["f2"]`，publication顶层加共享 `factIds:["f2","f3"]`，引用当前facts原文。可选topic记录titlePromise和mainSentenceIndexes，shots.match说明直接展示或环境铺垫。validate-plan生成content-audit.json，按[内容复核](content-review.md)查看后再review-content；结构检查不替代语义核验。
