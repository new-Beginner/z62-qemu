# 2026-11-04 r91 源码更新

本次在 r86 公开历史上增加 r87–r91 实现和文档。默认仍是 r69 QEMU 内核／r75 交互入口；独立 r89/r91 采集内核默认关闭，不附带 EXE 或 Nikon 固件。

## 新增内容

- MAIN／linear16／RGGB 来源包、CRC、时间身份、缓存读占用和代次生命周期。
- 冻结 RAW transfer、LUT8 量化区间与中点重建，明确区分编码域和线性域。
- 独立 QEMU 采集设备：有限 RAW12 配方、配置提交、冻结 LUT、worker、虚拟时钟 DMA、bank/ring、DMA 后事件 3/4/135、W1C 背压。
- r91 显式外部 MAIN 策略，兼容已观察的共享源字 `0x200040`，未知值继续拒绝，物理 source pair 未模拟。
- 原生探针、原厂窗口驱动、独立数值复核和选定摘要；补齐 README、功能／限制、构建、时间线及参考署名。

## 证据与适用范围

| Evidence | Finding | 后续路径 |
|---|---|---|
| r91 原始 C1.70，8.003360666 客体秒 | 14 次缓存接受、13 次实际 DMA、13 组原厂 CPU ACK；保存 6 帧、9,138,504 样本零差异 | 继续来源、所有权和统计／ISP 交付；ACK 不是高层工作完成 |
| 连续统计 0、预览 0、LCD 全黑 | 新采集路线尚未完成原厂取景／摄影 | 核对实验启用条件，不能靠修改旧 RAW 计数或补 ready 宣布成功 |
| 本地完整 Python 回归 701 项、零失败／错误／跳过 | 已有完整研究环境的历史回归通过 | 本次公开副本检查另见 [验证记录](VALIDATION.md)，没有重跑固件或 LibRaw |

本次发布副本实际通过 134 项无固件测试及 16 个 C case；902 个导出哈希、593 份 Python 内存编译和文档链接通过。最终文档回写后另做静态核对，详细范围及完整结果见上述验证记录。

[r91 摘要](evidence/capturework-original-r91.json)及[原件哈希索引](evidence-index-20261104.json)只分发选定事实和身份。原始 trace、RAM、MAIN／RAW、卡、固件、工具链和 NKN 恢复包不随公开源码分发。r87 首轮路径失败、r90 首轮 0 DMA 和非原子内核采样边界保留在阶段报告中。

## 尚未实现

新来源到统计／ISP 的完整桥、完整 run/stop 和 inflight 竞态验收、全局快照恢复、完整模式往返、原厂编码与客体存卡、真实镜头协议／PDAF／原厂 AF 闭环、整机及刷写安全认证均未完成。LUT8 重建不是原始像素恢复。本次没有修改 AF。

使用方法见 [采集后端说明](profiles/README-Z62-CAPTUREWORK-DEVICE.md)和[构建说明](BUILD.md)。参考与原作者列于 [REFERENCES](REFERENCES.md)，完整过程见 [DEVELOPMENT](DEVELOPMENT.md)。
