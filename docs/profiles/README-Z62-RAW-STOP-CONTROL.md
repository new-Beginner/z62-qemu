# RAW停止请求独立实验 r62

此层仅在`z62-raw-stop-control=on`时让RAW来源处理`2006800C bit200`。默认关闭，原r60及其已验证的原厂窗口保留。目前构建状态以独立build manifest和实际原生回执为准，不能把源码已写好当作验收通过。

独立构建已成功，EXE SHA256 `28b09a6294c09370d86f8c28f71599c53db11d52b94a3784360948321b1370d2`，22层身份核对通过。新原生停止／重启（本地证据，未分发：`analysis/z62-raw-stop-control-r62/native-1.json`）、旧统计回归（本地证据，未分发：`analysis/z62-raw-stop-control-r62/statistics-regression.json`）与旧视频回归（本地证据，未分发：`analysis/z62-raw-stop-control-r62/video-regression.json`）均通过。原厂对照是下一门槛，尚不能把设备停止修正称为模式恢复通过。

## 为什么需要实验

[r61报告](../history/2026-11-03_研究-Z62统计停止调用链与RAW停止缺口r61-report.md)核对了切换时原厂逻辑停止掩码2EB。旧RAW来源忽略+0C，与统计bridge不同。原生红阶段（本地证据，未分发：`analysis/z62-statistics-control-r61/raw-stop-red.json`）实际看到写0C=200后仍active、帧数1→2、四个RAW槽重新写入。

新层只把该停止请求加入旧RAW停止锁存条件；+14／+18及其他模型计算保持原样。停止后边界不产生新RAW DMA，重新启动仍要求原厂+08 bit200。它不补发完成、不重发控制、不强开统计，不等同恢复问题已经修复，也不证明物理硅片完整等价。

## 构建和原生验证

工程根目录PowerShell，使用已固定QEMU10.2.4／MSYS2和隔离Python，至少12GiB可用空间。独立目录不会覆盖r60；输出不得覆盖旧证据。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/build_z62_raw_stop_control.py --jobs 8
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_raw_stop_control.py --output 'analysis/z62-raw-stop-control-r62/native-1.json'
```

原生检查要求：默认关闭保留旧行为；开启后实际停止、四RAW槽保持不变、重复边界不重放；其他停止位不影响本RAW通道；显式+08重启后实际DMA和guards通过；旧RAW原生回归仍通过。失败时保留回执并定位，不能跳过进入原厂验收。

VMState52/min52只增加配置bool；不声称兼容旧51快照或整机迁移。runner核对22层身份和生成源哈希。使用C视频时仍须显式给出偶数origin，例如既有夹具(0,76)，它不是已恢复的真实传感器ROI。

后续原厂对照必须同时观察输入停止／新启动、RAW／统计／grid、旧r49恢复条件和场景像素。只有停止行为原生检查、旧回归和原厂窗口分别通过，才能相应报告能力；完整相机、原厂媒体、镜头／AF和实机刷写安全继续未验收。

通过原生门槛后可运行同一原厂场景，输出必须为新目录：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/trace_z62_raw_stop_lifecycle.py --output 'analysis/my-new-raw-stop-window' --card '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw' --group23 '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin' --duration 55
```

`completed_observation`只表示观察窗口完成。另查`strict_mode_recovery_verified`、视频／返回照片的新像素标志，以及实际帧计数。停住来源后出现的其他依赖缺口应如实保留，不能靠再造帧或完成绕过。

## 当前原厂观察限制

新native和ON下统计／视频兼容检查均通过，但首个原厂窗口`analysis/z62-raw-stop-control-r62/live-1`因连续QMP观察超时，在18.967计数器秒结束，未进入模式切换；因此不能判断完整恢复效果。失败产物保留，详见[r62阶段报告](../history/2026-11-03_实施-Z62显式RAW停止控制r62-report.md)。下一步先保全宿主超时线程栈，不扩大原厂或QMP超时取得成功。

后续[r63b完整对照](../history/2026-11-03_验证-Z62停止后新来源与宿主观察r63-report.md)完成55.117计数器秒，零QMP超时／零宿主附加。结果仍是严格恢复false：stream停止后没有持续新来源，video批次0；返回照片时旧灰度匹配但消费ID陈旧，完整新场景响应false。当前停止／只由新08启动是本实验模型的规则，不等于真实硬件完整合同。选项保持默认关闭，下一步核对DMA／commit重新武装与输入源，不能逼原厂额外启动或直接强开状态。
