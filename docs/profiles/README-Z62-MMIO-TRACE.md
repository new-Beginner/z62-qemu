# Z62 输入写入时序诊断 r64b

此入口记录原固件对输入、ISP和paired区域的**写入尝试**。它用于区分停止后的不同输入请求，不改变设备回调、返回值、RAW停止规则或原厂软件状态。它还没有恢复模式切换后的新帧。

## 当前结果

| 项目 | 已验证结果 | 限制 |
|---|---|---|
| 独立内核 | QEMU 10.2.4，r64b，23层构建身份；仅system/memory.c和system/trace-events有差异 | 设备模型与r62相同，VMState仍52 |
| 默认关闭 | 新事件默认不输出；同时打开新旧事件时，新事件是既定窗口的精确投影 | 原生夹具检查不证明所有原厂写入都被接受 |
| 旧功能兼容 | trace ON、STOP ON下RAW停止／重启及旧统计、视频数值／DMA／拒绝检查通过 | 无固件native检查，不是整机验收 |
| 完整诊断窗口 | 55.097观察器计数器秒，8,587,716字节，61,217次写入；1225条master控制记录全部配对 | 126次停顿且发生宿主GDB附加，只作诊断 |
| 停止后请求 | 无新RAW DMA／formatter1配置；仍有paired几何、10=1、08=1和ISP命令 | paired请求不等于RAW端口重启，也不证明实际DMA |
| 功能恢复 | 严格恢复、视频和返回照片的新场景响应均false | 不以旧图、ready=3或日志完整代替恢复 |

内核：`.build/z62-mmio-filter-2026.11.03-r64b/runtime/qemu-system-arm.exe`，SHA256 `a8d1a24495add090ea35bb9f08e8f4efa2820f8e5991b54da04539fec132e08d`。新事件名`nikon_z62_mmio_write`，保留原`memory_region_ops_write`。地址窗口末端不包含：`[20060000,2006C000)`、`[20100000,20110000)`、`[20380000,20381000)`。

## 复现与复核

在工程根目录PowerShell运行，构建目录和输出目录必须是新目录。已构建r64b无需重复构建。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/build_z62_mmio_filter.py --jobs 8
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_mmio_filter.py --output 'analysis/my-new-mmio-native'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_mmio_filter_compat.py --output 'analysis/my-new-mmio-compat'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/trace_z62_mmio_filtered_lifecycle.py --output 'analysis/my-new-mmio-window' --card '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw' --group23 '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin' --duration 55
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/verify_z62_mmio_filter_evidence.py --directory 'analysis/z62-mmio-write-r64/live-filter-1' --output 'analysis/z62-mmio-write-r64/verified-filter-2.json'
```

最后一条复核当前冻结证据，要求相邻的`native-filter-3`、`native-filter-compat-1`和`rearm-ledger-1.json`保持原布局。输出已存在会拒绝，不覆盖旧回执。完整命令参数以各工具`--help`为准。

## 日志解释

事件位于设备回调之前；ISO时间前缀是宿主UTC，不是guest虚拟时间。`cpu=-1`保持unknown，不能强配master；同时间、同值重复写保留。已知事件格式损坏会报错。控制环按顺序逐条配对，不能跳过不匹配项找后续匹配；末尾超出最后样本的尝试单独保存。

首次模式统计停止对应control seq1144、frame924、QEMU ns30819299160、trace entry52369；第二次seq1178、frame1173、ns39105755949、entry56623。两停止后区间内formatter1、RAW DMA0..3、统计几何／DMA配置写入均为0；但视频paired几何05EC0356、core300／846／flags3，以及返回照片05EA03EE、core305／1002／flags1都有请求。不能据此把DMA word18命名为enable／auto-repeat或强开旧RAW latch。

全量旧事件的失败窗口保留在`analysis/z62-mmio-write-r64/live-1`：19.338计数器秒触及256MiB预算，未进入模式切换。过滤native前两次失败来自夹具未开启preview：2010／2038落入普通RAM，不产生MMIO事件；修正夹具后通过，没有为此改C过滤逻辑。

完整证据见复核回执（本地证据，未分发：`analysis/z62-mmio-write-r64/verified-filter-1.json`）、逐区间账本（本地证据，未分发：`analysis/z62-mmio-write-r64/rearm-ledger-1.json`）和[正式报告](../history/2026-11-03_验证-Z62地址过滤与停止后输入请求r64b-report.md)。宿主超时捕获只能说明采到了有效现场，单次栈不能诊断死锁或QMP根因。
