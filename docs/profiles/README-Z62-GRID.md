# Z62 r48 命令组 0 软件 ISP

r48 将已有连续统计 RGB 数据转换为四份 60×40 packed12 输出，成功写回后才产生命令组 0 完成。原厂 C1.70 已自然执行完成回调和事件发布，5 次配对的 `81000000` 等待全部成功返回。

该设备仍是有限配置下的 C 级软件 ISP；传输与 IRQ 为 B 层，原厂代码为 A 层。没有还原尼康全部 11 个节点的数学，没有验收模式恢复、原厂拍照保存、完整镜头通信或 AF。

## 运行与验证

独立内核：`.build/z62-grid-2026.11.02-r48/runtime/qemu-system-arm.exe`。

SHA256：`9e6f7f8e4987d90fcd9c66fae243636f17b1ba3a9cd24db1a83daac2ad3b10f6`。

新开关默认关闭：`-global nikon-z72-boot-config.z62-grid-process=on`。原厂研究工具自行组合已有 RAW 边界、连续统计、预览结果与新设备开关；只加这一个开关不构成完整启动配置。

在工作区根目录运行，选择新的证据文件或目录：

```powershell
python -X utf8 -B -c "import sys;sys.path.insert(0,'tools');import run_z62_grid as h;print(h.verify_build()['binary_sha256'])"
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_grid.py --output analysis/z62-grid-r48/native-new.json
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/trace_z62_grid_delivery.py --output analysis/z62-grid-r48/delivery-new --card <USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw --group23 <USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin --duration 12
.build/tools/video-r26/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q
```

## 当前合同

| 项目 | 实现 |
|---|---|
| 命令组 | bank0 是编号 0 的命令组；bank1 是另一组，不是双 E6 的芯片编号 |
| 输入 | 已观察 RGB 六槽，三路 LE-u16，60×40、row128；四源槽当前为 5/0/1/2 |
| 运算 | `(R+G+B+1)/3` 的整数均值，再打包为 packed12；不是尼康矩阵/LUT 的等价还原 |
| 输出 | 四份独立 row96×40，共 15,360 字节；每行 6 字节 padding 清零，输入只读 |
| 来源 | 连续统计全部五路 DMA 成功后发内部槽通知；配置寄存器或 RAM 非零本身不能证明输入已供给 |
| 完成 | 全部数值及目标预检后实际写回，结果位 `2010001C/10` 与命令位 `20100020/4` 沿 IRQ102 交付 |
| 生命周期 | 逐位 W1C、屏蔽待定、背压、停止取消、重启需要新数据、复位、从引擎隔离 |
| 软件字段 | 回调/事件/软件 bookkeeping 不决定硬件成功；原生检查毒化这些字段并验证保留 |
| 快照 | 新状态及 timer 已登记 VMState46；整机与外部模型恢复未验收 |

## 实际结果与边界

- 原生 QEMU 检查通过，包含真实 6 RAW→6 统计 DMA→6 槽通知→4 packed12 输出，独立全样本对照及 6 类失败无输出/无完成。
- 原厂有界运行：12.048 客体秒、350 停顿；34 组/136 份输出、522,240 字节、拒绝 0；196 次来源通知。
- 首个完成按原厂 skip=1 的逻辑丢弃，后续 skip 自然为 0。33 次有效命令回调中有 32 次发布；32 对同线程、原栈记录确认计数各增 1。原厂同时消费计数，不能把 32 称作最终累计值。
- 5 次 `81000000` 等待均返回 1，输出包含 `01000000`；两次四输出快照的 19,200 个样本独立解码一致。当前输入为模型生成数据。
- 末次 IRQ 后尚有一组未消费，保留观察窗口边界；通用 `trace_complete=false`，本次按独占工具的有界观察完成判据验收。
- 530 项全量回归通过；新功能关闭时，旧预览和连续统计原生回归通过。

首次联动失败是测试漏启控制端；`native-1.json` 保留，只修测试配置，设备及二进制未改。完整结构化证据在 `analysis/z62-grid-r48/delivery-1/`；控制台摘录明确为 partial。

构建器 `tools/build_z62_grid.py --jobs 8` 只创建独立工作目录；已有构建无需重建。冻结父源与生成源均由 manifest 绑定。

完整结论见 [r48 阶段报告](../history/2026-11-02_实施-Z62命令组0软件ISP-r48-report.md)，剩余相机能力见 [覆盖表](../CAPABILITY-COVERAGE.md)。
