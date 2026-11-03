# 选择窗口并复核场景证据 r67b

此工具在不搬移／覆盖既有记录的前提下，独立验证固定r66构建、原生证据、指定原厂窗口、场景包及RAW／NV12／LCD区域。验证器运行成功、窗口完整、功能验收资格和实际功能通过分别记录。

## 选择要复核的窗口

在工程根目录PowerShell运行，输出文件必须不存在：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/verify_z62_paired_run.py --native-case 'analysis/z62-paired-handoff-r66' --run-directory 'analysis/z62-paired-host-r68/diagnostic-1' --output 'analysis/z62-paired-host-r68/my-new-verification.json'
```

正常模式要求完整55秒窗口、实际最终控制样本、正常detach／关闭及完整控制历史。保留原始严格恢复判据；统计停止时不会因为LCD像素成功而把严格恢复改成true。

中断／失败窗口默认拒绝。只重放已采样的部分证据时必须显式使用：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/verify_z62_paired_run.py --native-case 'analysis/z62-paired-handoff-r66' --run-directory 'analysis/z62-paired-handoff-r66/live-1' --allow-interrupted --output 'analysis/z62-paired-handoff-r66/my-new-partial-verification.json'
```

`--allow-interrupted`不会补齐缺失阶段或提升验收资格。旧live-1虽有两个匹配的新视频场景，`completed_requested_window`、`functional_acceptance_eligible`及两个功能gate仍false；live-2的QMP失联也按不完整保留。

## 判据与限制

| 字段 | 含义 |
|---|---|
| verification_completed | 此次哈希／包重建／已采样像素和声明一致性检查完成 |
| completed_requested_window | 最终控制样本达到要求的55秒，历史完整并正常关闭 |
| functional_acceptance_eligible | 完整且没有宿主调试器抓取或抓取错误等资格缺口 |
| video_pixels_verified_in_observed_samples | 已保存的视频前后来源标签及区域像素匹配；部分窗口也可能为true |
| video_functional_gate_passed | 上一项成立，且完整窗口具备功能资格 |
| photo_functional_gate_passed | 返回照片新来源与区域像素成立，且完整窗口具备功能资格 |
| strict_mode_recovery_verified | 原r49严格双流水恢复的原始结果，不由本工具放宽 |

宿主诊断目录必须带外层`paired-host-lifecycle.json`和所引用的host记录。外层抓取／错误资格覆盖未感知宿主附加的内层记录；宿主抓取不能被内层eligible=true隐瞒。普通ASCII字节相同副本且未附加调试器时，可保留资格。

包重建核对完整payload SHA及RAW参考；像素检查为4个RAW局部、12个NV12局部和4个LCD区域，不是全帧逐像素一致性。C级成像模型通过不能证明物理ISP、原厂编码存卡、AF或刷写安全。

专项9项先红后绿，当前全量618项通过。实际窗口及边界见[r68报告](../history/2026-11-03_验证-Z62模式场景闭环与宿主观察r68-report.md)。
