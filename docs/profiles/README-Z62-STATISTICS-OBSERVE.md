# 双引擎统计诊断 r60

本层用于查清照片→视频→照片后统计／grid不持续的原因。它只增加只读观察，默认关闭；不修正统计模型、不补帧、不发新完成、不改原厂ARM。r59b及其已构建源码保留。

独立r60已构建，新旧原生回归及589项Python回归通过。完整双CPU寄存器观察首轮在11.064秒后QMP失联，失败产物保留；独立r60q只追加QOM读取，已完成55.160观察器计数器秒，严格恢复仍未通过。详见[阶段报告](../history/2026-11-03_实施-Z62双引擎统计诊断r60-report.md)。

## 构建与运行

在工程根目录的PowerShell执行。需要既有固定QEMU10.2.4／MSYS2环境，以及至少12GiB可用空间；builder先校验r59b及源文件哈希，再建立独立源码／构建目录。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/build_z62_statistics_observe.py --jobs 8
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_statistics_observe.py --qemu '.build/z62-statistics-observe-2026.11.03-r60/runtime/qemu-system-arm.exe' --output 'analysis/z62-statistics-observe-r60/native-1.json'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/trace_z62_statistics_status_lifecycle.py --output 'analysis/my-new-r60-status' --card '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw' --group23 '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin' --duration 55
```

输出位置必须尚不存在，避免覆盖旧证据。原厂窗口复用r59b显式C视频origin(0,76)与场景变化；此坐标是软件夹具，不能当作实际传感器ROI。只使用专用虚拟卡的snapshot后备，不连接相机。

## 新增观察

| 对象 | 属性／数据 | 含义 |
|---|---|---|
| 两个BootConfig | `statistics-model-started` | 旧模型的有限统计启动锁存 |
| 两个BootConfig | `statistics-model-support`／`statistics-model-enable` | 旧模型资格，以及资格／启动锁存／reg10 bit10的联合表达式 |
| 两个BootConfig | `statistics-control-trace` | JSON写入环，容量256；仅控制地址族，含全值／写后mask／前后started／候选CPU和PC／虚拟时间／帧计数 |
| 两个BootConfig | `statistics-control-count` | 已记录控制写入总数，也是环内sequence来源 |
| 两个BootConfig | `statistics-frame-calls`／`statistics-frame-pulses` | bridge被调用次数／旧模型实际满足资格并发帧脉冲次数；不是成功统计帧数 |
| 两个BootConfig | `statistics-commit-pulses` | 旧模型满足资格且100 bit8提交的次数；不是成功DMA数 |
| 两个Input | `continuous-enabled/active/rearm/clock-level` | 连续统计内部现态，均只读bool |
| 宿主采样 | controls、formatter、93词geometry、73词DMA、两组计数 | 分别使用当前board的CPU0／CPU2虚拟地址视图，未跨寄存器洞整段读取 |

控制地址族为`20068000/04/08/0C/10/14/18`及`20068100`。环不会被大量MMIO读取淹没。历史`reason=success`不证明当前设备仍使能，成功帧必须查真实帧数／DMA证据。

`z62-statistics-observe=on`显式启用记录；只读getter在关闭时仍可读取。原bridge重命名后由包装器调用一次，原运算和IRQ条件不变。VMState51/min51包含诊断数组与计数；这不代表整机快照恢复已经验证。

## 证据边界

`collect(machine, cache)`严格发现唯一master／slave。角色重复或缺失会失败；单个引擎或属性读取失败会保存错误及`None`，另一引擎的已知数据仍保留，不伪造零。bool必须是真正bool。

所有采样标为非原子：CPU继续运行时，先后读取之间可能发生变化。控制环内部一条记录对应一次控制写入，可与周期样本联合判断；候选PC必须再对原始指令核实，不能直接叫写指令地址。QTest没有当前CPU时，记录`cpu=-1/pc_valid=false`。

完整原始环保留在每个样本中。观察器按角色和sequence去重，缺号单列`sequence_gaps`，不补造记录。`completed_observation`只表示观察窗口完成；`control_history_complete`另受缺号和读取错误约束。严格模式恢复继续采用旧r49判据。

早先“+14清启动锁存导致本次停止”的假说已被本窗口否定：实际记录sequence1109是`2006800C=0x10`，PC候选`1020A832`，启动锁存true→false；到最后采样点没有新的`20068008`启动写入。下一步应研究实际停止／重启条件，不直接删+14或强行开启统计。

## 原厂窗口与时钟边界

`status-1`已完成55.160观察器计数器秒／970.82宿主秒，348停顿、27份双引擎样本、1907条master控制记录／slave0条，来源和记录重建复核通过。视频灰40→210以及返回照片灰40均重算匹配RAW／NV12／LCD；严格r49恢复仍false。

QOM变体明确不追加双CPU寄存器采样，`mmio_registers_collected=false`。有完整原始环的已采区间为0.008–53.757观察器计数器秒，无缺号；最后1.403秒未抓控制环。旧输出`control_history_complete=true`只说明已采记录连续，**不能解释为整个55.160秒无遗漏**。新复核回执明确给出`full_window_control_history_verified=false`。

写入环的`qemu_virtual_ns`直接取`QEMU_CLOCK_VIRTUAL`，原观察器`virtual_seconds`来自`04266008`计数值／48MHz。固定QEMU的generic timer使用整数周期20ns，因此存在约25/24比例及初始化偏移；两种时间不能直接相减。本次停止写入记录为29.844265906 QEMU秒／frame895，以sequence和frame计数对照样本，不按两类秒值直接排序。

候选PC中有3条落在`1020AB28`的LDR，即写助手入口，实际STR在`1020AB2A`；其余候选PC经原始固件反汇编核对为STR。当前PC不是逐条精确写指令追踪。

复核已存在的记录：

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/verify_z62_statistics_observe_evidence.py --directory 'analysis/z62-statistics-observe-r60/status-1' --status-only --output 'analysis/my-new-r60-verification.json'
```

需要复现完整寄存器观察失败时，用`trace_z62_statistics_lifecycle.py`及新的输出目录；不要把它与QOM变体的覆盖或结果混用。原失败目录为`analysis/z62-statistics-observe-r60/live-1`。最新复核为verified-status-2.json（本地证据，未分发：`analysis/z62-statistics-observe-r60/verified-status-2.json`），保留首版复核回执。

## 当前构建与原生检查

独立EXE为`.build/z62-statistics-observe-2026.11.03-r60/runtime/qemu-system-arm.exe`，SHA256为`f8835bb8b0145db797f4d28782c9400876af364511e1f093b6866b062c0ee6ab`。21层身份链已由`run_z62_statistics_observe.verify_build()`现场核对。

新原生检查（本地证据，未分发：`analysis/z62-statistics-observe-r60/native-1.json`）、连续统计回归（本地证据，未分发：`analysis/z62-statistics-observe-r60/continuous-regression.json`）和视频回归（本地证据，未分发：`analysis/z62-statistics-observe-r60/video-regression.json`）均通过。关闭／开启观察器都实际产生一帧26240字节统计；环容量、只读、复位、从引擎隔离及真实双CPU视图通过。QTest没有运行原厂固件，不能据此确认停止根因或模式恢复。
