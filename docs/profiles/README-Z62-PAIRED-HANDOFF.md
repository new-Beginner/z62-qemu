# 软件输入来源交接修正 r66

r66修正r65的C级模型缺陷：旧RAW遗留通知没有被ISP调度时，仍会阻止新paired输入。新版本保留真实待消费输出、已调度旧工作和本源未消费输入的保护；只有新场景实际DMA成功后，才替代无调度的非本源旧通知，并累积只读`paired-ingress-retired-notifications`。它不发额外完成、不清guest ready／队列、不重开RAW。

**r68完整55.021秒窗口中，视频两次换景及返回照片新场景均已通过来源和LCD区域复核；严格双流水恢复仍false。** 沿用同一r66模型，实际宿主抓取0次，具备该项功能评估资格。live-1的用户中断和live-2的QMP失联记录保留；QMP根因仍未知。详见[r68报告](../history/2026-11-03_验证-Z62模式场景闭环与宿主观察r68-report.md)。统计新来源、原厂媒体、镜头及AF仍未实现，默认交互入口未升级。

## 结果与边界

| 项目 | r65 | r66原生结果 |
|---|---|---|
| 一个旧RAW通知，尚未运行ISP | 新源0批、视频0批，所有完成pending为0仍backpressure | 旧RAW仍1帧且停止，新源1批、视频1批，真实DMA后出现8／61／1002完成，retired=1 |
| 已调度的旧事务 | 需要保护 | 先完成旧事务，未算作遗留通知；待真实ack后才消费新白场 |
| 替换预检失败 | 不能假完成或丢通知 | 未写任何源槽、retired保持0；地址修复后实际写入再retire=1 |
| 原有新帧数据与生命周期 | 15项原生门槛通过 | 全部仍通过，默认off、别名／地址拒绝、背压、停止／重启、reset、两种场景、旧RAW兼容均保留 |
| Python及旧套件 | 609项 | 当前609项／258.920秒通过；旧统计／视频STOP ON、trace ON、新源默认OFF兼容通过 |
| 原厂新场景 | r65仅返回照片通过 | r68视频40→210及返回照片publication3通过；427批实际新输入，严格恢复仍false |
| 物理协议与整机 | 未完成 | 没有扩大为物理等价、完整快照、原厂拍摄存卡或AF验收 |

内核：`.build/z62-paired-handoff-2026.11.03-r66/runtime/qemu-system-arm.exe`，SHA256 `22f77a97da26d190f8c92cf6059466042bd092510a1555865c13f8c71da6858e`。25层身份，VMState54。仅board及paired header两份生成源变化，保留r65。原有C场景、packed12和视频格式桥的近似范围见[输入说明](README-Z62-PAIRED-INGRESS.md)。

## 使用

工程根目录PowerShell执行，输出必须是新名称。已完成的固定构建目录不可覆盖，无需重复构建当前r66。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/build_z62_paired_handoff.py --jobs 8
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_paired_ingress_handoff.py --qemu '.build/z62-paired-handoff-2026.11.03-r66/runtime/qemu-system-arm.exe' --output 'analysis/my-new-r66-handoff.json'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_paired_ingress.py --qemu '.build/z62-paired-handoff-2026.11.03-r66/runtime/qemu-system-arm.exe' --output 'analysis/my-new-r66-native.json'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/trace_z62_paired_handoff_lifecycle.py --output 'analysis/my-new-r66-window' --card '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw' --group23 '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin' --duration 55
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/verify_z62_paired_run.py --native-case 'analysis/z62-paired-handoff-r66' --run-directory 'analysis/z62-paired-host-r68/diagnostic-1' --output 'analysis/z62-paired-host-r68/my-new-verification.json'
```

新模型沿用同一显式`z62-paired-ingress`开关，默认关闭；`run_z62_paired_handoff.configure_command`仍要求显式RAW停止模型及paired配置。最后一个命令同时核对冻结native证据和指定的完整窗口；[r67b工具](README-Z62-PAIRED-RUN-VERIFY.md)可明确选择目录，避免旧验证器固定选取已中断live-1。失败和部分窗口不会提升为通过。

## 证据

r65最小失败（本地证据，未分发：`analysis/z62-paired-ingress-r65/handoff-1.json`）、r66交接验证（本地证据，未分发：`analysis/z62-paired-handoff-r66/handoff-2.json`）、全部来源原生检查（本地证据，未分发：`analysis/z62-paired-handoff-r66/native-3.json`）、旧套件兼容（本地证据，未分发：`analysis/z62-paired-handoff-r66/compat-1/native-compat-check.json`）及首次复核（本地证据，未分发：`analysis/z62-paired-handoff-r66/verified-native-1.json`）均保留。

本修正处理模型内部来源代次和所有权。retired计数不是guest完成，也不是修复尼康硬件协议的证据。真实pending结果不会被此路径清除，DMA故障不会发布完成；不承诺任意中途I/O故障的内存回滚。完整原厂结果见[阶段报告](../history/2026-11-03_修复-Z62软件来源交接r66-report.md)和[能力表](../CAPABILITY-COVERAGE.md)。
