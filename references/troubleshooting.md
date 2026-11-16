# 按阶段定位故障

只在失败时读取相关条目。先保留阶段、完整错误码、脱敏日志、实际版本和任务状态；不把本次宿主问题推广成所有电脑的规则。

## 浏览器启动与连接

setup --install后先preflight，付费前验证页面和截图。失败看preflight.json、.preflight/check.log、snapshot.log；browserSkipped说明浏览器检查未完成，不证明版面不合格。check会区分runtime/layout/contrast等错误。

“Requesting main frame too early”只表示Puppeteer没有主框架，可能由进程启动失败、连接中断或初始化时序造成。结合浏览器stderr定位；没有启动证据，不盲目降级Chrome、换GPU或改字幕。

默认保留宿主与Chrome策略。优先使用宿主正式支持的执行通道；不覆盖全局浏览器入口、不修改npx缓存、不默认清空NODE_OPTIONS/PYTHONPATH。若确认特定宿主需显式浏览器策略，render.browser_sandbox接受inherit／required／disabled，映射锁定版本HYPERFRAMES_CHROME_SANDBOX；disabled仍是在关闭Chrome自身沙箱，不是通用兼容修复。仅在现有授权与宿主允许的边界内配置，不自动切换。封面与正文共用锁定浏览器运行时。

命令执行中断不等于没执行。云端提交先查run.json、task_id和服务端状态，不用文件mtime证明没有付费请求。broker宕机属于宿主故障，恢复后继续原任务。

## 配音与数字

ASR识别同音字不等于TTS读错。差异查看audio-check.json、alignment-check.json，结合原音核验；不能猜测放行。numericMapping失败是词级时间映射问题，应复用原音修正，不把“禁用三位数”或“每行八字”当通用标准。数字组不能内部切cue。

发音词典是服务请求参数，不保证纠正每次生成；确认发音疑点后再选择改写或重生成，保留对照，不能仅由ASR结果断定词典部分生效。

## 服务资源与凭据

保留原始供应商code、message、request_id、resource和speaker绑定信息（脱敏），按当前接口文档核对。not granted优先查对应资源授权；resource mismatched还可能是资源／音色绑定不匹配，不能把55000000固定解释为未开通。适配和中转详见service-runtime.md。

## 字体与交付

缺字／缺字体：修复明确的字体引用；不静默替换成粗黑体。字幕超宽：按实际测宽重排，复用音频。ZIP乱码先检查UTF-8标志和工具编码，不盲做cp437回转。编辑HTML必须实际验证修改、换图和PNG导出；缺动态验证时如实报告。

## 预览字体正常，实际视频变成默认字体

渲染编译可能丢弃子组合中的字体声明。正文渲染器已将实际用字的 WOFF2 子集嵌入主文档；不要仅把 `@font-face` 放在子模板。检查实际导出视频帧，不能只验收 snapshot。不要修改全局 npx 缓存。
