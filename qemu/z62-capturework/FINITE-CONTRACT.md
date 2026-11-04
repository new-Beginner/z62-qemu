# r98：保留 CW 图像的有限统计来源

实现层级为 B 级有限传输、C 级数学，结合 A 级原厂提交／消费。属性 `z62-capturework-finite` 默认关闭，旧 r93 和默认 r75／r69 保持。**同一保留图像的 61 次采样不是 61 次新采集，也不是 PDAF。**

## 来源和所有权

1. 必须同时启用 CW 和 `functional-finite-stats`。缺依赖时拒绝 realize。
2. 仅在 CW 全部有效行实际 DMA 成功后保留量化 linear12 图像、按值 transfer、epoch／publication／frame／time、代次及 RAW 地址／bank／slot。
3. CW stop 和配置变化保留 latest；global reset／unrealize 清除。已取消或失败的 CW 不能成为来源。
4. finite_prepare 从私有来源计算并冻结一个 batch，后来的实际 CW 只替换 latest，下次请求选 latest；不能改变正在运行 batch。
5. 旧 `raw_accepted` 始终保持原合同，不为使 finite gate 通过而增加。

MAIN、编码 RAW 和量化线性域分开。LUT8 丢失低位，linear12 为冻结量化区间中点，不称恢复原始样本。

## 数学和传输范围

当前有限配方为 1514×1006 输入、30×12 LE-u16，row64，共 768 字节。每格采用整数边界分区的区域均值，四舍五入；每行末尾 4 字节为 0。它是静止保留图像的 C 采样模型，没有真实噪声、传感器时间或 Nikon 测光标定。

保留原有限引擎的 61 槽、目标资格、实际 DMA、IRQ、W1C、取消及下一批请求合同。缺 source、非法跨度和 source/output canonical RAM alias 必须拒绝；没有 DMA 成功就不能报告完成。不写原厂软件 ready／返回值／队列，不改等待时间。CW 仍共享既有 worker，不支持启用状态下的完整迁移／快照。

## 当前验证范围

| 检查 | 实际结果 | 限制 |
|---|---|---|
| native 两个输入、两批 | 122 次 DMA、93,696 字节独立重算一致；4 进程 exit0 | 合成 CPU，不运行原厂固件 |
| native 生命周期／拒绝 | 停采保留、owned batch 不变、下次 latest、缺来源、取消不保留、reset、alias、default-off legacy gate 通过 | 不等于全部并发时序穷尽 |
| 原厂 16.000750250 秒 | 33 CW／group、32 连续统计；122 有限采样／2批／0拒绝 | 两批都用 publication33／frame61，不是新 RAW |
| 原厂保存两份 scalar | 1,536 字节从保留 packed12／冻结 LUT 独立重算，零差异；CPU0 bit7 ACK 写入7次 | 每批只保存一份 scalar，不称逐份核对全部原厂122次DMA |
| 最终原厂 LCD | 出现要求关机再开机的 Error，预览0、CW未恢复 | 完整摄影和恢复失败，不提升默认入口 |

source、builder、adapter、generated files、EXE 与回执通过 SHA 绑定并归档。原厂原始图像／卡／完整轨迹留在本地，公开分发选定摘要。完整说明及复现见 [r96–r98 报告](../../docs/history/2026-11-04_实施-Z62连续供帧与保留帧有限采样r96-r98-report.md)。

构建依赖顺序为 r91 policy → r92 CW statistics → r93 capture group → r98 retained finite；r94–r97 是参数／观察／供帧工具，不需要另造内核。新克隆须先具备父构建、工具链锁与合法输入。

```powershell
python -X utf8 -B tools/build_z62_capturework_statistics.py --jobs 4
python -X utf8 -B tools/build_z62_capture_group.py --jobs 4
python -X utf8 -B tools/build_z62_capturework_finite.py --jobs 4
```

参考 nightglasses 的采集研究与本工程既有有限统计模型；当前新缓存、所有权和数值边界在独立 r98 适配层实现，保留 GPL 与上游署名。尚未实现 readout／ISP 全链、原厂编码／存卡、真实 AF/PDAF、镜头反馈或刷机安全认证。
