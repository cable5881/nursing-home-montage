# 内部计划数据

用户只提供机构素材。由智能体阅读 inventory.json/source-text.txt、观察视频图片后编写 job/plan.json，不把填 JSON 的工作交给用户。

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
      "text":"给长辈选养老院，先看生活空间，再看照护安排。",
      "kind":"hook",
      "factIds":[],
      "label":"居住空间",
      "captions":[
        {"text":"给长辈选养老院","lines":["给长辈","选养老院"],"focus":""},
        {"text":"先看生活空间","lines":["先看生活空间"],"focus":"生活空间"},
        {"text":"再看照护安排","lines":["再看照护安排"],"focus":"照护安排"}
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
    }
  ],
  "asrPrompt":"仅提供机构专名、地名等识别提示，不粘贴整篇原稿",
  "settings": {
    "avatar":{"mode":"both","x":48,"bottom":1500,"width":400,"height":550},
    "voice":{"speech_rate":-3}
  }
}
```

例子用于解释字段，事实与素材名必须替换为当前输入中的真实内容。照片只允许中段；首句 shots 全部是实际视频且观察到运动。`sourceStart` 是原片秒数；`weight` 是分配当前实测句长的相对权重，不是预先承诺秒数。源片剩余长度不够时构建报错，增加真实镜头或调整起点，不变速、不虚构动态。

`captions.text` 按原稿完整顺序覆盖整句；`lines` 保持同义同字，可把十号、二十四小时显示为10号、24小时，最多两行；focus 只高亮已有词。数字会先按中文读法归一化。超过既定字号可容纳宽度时重新断句，不能擅自缩小全片字幕。缺省 captions 会产生短句草稿，仍须审阅。

`facts.quote` 必须是当前输入文本的原文片段；每个 factual sentence 引用至少一条。validate-plan 只能验证来源存在、字幕覆盖与片源，不会证明所有改写关系都正确。机构名、城市、服务条件、数字与疗效等由智能体逐句核验；不把同一家包装成多家。泛化建议型开场可用 kind=hook，不能用它绕过事实核验。

时长由完整配音及词级对齐计算。首尾窗口按完整句选择，并留少量音频边界；结束只补齐不足一个视频帧。`mode` 可选 off/opening/closing/both。只有一句时不会为同一句重复生成两个数字人。

可选设置依次继承 preset.json和用户项目settings；选择人物优先使用plan.person；更换人物用 settings.avatar.portrait（本地路径），表情用 settings.avatar.prompt，换音乐用 settings.music.resource（绝对本地路径，或.montage相对路径，并设置enabled=true）。语音发音规则使用 settings.voice.pronunciation_dict.tone。模板当前固定1080×1920/30fps；其他画幅须明确改编模板。
