# r17 RAW输入边界合同

此扩展在独立r13源码快照上构建，默认关闭，不修改原固件或冻结r13文件。它补充原厂输入边界事件，不提供统计、任意ISP算子或照片完成。

## 已确认的消费者

bank0 status `20068210 bit0` → IRQ94 → 原厂`10238FF2(41072800,payload)`读取payload bit0 → 任务事件1 → `10238B8A` → `041A000F` → `1022F17A`置C1887CDC bit4。软件事件与标志完全由原厂执行。

`analysis/z62-capture-r17/frame-delivery-baseline`完整3.002秒，无bank0回调或041A000F；掩码5等待重复超时。`frame-delivery-pulse`完整3.054秒，仅在1.463秒且已验证16次原生RAW批次与内存前缀后测试一次input-event0：1.469秒经过原厂消费者，1.546秒下一次掩码5等待立即返回1；之后又恢复超时。该次脉冲仅用于路线诊断，不加入启动器。

## 功能模型与限制

- 正常帧时钟和原生测试帧引脚均先调用既有RAW源；仅该调用导致成功RAW批次数增加时才报告bank0 bit0。
- 原有RAW源已经验证主引擎、启动/使能/停止、重复高电平、背压和实际四槽DMA成功。失败、停止、复位后未启动、从引擎、无关直接DMA均不产生该边界。
- 事件沿用硬件状态锁存、掩码、IRQ94和W1C。RAW通道2完成仍使用独立bank4 bit8/IRQ96；清其中一路不清另一路。
- 新只读计数raw-boundary-events记录源边界次数，raw-boundary-coalesced记录上次bit0尚未消费时又发生边界。复位清零，VMState版本44保存计数。
- 边界与成功DMA同一帧关联，是明确的功能时序假设；尚未有真机波形证明其前后相位。不会称其为硅片精确的帧开始或帧结束。
- 该事件不产生统计数据、不设置其他ready位，不改软件队列容量或丢弃旧工作。另一路约200毫秒输入处理等待仍需恢复真实数据合同。

构建：`python -X utf8 -B tools/build_z62_raw_boundary.py --jobs 12`。
原生验证：`python -X utf8 -B tools/probe_z62_raw_boundary.py --output analysis/z62-capture-r17/native.json`。
所有输出目录/文件独占创建，已保存证据不能覆盖。仅构建或原生测试通过不构成整机验收；默认CMD仍为r13+r16宿主。
