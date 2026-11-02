# Z6II 候选固件离线测试

**已支持明确加载你自己的候选固件，但完整 Z6II 模拟仍在开发。** 推荐使用 [统一入口](README-Z62-QEMU.md)，同样支持本页的候选输入合同。下文保留的 `start-z6ii-firmware-test.cmd` 使用独立 r5 QEMU；候选宿主版本为 `2026.10.28-candidate1`。支持 C1.70 的固定成员布局，不自动支持其他版本。不能据此判断更新到真机是否安全。

## 启动一个固件

在本工作区用原包检查入口：

```bat
start-z6ii-firmware-test.cmd --firmware "Z6_2_0170 (1).bin"
```

用自己的修改包时，将 `--firmware` 后的路径替换为实际文件。浏览器打开 <http://127.0.0.1:8674>。首次启动需等待，自动 MENU 默认关闭，可手动按 MENU。结束使用时点击网页“关闭模拟器”。

CMD 明确使用合成参数，并非真实相机标定。若已有自己的参数目录，应直接使用 Python 入口和 `--parameters`，不能与 `--experimental-parameters` 同用。其他 RAW、完成桥、捕获预设和虚拟 SD 参数继承 [r5 使用说明](README-Z62-TRANSACTION.md)。默认均为 baseline、RAW off、完成桥 off、无卡。

## 接受哪些输入

| 输入 | 规则 | 实际执行范围 |
|---|---|---|
| `--firmware` 更新包 | Z6II C1.70 目录、名称、偏移、长度；5 个成员及包 CRC 全部通过 | master、slave、controller 三个成员 |
| `--members` 成员目录 | `master.bin`、`slave.bin`、`controller.bin`；包括原格式两字节 CRC 尾；固定 C1.70 大小 | 三个成员 |

成员大小依次为 38,750,138、8,832,194、524,290 字节。更新包中的 `_tpj01_v140.bin` 和 `vr1850_010100.bi` 会校验并记录哈希，但其处理器尚未模拟，**不会执行它们的修改**。目录输入不含更新包校验结论。

新入口不再要求候选与原固件 SHA256 相同，但每次启动都要求暂存成员与所选候选快照的大小和 SHA256 相同。CRC 不是签名验证；名字与大小匹配也不能证明候选的内部布局或功能正确。不会自动修正 CRC，也不重新打包固件。

只检查输入、打印哈希和修改字节数，不启动 QEMU：

```bat
python -B tools\run_z62_firmware.py --firmware "Z6_2_0170 (1).bin" --inspect-only
```

已有完整成员目录时，例如本项目原版提取目录：

```bat
start-z6ii-firmware-test.cmd --members artifacts\z62-reference-1.70
```

输入只读，启动时在独立 ASCII 临时目录保存所选快照；后续修改源文件不会改变当前会话。若想测试新的修改，关闭后重新启动。终端显示会话目录，其中 `candidate.json` 和 `session.json` 记录候选哈希、基线哈希、变化字节范围、QEMU 身份、实验参数和退出状态。

## 如何读测试结果

- 候选模式始终显示“固件状态未知”。原版诊断使用固定 RAM 地址，不能未经核实就用于判断修改版健康；其他菜单索引/时间等读数也标记为未验证的原版布局观测。
- 若候选尚未初始化相应内存，保留 `candidate_observation_error`。QEMU 进程运行不等于相机固件工作正常。
- 原厂菜单、真实修改指令执行、RAW DMA、虚拟卡读写是不同层级的证据。完整取景、拍照编码、客体存卡、真实 NOR/标定和固件更新流程尚未完成。
- 本入口仅连接本机 QEMU，不接物理相机、USB/PTP 或物理存储卡。虚拟卡仍默认快照。

## 重现验证

```bat
python -B -m unittest discover -s tests -p test_z62_candidate.py -v
python -B tools\probe_z62_candidate.py --sentinel-self-test --output artifacts\candidate-sentinel-check
```

输出目录必须不存在。sentinel 检查仅在临时 master 副本中放入 `mov r0,#0x62; b .`，重算该成员 CRC 后启动 QEMU，读取 `r0` 和 PC；不修改原文件、不生成更新包。它证明修改后的指令确实执行，不是相机功能验证。

对实际候选作有界启动观测：

```bat
python -B tools\probe_z62_candidate.py --firmware "Z6_2_0170 (1).bin" --wall-seconds 30 --output artifacts\candidate-boot-check
```

`probe_completed=true` 只表示所选入口字节加载、QMP 运行观测、证据采集及正常退出完成。报告的 `firmware_health_verified` 和 `flash_safety_verified` 仍为 false。

整体开发和验收条件见 工作计划（本地证据，未分发：`GOAL-Z62-QEMU.md`）。
