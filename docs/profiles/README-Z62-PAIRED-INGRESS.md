# 独立软件paired帧源 r65

r65为既有软件ISP增加默认关闭的C级输入模型：旧RAW stream停止后，响应原厂已提交的paired请求，从现有场景邮箱生成新的四槽RAW数据。它不重开旧RAW、不生成统计结果、不直接发完成中断。MAIN／WORK／预览及结果完成继续由既有软件ISP在计算和DMA后负责。

**原生数据与生命周期检查通过；r65原厂55秒场景中，返回照片的新场景响应通过，视频仍失败。** 旧来源通知交接缺陷已在[独立r66](README-Z62-PAIRED-HANDOFF.md)修正并通过原生回归，r66原厂窗口待终态。严格模式恢复、原厂录像编码和完整相机均未通过。默认交互入口未升级，AF算法未改。

## 已验证与限制

| 内容 | 当前结果 | 边界 |
|---|---|---|
| 独立QEMU | r65、QEMU10.2.4、24层身份，VMState53 | r64b及父内核保留；不是向旧快照兼容的设备版本 |
| 来源 | 复用同一scene mailbox；ramp及另一幅白场逐字节匹配四个RAW槽 | 1514×1006、实验packed12，非全分辨率物理传感器 |
| 视频数值 | MAIN、WORK、预览对独立oracle通过，换白场后数值随之变化 | 使用已有C级视频格式桥和显式origin，不是原厂ISP数学等价 |
| 旧RAW停止 | 新来源写入时旧active=false、frames=0、accepted=0、无RAW完成 | 软件输入本身不产生RAW／统计IRQ |
| 同时启用选项 | 旧RAW活动时软件源退出；旧RAW实际DMA及视频数值仍通过 | 不允许两个源竞争同一缓冲 |
| 拒绝／生命周期 | 缺场景、晚出现的非法源地址、别名、背压、停止、显式paired重启、slave隔离、reset通过 | DMA故障不发布完成；不承诺任意中途I/O失败的内存事务回滚 |
| 回归 | Python609项；新EXE上旧统计／视频数值、DMA、拒绝套件通过 | 旧套件中paired默认OFF；新ON数据检查单列，不混作原厂恢复 |
| 原厂场景 | 55.070计数器秒完成并关闭，返回照片publication3及RAW／NV12／LCD区域通过；视频0批、严格恢复false | 无宿主调试器附加；3次QMP超时恢复、不重发控制；区域核验不是全帧逐像素或整机验收 |

EXE：`.build/z62-paired-ingress-2026.11.03-r65/runtime/qemu-system-arm.exe`，SHA256 `1e224c3f13d4919d36c4c0c1724d0d65bd283041b609286c305ba1728de5eccd`。

## 运行与复核

工程根目录PowerShell，输出名称必须全新。构建目录已存在时builder会拒绝，不必重复构建已完成的r65。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/build_z62_paired_ingress.py --jobs 8
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_paired_ingress.py --output 'analysis/my-new-paired-native.json'
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/trace_z62_paired_ingress_lifecycle.py --output 'analysis/my-new-paired-window' --card '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw' --group23 '<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin' --duration 55
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/verify_z62_paired_ingress_evidence.py --directory 'analysis/z62-paired-ingress-r65' --output 'analysis/z62-paired-ingress-r65/verified-native-2.json'
```

最后一条用于复核当前冻结目录的`native-3.json`和`compat-1`，会核对当前probe、C适配器、两份头文件、五份生成源变化及所有日志SHA。如`live-1`已有终态产物，也会把其真实通过／失败标志纳入回执，不把native成功扩大为整机成功。

手工配置入口为`run_z62_paired_ingress.configure_command`，要求显式`stop_control=True, paired=True`；C侧还要求preview／results已启用。使用同一`/machine/master-input`场景发布与消费状态。仅有属性或控制写入不产生像素，没有场景就拒绝，不回退固定图。

## 合同和观测

支持本项目已测的照片`05EA03EE／2272／305／1002／flags1`和视频`05EC0356／2288／300／846／flags3`配置，视频还须通过已有的完整数值profile。paired08=1启动软件输入；关闭paired08／10、core2608／引擎或进入已知drain会停止。单改回flags不会静默重启，须再提交paired请求。这些是**此C模型的明示规则**，不是对物理芯片控制寄存器的完整解释。

每次写入前在BQL下检查四个源地址及相关输出的RAM范围、权限和实际backing别名，再从已验证场景复制数据。仅在四次RAW写入成功后更新来源代次、记录原始场景标签与投递虚拟时间，通知既有ISP有新输入。外部帧编号／时间戳不会被投递次数改写；重复静态帧仍保留原标签。33,333,333ns为软件节奏假设，不是实机30fps精度或QEMU性能验收。

一个cohort的四槽使用同一幅场景，这是既有视频输出别名合同限定的C级近似，不是四相曝光、运动采样或PDAF真值。不能用这些普通合成RAW评价上游相位估计。

boot设备新增只读`paired-ingress-active/attempts/frames/bytes/rejected/blocked/publish-id/dma-time-ns/reason`。`scene-used-*`仍表示实际RAW消费；LCD是否使用新图需要单独验证。pending结果未消费时，不覆盖缓冲或发新完成。未实现新的统计来源，因此严格双流水恢复保持独立判据。

r65的额外交接缺陷：视频阶段backpressure126次但未产生新cohort；最小handoff复现（本地证据，未分发：`analysis/z62-paired-ingress-r65/handoff-1.json`）在所有硬件完成pending为0时仍因旧RAW通知停住。此缺陷没有通过清ready／队列绕过，r65源码和失败证据保留；[独立r66](README-Z62-PAIRED-HANDOFF.md)仅修正未调度旧通知的所有权处理，已构建并通过原生回归，原厂新窗口待终态。

详情见[阶段报告](../history/2026-11-03_实施-Z62独立软件paired输入r65-report.md)、原生回执（本地证据，未分发：`analysis/z62-paired-ingress-r65/native-3.json`）、复核（本地证据，未分发：`analysis/z62-paired-ingress-r65/verified-native-1.json`）及[能力清单](../CAPABILITY-COVERAGE.md)。完整系统快照、原厂媒体存卡、音频、镜头协议和原厂AF闭环仍未完成；此实验不能证明实机刷写安全。
