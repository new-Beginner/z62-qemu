# Z62 r87–r91 独立 MAIN 与采集设备

后续源码已推进到r98，默认入口仍r75／r69。本页保留r87–r91合同；r92连续统计、r93采集组、r95虚拟参数、r97连续源与r98有限来源的当前状态见[总览](../../README.md)、[参数合同](../../qemu/z62-capturework/GROUP-PARAMETERS.md)及[有限来源合同](../../qemu/z62-capturework/FINITE-CONTRACT.md)。r98最终原厂Error、preview0，完整相机仍未通过。

本路线把显式软件 MAIN 帧经过两级缩小、冻结 LUT 和 RAW 打包后，通过独立 QEMU 设备写入客体内存。**默认关闭，默认交互入口仍为 r75 界面／r69 内核。** r91 原厂窗口确认了 DMA 与原厂 CPU 中断 ACK，下游统计、预览和原厂摄影存卡尚未贯通；本实验不能认证候选固件的真机更新安全。

## 选用哪个版本

| 阶段 | 实现 | 验证与边界 |
|---|---|---|
| r86 | C11 两级有理 nearest、CFA 相位、LUT、RAW12/14/16 | 独立数值原语，不是硅片 ISP 公式 |
| r87 | MAIN／linear16／RGGB 包、CRC、时间身份、单缓存读占用 | 与旧辅助 Z62S 分开；CRC 仅检测传输损坏 |
| r88 | 不可变 RAW transfer 和量化区间重建 | LUT8 不能无损还原：输出区间 `[i*256,i*256+255]`，代表值 `i*256+128` |
| r89 | 有限 RAW12 配方、真实配置提交、bank/ring、worker、虚拟时钟 DMA、W1C 背压 | 有效行全部写回后发事件 3、4、135；提交前取消、复位等有原生测试，未穷尽 inflight 竞态 |
| r91 | 独立适配层，显式外部 MAIN 共享源策略 | 开启后接受已观察字 `0x200040` 和 0，未知 `0x200041` 仍拒绝；物理 source pair 未实现 |

当前几何为 `2020×1342 → 1514×1342 → 1514×1006`，RAW12 stride 为 2272。它是受限配方；支持独立 RAW14/16 数值运算，不等于 QEMU 后端已经支持所有 RAW14/16 配置。

## 构建与开关

完整研究环境在 r69 output-lineage 父构建、工作目录内 r73 工具链锁及原始源绑定之上构建；公开仓库不附带这些缓存或固件。下列命令需要先按公开 `docs/BUILD.md` 准备父构建与依赖。本次发布没有在空系统重编整条链，不应删除 manifest／SHA guard 绕过缺失。

```powershell
python -X utf8 -B tools/build_z62_capturework.py --jobs 4
python -X utf8 -B tools/build_z62_capturework_policy.py --jobs 4
```

r89 使用 `tools/run_z62_capturework.py`，r91 使用 `tools/run_z62_capturework_policy.py`。底层属性分别为：

```text
-global nikon-z72-input-config.z62-capturework=on
-global nikon-z72-input-config.z62-capturework-policy0=on
```

第二项要求第一项同时启用。这是 C 级外部 MAIN 策略，不能用来验证对物理源选择寄存器的修改。运行器负责组合既有参数，不能仅复制这两行就认为完整原厂环境已就绪。启用 CaptureWork 时阻止迁移／完整快照，外部 worker／数据所有权尚未实现完整恢复。

本地已验收 r89 EXE SHA256 为 `65c3eccad787d7ddef4bc8bfef603df115a88d29c61b64cb8a165a66d26b2777`；r91 为 `5270d7cfb7db60bbb2ef2f8102ce6c37de4b6c3dbf34a35ea84aed6d67675aa2`。它们是已有验收对象的身份，不要求另一工具链产物字节相同；新构建必须另做绑定与验证。

## 如何解读已有结果

| Evidence | Finding | 后续路径 |
|---|---|---|
| r89 原生合成 ARM 循环，6 帧 9,138,504 像素一致 | 有效配置下 DMA、事件、bank/ring 和部分生命周期可用 | 不能代替原厂消费检查 |
| r90 首轮 21 次缓存接受、0 DMA | 原厂非零共享源字未被原生夹具覆盖 | 保留失败，另建 r91 显式策略 |
| r91 原厂 C1.70 8.003360666 客体秒窗口 | 14 次缓存接受、13 次 DMA、13 组原厂 CPU W1C；保存 6 帧共 9,138,504 样本零差异 | ACK 证明中断处理执行，不证明高层采集完成；原厂窗口未额外验证 padding |
| 原厂窗口统计 0、预览 0、LCD 全黑 | 新来源还未交付给下游；grid 的 disabled 为当前实验配置状态 | 核对启用条件，再建立真实来源资格和线性视图 |
| 本地完整 Python 701 项、零失败／错误／跳过 | 当前完整研究环境回归通过 | 未重跑 RawPy/LibRaw、长期运行或完整相机验收 |

事件 CB 曾采样到 `0x04300000`；没有采样到完整 `0x05B00000` AND 条件，非原子采样不能证明间隙从未满足。不得靠补 ready、改原厂返回、扩大队列或增加旧 RAW 计数宣布贯通。下一步需要冻结 transfer 解码、每帧／每槽来源与所有权、统计及 ISP 数值输入和取消背压合同。

完整证据适用范围、原生／原厂命令和归档见 [r89 报告](../history/2026-11-04_实施-Z62原生采集后端与DMA交付r89-report.md)及 [r90/r91 报告](../history/2026-11-04_实施-Z62原厂MAIN交付与共享源策略r90-r91-report.md)。公开仓库只分发选定摘要及原件哈希，不分发固件、卡、完整 RAM／轨迹或 NKN 恢复包。

参考 nightglasses/z7ii-qemu 固定 `0e53ea5a6d4f3fc635d63c195a92e943370ac5e9` 的 CaptureWork 分工、共享字段与外部 MAIN 研究；本项目的 Z62 几何、配置和 CPU ACK 用目标固件独立交叉核对。保留既有 Z62/Z72/WonderLantern、QEMU 作者与许可证；不将其他机型代码视为 Z62 硬件规格。
