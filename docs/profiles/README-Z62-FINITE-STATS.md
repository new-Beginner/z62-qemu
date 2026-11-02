# Z6II QEMU r8有限统计开发版

r8增加了从实际RAW内存计算统计网格、按61槽完成有限采集的设备模型。**这仍不是完整相机模拟器，不能用来证明真机刷入安全。** 统一入口`start-z6ii-qemu.cmd`已升级到r8，旧r6保留可回退。

独立研究入口：

```powershell
python -X utf8 -B tools/run_z62_finite_stats.py --experimental-parameters --capcom-sync
```

浏览器地址为 <http://127.0.0.1:8678>。入口默认开启原生RAW、有限统计、输入命令应答和帧时钟两相输入。`--no-finite-stats`可关闭新增设备作对照；其它固件/候选包参数沿用r6/r7入口，候选健康状态仍为未知。

内核：`.build/z62-finite-stats-2026.10.29-r8/runtime/qemu-system-arm.exe`。

SHA256：`05fcd74d61700eebf4b8f911308b3c5ecabed29e673f581ba7ad97f51ff7bb91`。

## 实现范围

有限统计阶段读取最近一次成功RAW DMA的第一槽，生成30×12的LE-u16区域均值，行步长64字节。只接受已恢复的C1.70有限采集描述符，在全部61个槽真实写入后产生批次完成。原固件负责中断、切bank、停止和后续流程。

当前算法将静止RAW全帧划分为矩形区域求均值，属于公开定义的功能近似；尚未复现尼康测光、颜色校准及抗闪烁硬件算子。不能据此检查真实曝光和色彩精度，也不代表后端ISP、取景、拍照保存或完整更新流程已完成。

测光裁剪、权重和颜色系数寄存器尚未参与此均值计算；修改这些参数的固件仍不能在这里验证对应数值效果。

详细布局、门控、数据边界与证据见 [设备合同](../../qemu/z62-finite-stats/CONTRACT.md)。r6/r7二进制和原始固件均保留。

## 验证入口

```powershell
python -X utf8 -B tools/probe_z62_finite_stats.py --output analysis/z62-finite-r8/qtest-new.json
python -X utf8 -B tools/probe_z62_finite_firmware.py --output analysis/z62-finite-r8/native-new --duration 22
```

所有输出路径必须不存在。第一条是不执行固件的原生DMA/IRQ检查，第二条运行原固件、不给宿主完成IRQ；两类证据不能互相替代。

已完成的原生设备检查见 qtest结果（本地证据，未分发：`analysis/z62-finite-r8/qtest.json`）：数值读回、61槽计数、无提前完成、W1C、零步长第二bank、完整批次预检、配置变化、停止/重启、屏蔽、复位及只读计数均通过。旧RAW源回归见 回归结果（本地证据，未分发：`analysis/z62-finite-r8/legacy-raw-stream.json`）。原固件推进和画面以 运行记录（本地证据，未分发：`analysis/z62-finite-r8/native/report.json`）及截图为准，不能把扫描帧数或空错误列表当作取景通过。
