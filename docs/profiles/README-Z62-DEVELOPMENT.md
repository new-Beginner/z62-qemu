# Z6II / Z62 独立开发版 r4

**版本：2026.10.28-r4。不是完整相机模拟器，不是刷机包。** 原固件菜单可运行，但退出/重开仍可能出现原厂 Error；合成 RAW 不等于取景，虚拟卡持久化不等于拍照保存。

旧 v0.4、r1/r3 和 Z72 runtime 保留，不覆盖。此入口不访问物理相机、USB 或物理存储卡，不修改固件指令/返回值/错误列表。

## 启动

Windows、Python 3.12，在项目根目录执行；本机已经生成独立原生 QEMU runtime。需要用户自有的原始 Z6II C1.70 包。

```bat
start-z6ii-development-2026.10.28-r4.cmd
```

控制台为 `http://127.0.0.1:8672`，启动需等待数分钟。默认：`baseline`、RAW 关闭、无卡；指定虚拟卡时默认为快照。CMD 显式使用合成参数，不是真实 NOR/校准。

只在需要研究合成 DMA 时启用：

```bat
start-z6ii-development-2026.10.28-r4.cmd --functional-raw --capture-preset init-mode
```

`init-mode` 是已有实验完成源，**不是重复菜单循环修复**。RAW 独立于该预设；不会连接到 sensor IRQ92 来消除固件错误。

如有合法取得的参数目录，直接调用 Python（不要与 CMD 自带的实验参数并用）：

```bat
python -B tools\run_z62_development.py --parameters "D:\camera-lab\parameters" --port 8672
```

上例参数路径需替换为实际目录。构建身份或 EXE 哈希不符会拒绝启动；不要删除 manifest 来绕过检查。

## 创建并使用虚拟 SD

只接受普通 `.raw` / `.img` 文件，不接受物理盘或符号链接。创建不会覆盖已有文件。

```bat
python -B tools\z62_virtual_sd.py --create artifacts\z62-development-card.raw --size-mib 512
start-z6ii-development-2026.10.28-r4.cmd --sd-card artifacts\z62-development-card.raw
```

这是空白 MBR/FAT32 卡，含 BPB/FSInfo 备份、双 FAT 和卷标；不是相机格式化的卡。不放入固件更新文件。支持 512～32768 MiB 的二次幂尺寸；大卡复制和哈希会较慢，需要源卡、暂存卡和保存临时副本的磁盘空间。

### 明确保存改动

```bat
start-z6ii-development-2026.10.28-r4.cmd --sd-card artifacts\z62-development-card.raw --sd-mode persistent
```

- 默认 `snapshot`：QEMU 使用快照，退出不回写源镜像。
- `persistent`：QEMU 写本会话 ASCII 暂存副本；点击网页 **停止** 后，宿主确认全部自有 QEMU 正常退出，才校验并原子替换源镜像。
- 重启控制台内的模拟器可继续使用同一暂存卡；最终停止才回写。窗口被强制关闭、进程异常退出、源镜像被外部修改或大小改变，均不应当成正常保存。
- 正常退出后查看终端输出的会话目录 `session.json`：`clean_exit=true` 且 `sd_card.saved=true` 才算已保存。

### 异常恢复

源镜像保持不动，恢复副本在终端输出会话目录下的 `virtual-sd.raw`。先确认对应进程已经结束，再复制到**新的文件名**进行检查；不要直接覆盖源卡。异常中断可能留下 `原文件名.z62-lock`，其中记录 PID 和暂存路径；确认该会话结束后才可手工移除。这个锁是本工具的协作锁，不能防止不遵守锁的其他编辑器；不要并行编辑或替换源卡。

不自动承诺客体文件系统一致性：正常 QEMU 退出只能确保宿主保存流程，不代表固件已完成所有应用层写入。

## 本轮实现的设备能力

| 模块 | 实现 | 边界 |
|---|---|---|
| 原固件 UI/按键 | 继承 Z62 原始 LCD、控制器输入和 Z72 参考面板更新 | 不网页重画菜单；循环仍有错误 |
| 合成 RAW DMA | 显式 submit；1514×1006、stride 2272；四槽；两组描述符选择；独立 engine RAM | packed12 和 bank 位语义为实验假设，不是硬件定论 |
| DMA 防护 | 全部描述符预检、地址/重叠/可写 RAM 检查、失败计数、只读 QOM | 不猜地址、不回退到另一有效 bank、不生成虚假完成 |
| 重复 DMA/reset | 每次有效提交实际写入四槽，完成后独立脉冲；reset 清计数 | 不等于传感器启停状态机；VMState 已编码，未做 live migration 验收 |
| 虚拟 SD | SDHCI PIO 读写、快照、显式持久保存、FAT32 创建 | 未验收原固件拍照生成文件 |
| 开发观测 | 完整固件状态列表、RAW 计数、错误原因、来源 manifest | 非原子采样；未知不作健康；不判定真实取景 |

RAW 仅在写 `0x20068104=1` 且配置恰好满足支持合同后写入合法处理池。配置不匹配会拒绝，即使它会让实验“不出图”。独立 qtest 可验证设备，原固件是否真正提交并消费同一合同，必须另行验证。

`/status` 的 `functional_raw_status` 包含两 engine 的 `raw-accepted`、`raw-rejected`、`raw-bytes` 和 `raw-last-reason`。`firmware_health_known=false` 表示未知，不是正常；`live_view_verified` 始终为 false。旧通用诊断中的 `sensor_pixels_modeled=false` 指原传感器链，不能替代新 RAW DMA 计数。

## 构建与验证

独立 runtime：`.build/z62-functional-2026.10.28-r4/runtime/qemu-system-arm.exe`。固定 Z62 donor `4f4389944fc339d107f22f5f7ca3f90cc34b78de`；保留 Z72 参考更新来源；参考 Z6 的描述符有界模型，不搬用其地址或辅助启动补丁。

重新构建使用**未存在的新目录**，需要原生 Windows Python、MSYS2 UCRT64 和已校验 QEMU 10.2.4 缓存；默认从旧构建 manifest 读取本机工具链位置，也可显式 `--msys2-dir`：

```bat
python -B tools\build_z62_functional.py --work-dir .build\z62-functional-local-check
python -B tools\probe_z62_functional_raw.py --help
python -B tools\probe_z62_sd_persistence.py --qemu .build\z62-functional-2026.10.28-r4\runtime\qemu-system-arm.exe --output artifacts\sd-r4-check.json
python -B -m unittest discover -s tests -v
```

原固件循环验证（输出目录必须不存在；失败会返回非零，保留完整证据）：

```bat
python -B tools\probe_z62_menu_timing.py --qemu .build\z62-functional-2026.10.28-r4\runtime\qemu-system-arm.exe --development-host --functional-raw --capture-preset init-mode --menu-at 3 --cycles 3 --wall-limit 1400 --output artifacts\r4-cycle-check
```

通过条件是**完整空固件状态列表＋退出＋重开＋真实导航像素变化**，不是 `error=null` 或画面有变化。

设备构建/qtest 证据：RAW 报告（本地证据，未分发：`analysis/z62-functional-device/REPORT.md`）。动态错误证据：上层等待报告（本地证据，未分发：`analysis/z62-upper-waits/report.zh-CN.md`）。宿主/SD/原固件循环证据在 `analysis/z62-development-r4/`。

## 尚未实现/验收

1. 稳定重复 MENU 循环：第二轮上层 `mask=8` 等待的具体失败 caller 已定位；底层事务到通知的因果仍未完成，未硬补事件。
2. 原固件完整 RAW→ISP→LCD 消费链、持续实时取景、传感器流控和准确 packing。
3. 正常拍照、JPEG/NEF/视频编码与客体文件保存；卡扇区可持久化不代表这些功能成立。
4. 真实 NOR/校准、跨重启设置持久化、AF/镜头/测光及准确电气时序。
5. 整机迁移/快照恢复、长时间与多次冷启动稳定性。实验 RAW 的 VMState 定义不等于整机迁移通过。

这些是当前实现边界，不是断言永远无法实现。固件原件、旧运行环境及失败证据均保留，不提交/推送固件或卡镜像。
