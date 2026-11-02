# Z62 r5 事务完成实验版

**2026.10.28-r5 是独立实验版，不是完整取景/拍照或无错循环版本。** 参考公开图的事务完成思路，增加真实 RAW DMA 成功后的设备完成桥；默认关闭。旧 r4、原固件、donor 和 8672 展示不变。

## 启动

Windows/Python 3.12，在项目根目录执行。默认 baseline、RAW off、完成桥 off、端口 8673：

```bat
start-z6ii-transaction-2026.10.28-r5.cmd
```

复现本轮显式实验（合成参数由 CMD 明确启用，非真实 NOR/校准）：

```bat
start-z6ii-transaction-2026.10.28-r5.cmd --functional-raw --raw-completion --capture-preset init-mode
```

地址 `http://127.0.0.1:8673`。启动需数分钟；网页“关闭模拟器”正常结束本实例。不要密集连按；当前可交互菜单不代表无错误，查看固件状态列表。

参数 `--raw-completion` 必须与 `--functional-raw` 同时指定。不能和旧 `laboratory-frame-completion` 同时开启，设备会拒绝双来源。`init-mode` 仍是已有实验预设，初始化 one-shot 未取消。

Python 直接入口为 `tools/run_z62_transaction.py`，支持原 r4 的显式参数目录、虚拟卡 snapshot/persistent、输入 trace 与禁用自动菜单。虚拟卡创建、保存与恢复流程沿用 [r4 说明](README-Z62-DEVELOPMENT.md)，把启动脚本换成本页 r5 入口；默认无卡，不访问物理设备。

## 新增了什么

成功写完四个合法 RAW 槽 → 同 engine `raw-dma-complete` → 检查实验开关、mode2 和 mask bit1 → 锁存 `0x20065508 bit1` → 原设备 IRQ92。

- 失败 DMA、仅写配置、未 arm、错误 mode 都不生成完成。
- status 已 pending 时合并，不制造额外边沿；W1C 后下一笔成功事务可重新完成。
- 无周期完成定时器、不强补软件 event8、不改固件指令/返回值/错误列表/应用索引。
- packed12、完成源关联仍是功能性假设，不是芯片时序或真实 packing 证明。
- `/status` 的 `transaction_bridge` 只读显示 source-events/completions/ignored/coalesced/last-reason。读取失败显示 unknown，不当成零；采样非原子。

## 本机实测结果

| 同一 r5 EXE、相同 RAW/init-mode | bridge off | bridge on |
|---|---|---|
| 实际 RAW 成功写入 | 3次，27,427,584字节 | 3次，27,427,584字节 |
| 事务完成桥锁存 | 0次，3次忽略 | 3次，无忽略/合并 |
| 第一轮退出/重开/导航 | 通过 | 通过 |
| 第二轮最终固件状态 | `0x35,0x3F` | `0x35` |
| 整体健康循环 | 失败 | 失败 |

开启组观察到36.965客体秒，未采到0x3F；关闭组到37.171秒，已出现0x3F。**只能说这一对照窗口内局部改善，不能声称永久消除0x3F或循环已修复。** 两组第二轮都因0x35停止，未执行第三轮；未验收多次冷启动和长稳。

最终完整回归 **207项通过、零跳过**；新EXE SDHCI快照/持久保存回归通过；CMD原固件菜单状态读取及正常退出通过。原始失败日志保留。原生qtest还覆盖默认关闭、错误描述符、mode/mask门控、真实IRQ边沿、合并/W1C、重复high、reset、主从隔离、只读属性与旧r4设备回归。

## 构建与复核

EXE：`.build/z62-transaction-2026.10.28-r5/runtime/qemu-system-arm.exe`。

SHA256：`451a5a2c38ef9fa4db34aa826aebb9312379d67023b4697aa3209ca7b31e6a6f`。

`tools/build_z62_transaction.py` 使用原生 MSYS2 UCRT64、已校验 QEMU10.2.4 缓存、固定 donor，依次应用 r1、未改动的 r4、r5 adapter。本版构建器限定独立 r5 工作目录，若目录已经存在则拒绝覆盖；当前已构建，无需重新执行。三份 manifest 分别记录参考、RAW 和事务层身份；运行入口核对源码身份及 EXE 哈希。

重新运行验证（输出路径必须不存在）：

```bat
python -B tools\probe_z62_transaction.py --qemu .build\z62-transaction-2026.10.28-r5\runtime\qemu-system-arm.exe --output artifacts\r5-device-check.json
python -B tools\probe_z62_transaction_cycle.py --functional-raw --raw-completion --capture-preset init-mode --cycles 3 --output artifacts\r5-cycle-check
python -B -m unittest discover -s tests -v
python -B analysis\z62-transaction-r5\summarize.py
```

qtest 输出采用独占原子发布，不覆盖已有证据；失败记录 `completed=false` 并返回错误。文件系统不支持硬链接时会明确失败，不回退为覆盖写。

详细图示核对、A/B证据与限制见 [总报告](../history/2026-10-28_实施-Z72图示核对与Z62事务完成r5-report.md)、[实验范围](../../analysis/z62-transaction-r5/scope.md)、设备报告（本地证据，未分发：`analysis/z62-transaction-device/REPORT.md`）。

## 仍未实现

- 上层0x35等待通知的完整生产链，以及稳定重复菜单/启停。
- RAW→ISP→LCD的自然消费和持续取景。
- 原固件拍照、NEF/JPEG/视频编码、照片保存和回放闭环。
- 真实NOR/校准、整机迁移、长期稳定性和实机刷写安全。

本版不加载修改固件，不取消原固件哈希检查，不接物理相机或PTP。它是设备模型推进实验，不是刷机包。
