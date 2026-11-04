> **当前总览见 [README](../../README.md)：2026-11-04/r98 源码快照，r75 工作目录交互入口使用 r69 内核。以下保留早期版本的历史说明，不作为当前默认功能表。**
>
> **2026-10-29 历史更新：当时统一入口为 `start-z6ii-qemu.cmd`，支持原版及 C1.70 布局候选固件。**
> 当前为r9预览内核与r10b快门输入，操作范围见 [Z6II QEMU 使用说明](README-Z62-QEMU.md)。已验证合成RAW预览及半按返回，完整ISP、拍照保存及真机更新安全仍未完成或未验收。下文保留 v0.4.0 历史探针说明。
>
> **2026-10-26 更新：已在本机复现 Z6II、Z7II 原始固件 MENU 和方向键。**
> 这是独立参考环境，不是下述 v0.4.0 严格探针的功能升级。Z6II 使用明确标注的合成参数，非真实 NOR/校准数据。
> 操作与重启见 [原始菜单参考环境](README-MENU.md)；Z6II 入口 `start-z6ii-menu-reference.cmd`。

# Nikon Z6II QEMU Lab v0.4.0

基于 QEMU 10.2.4 的 Windows 原生 Z6II 1.70 固件启动/调试环境，机型 `nikon-z6ii`。

**尚不是可以操作原相机 MENU 的完整模拟器。** 不修改原始固件，不连接或刷写相机，不上传或打包尼康固件。CPU、CBAR、GIC、定时频率、零复位和同步完成反馈都是实验选择，不是已识别的硅片规格。

## 立即运行

需要 Python 3.12+；启动器只用标准库，不需要 MSYS2/WSL/Docker/Unicorn。

双击项目根目录 `start-qemu-v0.4.0.cmd`，或执行：

```bash
python tools/run_qemu.py --engine both
```

便携包：`dist/z6ii-qemu-v0.4.0-windows-x64.zip`，同目录有 `.zip.sha256`。解压后，将已提取的 `artifacts/z6ii-1.70` 目录拖到包内 `run.cmd`，或执行 `run.cmd "固件目录绝对路径" both`。包内日志写入 `logs/`。v0.2.0、v0.3.0 包和入口仍保留，旧入口固定使用旧包。

- `master` / `slave`：选择对应固件。
- `both`：两个独立 QEMU 进程，**尚未连接双芯片通信**。
- `--cores 2`：一个执行环境内的两个核，不是两颗 EXPEED。
- 默认只接受已验证的两份原始 payload，路径 `artifacts/z6ii-1.70/`。
- 项目日志默认写入 `analysis/qemu-v0.4.0/latest/`，再次运行会更新。
- 退出码 `2`：未建模硬件或运行时限；不是相机启动成功。`1`：配置/摘要/QEMU 错误。

## v0.4.0 的推进

本节记录 v0.4.0 当时的结果：参考固定版本 `JKWTCN/z72-qemu`（`f6b80ec650116a6b0117d31f9ea112b05bb7f52a`）的候选合同，再从本地两份 Z6II 原固件独立执行验证。当时尚未运行 Z7II；后续已使用用户提供的 Z7II 固件完成本机菜单复现，详见上方参考环境。

| 项目 | 已实现的实验行为 |
|---|---|
| 精确访问范围 | 346 个 32 位字：4 个早期配置字、两个配置通道各 171 字；空洞仍拒绝 |
| 完成反馈 | 40 对命令/状态；仅支持已观察的命令，阶段型命令接受 0–4；状态 W1C |
| 结果字 | `0x2003016C` / `0x2005016C` 只读；默认 0，可注入失败值 |
| 原始执行 | 每侧 428 次访问：368 写、48 状态读、6 结果读、6 早期读；四次调用返回 0 |
| 新边界 | PC `0x1002BDD8` 写 `0x20016020=0x40000000`，严格停止，不假设该硬件已实现 |
| 保留 | 原始 40,000 / 8,000 延时和 40,000,000 轮询参数，不改分支、不缩短等待 |

**完成时序、结果成功值、W1C、非法命令清除就绪以及零复位仍是明确标注的模型假设。** 固件访问/确认序列与这些假设兼容，不证明真实内存训练、时钟或供电效果。两份固件使用相同配置轨迹，不等于两颗 EXPEED 已通信。两个通道的布局相同，但部分参数不同。

记录完整成功轨迹：

```bash
python tools/run_qemu.py --engine both --trace-config
```

### 负对照与失败注入

```bash
# 关闭扩展模型，恢复 v0.3.0 的首个状态读取边界
python tools/run_qemu.py --engine both --no-platform-config
# 关闭全部配置模型，恢复首次 MMIO 写入边界
python tools/run_qemu.py --engine both --no-boot-config
# 只阻断通道 1 的一个命令，通道 2 仍可完成
python tools/run_qemu.py --engine master --blocked-control 0x20024100 --timeout 60
# 注入非零结果，执行原始错误处理路径
python tools/run_qemu.py --engine both --completion-result 1
# 禁用全部完成反馈，保留原始轮询超时（可能较久）
python tools/run_qemu.py --engine master --no-auto-complete --timeout 120
```

超时实验禁止同时使用 `--trace-config`，避免记录数千万次状态读取。启动日志会保存实际模型开关、阻断地址和结果值。原生机器属性：`platform-config=off`、`boot-config=off`、`auto-complete=off`、`blocked-control=0x20024100`、`completion-result=1`、`trace-config=on`。

## 从原始入口调试

```bash
python tools/run_qemu.py --engine master --paused --gdb-port 1234 --qmp-port 4444 --timeout 0
```

在支持 ARM 的 GDB 中：

```gdb
target remote 127.0.0.1:1234
x/4i 0x10020000
info registers
si
```

QMP 端口 `127.0.0.1:4444`，先发送 `qmp_capabilities`。双实例从侧端口加 1；启动器拒绝端口重叠。调试端口仅绑定回环地址。Ctrl+C 结束启动器和子进程。

## 复现证据、构建与测试

分析探针需要 `requirements.txt` 的 Capstone/Unicorn，启动便携程序不需要。

```bash
python tools/analyze_boot.py
python tools/analyze_platform.py
python tools/build_qemu.py --msys-root C:/msys64 --jobs 4
Z6II_QEMU_REQUIRED=1 python -m unittest discover -s tests -v
```

将 `C:/msys64` 替换为实际 MSYS2 UCRT64 根目录。依赖 GCC、Ninja、pkgconf、GLib、Pixman、zlib、dtc/libfdt、Python、packaging、MSYS make/diffutils。构建器不静默安装依赖。

QEMU 源码固定为 `https://download.qemu.org/qemu-10.2.4.tar.xz`，SHA-256：

```text
821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746
```

源码缓存位于 `.build/`；只新增板型、头文件和 Meson/Kconfig 注册，不修改 QEMU ARM 核心。Linux 构建入口为 `python tools/build_qemu.py --jobs 4`，未在 Linux 实测。

测试覆盖固件哈希/CRC、静态证据、GDB 原始单步和真实调用返回、QMP 双核/复位、精确字集、W1C/通道隔离、无效命令/访问、原生和独立 Unicorn 逐项轨迹、原始超时与错误路径。通过情况以实际输出为准。

## 未实现范围

- `0x20016020` 起的平台操作及真实内存控制器/时钟/供电效果。
- 完整 RAM/BSS、堆、外设、中断与控制 MCU、RTOS 调度。
- 双 EXPEED 远端窗口、通知线路和 DUALEG；不能把两份同基址固件放进一个地址空间。
- LCD、原始 MENU、按键和图像处理。
- 整机迁移和其他 Windows 机器兼容性；固件签名验证、重打包及安装恢复流程。

## Git 与来源

本地 Git 分支 `main`，中文提交；原始固件、提取产物、二进制、构建缓存均排除。第三方源码以固定提交子模块记录。没有自动建立远端或推送。

- [QEMU 10.2.4](https://download.qemu.org/qemu-10.2.4.tar.xz)，许可见源码和包内 `COPYING-QEMU`。
- [WonderLantern/z6-qemu](https://github.com/WonderLantern/z6-qemu)，`419a1f2a91a1f2d3a0209027c29606475f7fe26f`。
- [JKWTCN/z72-qemu](https://github.com/JKWTCN/z72-qemu)，`f6b80ec650116a6b0117d31f9ea112b05bb7f52a`，GPL-2.0；本轮未改参考工作树。
- 板型和头文件 GPL-2.0-or-later；包内保存源码快照、证据和依赖许可证。重建请用项目根目录构建器，包内 `source-overlay/build_qemu.py` 不是独立源码树。
- DLL 来自 MSYS2 UCRT64。本包为本机研究交付；公开分发前需核对 QEMU/各 DLL 完整对应源码提供义务。
