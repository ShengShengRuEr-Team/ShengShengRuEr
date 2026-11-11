# 播放器音量拖动修复（2026-11-11）

用户在学生端整卷页指出右侧音量圆点无法拖动。1196px 视口真实浏览器复现：`.player-volume .ant-slider` 实际宽度为 0，位置 x=1047。

原因是 Ant Design Space 为子元素增加包装，音量 Slider 没有可用宽度。改用直接 flex 容器，让滑块占用图标以外的剩余宽度；保留原有130px容器及900px以下隐藏音量控件的布局。给音量与播放进度的滑块手柄补充可访问名称。

![修复后音量滑轨可拖动，当前音量25%](screenshots/audio-player-volume-fixed-20261111.png)

## 本轮验证

- 学生端1196 / 1440 / 901px：滑轨均为110px，真实鼠标拖动到25%，HTMLAudioElement.volume同步为0.25；手柄数值一致。
- Home / ArrowRight / End分别验证音量0 / 0.05 / 1。
- 管理端1196px：打开试听后同样通过音量鼠标及键盘验证。
- 学生端390px：保持小屏既有布局，音量控件隐藏，进度拖动正常。
- 五个场景均用鼠标拖动进度至中点，23:36音频定位至约11:48；不产生额外音频请求，pageerror均为空。
- Node24.14.0 / npm11.9.0执行npm run build通过（含TypeScript检查）。设计机械检查无发现。保留已有构建分块大小提示。

上述5个场景全部PASS。复现前结果为FAIL（宽度0）；本轮未改后端、依赖版本或数据库，不重复宣称上轮252项测试已对本次新提交重跑。

可复用脚本：`frontend/scripts/acceptance-audio-controls.cjs`。通过WEB_URL、API_URL、STUDENT_PASSWORD、ADMIN_PASSWORD配置独立测试环境；PLAYWRIGHT_MODULE可使用已有安装，EVIDENCE_DIR可保存截图和JSON，不新增依赖。

本机证据在独立验收目录 `evidence/audio-drag-fix-20261111/`：baseline-results.json、results.json、截图、build.log和design-detector.json。初轮管理端脚本未打开试听、随后精确按钮名称又未包含图标名称，属于脚本问题；修正后完整5组重新执行并全部通过，保留initial-results.json及second-results.json。

上一轮主要验证音频播放、进度键盘定位及翻篇不断播，未覆盖音量鼠标拖动；本次补上真实鼠标动作与实际媒体音量的对照，避免仅凭控件显示正常判通过。
