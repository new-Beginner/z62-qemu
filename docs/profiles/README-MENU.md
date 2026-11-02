# Z6II / Z7II 原始菜单参考环境

**本机已验证两机型原始 C1.70 固件的 MENU 显示及向下导航。不是完整相机模拟器，不是 v0.4.0 严格启动探针的替换版。**

Z6II 使用显式合成参数，Z7II 使用捐赠项目的实验参数；均非恢复的工厂校准/NOR。未连接相机、未刷机、未验证实际取景/拍照/录像/设置持久化。不能将此模型用于推断刷机安全性。

## 独立开发版 r4

新增 `start-z6ii-development-2026.10.28-r4.cmd`（本机端口 8672），使用独立新编译的设备：可选有界合成 RAW DMA、虚拟 SD 快照/持久化、原固件状态与 DMA 只读观测。旧入口不变。**仍不是完整取景/拍照或无错菜单循环版本。** 使用与恢复说明见 [r4 开发版](README-Z62-DEVELOPMENT.md)。

## 现在操作

以下为各入口默认地址；需启动控制台后访问，不表示当前进程正在运行。

| 机型 | 浏览器地址 | 已验证画面 |
|---|---|---|
| Z6II（Z62） | http://127.0.0.1:8662 | 1024×682 原始 PLAYBACK MENU；方向键改变高亮 |
| Z7II（Z72） | http://127.0.0.1:8666 | 720×480 原始 PLAYBACK MENU；方向键改变高亮 |

页面按钮或键盘操作：`M` 打开菜单，方向键导航，`Enter` 确认，`X` 退出，`Esc` 释放全部按键。灰色项目可能依赖未实现硬件；没有逐项验证所有菜单。

输入通过原控制器引脚与客体去抖处理，画面由 QEMU screendump 输出。网页只是显示和输入终端，没有重画相机菜单，也没有强写应用索引。

**启动速度较慢。** 本机首次 Z6II 观察在墙上时间 370 秒、客体时间 28 秒时进入菜单；按键可能需要几秒生效。等待客体推进，不要密集连按或强制改状态。Z72 若自动 MENU 没有打开，待输入就绪后正常按一次 MENU。

## 关闭后重新启动

需要本机 Python 3.12+、已经构建的 `.build/z62-reference/runtime` 或 `.build/z72-reference/runtime`，以及各自原始升级包。运行不需要 WSL、Docker 或 MSYS2。

1. 先用页面的“关闭模拟器”关闭同端口旧实例；仅关闭浏览器页不会停止进程。
2. 双击根目录 `start-z6ii-menu-reference.cmd` 或 `start-z72-menu-reference.cmd`。
3. 打开对应地址，等待原固件启动。

等价命令（项目根目录）：

```bash
python tools/prepare_reference_firmware.py z62
python tools/run_reference_console.py z62 --experimental-parameters --port 8662

# Z7II 请单独在另一终端执行
python tools/prepare_reference_firmware.py z72
python tools/run_reference_console.py z72 --port 8666
```

提取器验证原始包及完整成员哈希、所有 CRC；成员保留尾部两字节 CRC，不能替换成旧探针的 payload-only 文件。已有内容不同时拒绝覆盖。固件签名并未验证。

控制台将固定提交的受跟踪源码和完整成员复制到 ASCII 临时目录，保存 `session.json`、`effective-command-0.json` 及日志；不执行捐赠工作树中的未跟踪脚本。临时目录仅供本地运行，含固件，不能提交或发布。设置 `PI_SCRATCH_DIR` 可指定 ASCII 临时根目录；必须没有逗号。

有自行合法取得的参数组时可使用 `--parameters 参数目录` **替代** `--experimental-parameters`，但本次未测试真实参数组，不建议为本任务拆机提取。

## 来源与构建

| 来源 | 固定提交 | 用途 |
|---|---|---|
| [JKWTCN/z72-qemu](https://github.com/JKWTCN/z72-qemu) | `f6b80ec650116a6b0117d31f9ea112b05bb7f52a` | 双执行环境、控制器、GPU、Z72 原始菜单 |
| [xiaoqingfeng0526/nikon-z62-qemu](https://github.com/xiaoqingfeng0526/nikon-z62-qemu) | `4f4389944fc339d107f22f5f7ca3f90cc34b78de` | Z6II C1.70 的映射、LCD、配置与控制台适配 |
| QEMU | 10.2.4 | Windows 原生 TCG 与 pixman |

重新构建请使用全新目录，避免覆盖正在使用的程序：

```bash
python -B tools/build_reference_qemu.py z62 --msys2-dir "$PI_SCRATCH_DIR/toolchain/msys64" --work-dir .build/z62-reference-clean --jobs 8
```

Z72 替换 profile 和新目录名；cmd 中请将工具链参数换为实际绝对路径。要求已缓存并校验的 QEMU 归档和已安装 UCRT64；脚本不自动安装工具链。新的运行目录可通过控制台 `--qemu` 指定。脚本故意拒绝重用成功或失败的非空目录。此次固化入口通过 13 项无编译测试，**未再次完整重编译**；现有两个 EXE 的实际构建证据另行保留。

两个参考 EXE 已编译并在清洁 PATH 下检查依赖；各自运行目录和旧版本保留。构建使用隔离 MSYS2/UCRT64，运行本身不依赖它。

本次实际构建先生成 Z72，再复用其**生成源码/对象树**增量转换为 Z62；Z72 的已完成运行目录保持不变。`.build/z72-reference/source` 和 `build` 现已是 Z62，不可误认为纯 Z72 源码。转换标记与来源保存在构建证据中。

唯一额外 C 兼容修正：`frame_count` 是 `uint32_t`，其只读 QOM 注册由 `object_property_add_uint64_ptr` 改为 `object_property_add_uint32_ptr`。没有改计数器逻辑、客体指令、CPU 核心或返回值。宿主启动适配仅 ASCII 路径、斜杠规范化和 Windows `NUL` 日志设备。

## 验证与边界

- Z72 实测方向键：`Delete` → `Playback folder`，61,804 像素变化。
- Z6II 实测方向键：相同菜单项变化，124,535 像素变化；原始应用索引 1、LCD 开启。
- Z6II 未启用参考项目的主屏实验：`main_screen_experiment=false`、`experimental_boundaries=0`、无 SD 卡。
- 合成组 17/18/32 大部分为零；少数候选配置沿用公开 Z72 fixture，Z6II 资源版本字段偏移 `0xCE014` 已由本地原始函数核对。不是原始 NOR、序列号或传感器校准恢复。
- 网络检索找到的同机型 R3 项目声称更多功能，但本次只对本机实际显示和一次向下导航作验收。
- 暂未发布新的便携包；若再分发 QEMU，需完成对应源码、许可证及依赖清单审查，不附带尼康固件或参数数据。

证据：`analysis/reference-qemu/`；本地画面：`artifacts/reference-qemu/{z62,z72}/`（不入 Git）。详细过程见 [复现报告](../history/2026-10-26_逆向-Z72与Z6II原始菜单本地复现-report.md)。

回归命令：

```bash
Z6II_QEMU_REQUIRED=1 python -m unittest discover -s tests -v
```

Windows cmd 请先执行 `set Z6II_QEMU_REQUIRED=1`，再执行 Python 命令。旧版无界面严格探针仍见 [README-QEMU.md](README-QEMU.md)。

最终完整回归：86 项通过，零跳过，60.872 秒；日志 `analysis/reference-qemu/tests.log`。两个 CMD 入口也已实际通过原包识别及 `--help` 检查。

## 2026.10.27-r1：Z72 新提交的 Z62 适配

保留上述旧环境，新增独立原生构建 `.build/z62-reference-2026.10.27-r1/runtime`。启动 `start-z6ii-reference-2026.10.27-r1.cmd`；仍需原包、Python、显式合成参数，端口默认 8662，先关闭同端口旧实例。

本轮只移植 Z72 `4a7bed36b6e747f58d5ab25f31b06a31fa7c6ec2` 中的肩屏 **I²C 寄存器协议**、总线地址只读观测和输入 MMIO 环形追踪；没有物理肩屏段码/图标仿真。两个固定子模块 HEAD 不变，由 `tools/reference_updates.py` 在新生成树/临时控制台副本适配。`/status` 返回肩屏寄存器、计数和两引擎输入日志，不读取未经验证的 Z72 控制器 RAM 地址。

输入追踪默认设备属性关闭，新 CMD 显式打开。追踪只观察 `0x20060000..0x20070000`，保存最近 256 条；修正上游短环起始位置，计数改为 64 位并在复位清零。新构建 VMState 为 38，不能加载旧快照。

`--sampling-source` 是**额外显式实验**，打开现有 `sensor-sample` 与 `sample-counter`，不提供传感器像素。Z72 上游证明它能消除一次退出后的致命对话框，但仍不能重开菜单；Z62 不能据此宣称修复。新版默认不打开采样源，也不启用 `main_screen_experiment` 或外部捕获完成注入。

```bash
# 全新目录构建；TOOLCHAIN 指向已安装的 MSYS2/UCRT64
python -B tools/build_reference_qemu.py z62 --z62-updates --msys2-dir "$TOOLCHAIN" --work-dir .build/z62-reference-2026.10.27-r1 --jobs 12
# 运行（与旧入口隔离；二进制必须匹配其构建清单与适配器哈希）
python -B tools/run_reference_console.py z62 --z62-updates --input-trace --experimental-parameters --qemu .build/z62-reference-2026.10.27-r1/runtime/qemu-system-arm.exe
# 无固件设备验证；输出路径应为本地分析文件
python -B tools/probe_reference_devices.py --qemu .build/z62-reference-2026.10.27-r1/runtime/qemu-system-arm.exe --output analysis/z72-update-2026-10-27/input-trace-test.json
```

首次构建前需 `git -C third_party/z72-qemu fetch origin main`，以取得固定提交对象；构建只按固定 SHA 读取两份上游 C 源码并校验内容哈希，不执行当前远端分支。其余仍遵守原来的离线归档和新工作目录保护规则。此次已完成全新编译及设备测试；未制作新的分发包。

本机 A/B 实测（同一新版 EXE、原始 C1.70、合成参数、无主屏/边界注入）：采样源开/关均可打开并导航原厂菜单，但退出后均显示致命 Error 对话框，尝试重开仍在拍摄应用。**只开两个采样开关不足以修复 Z62。** 肩屏寄存器设备通过合成 I²C 契约测试，原厂冷启动未自然访问它。完整回归 93 项通过；详见 `analysis/z72-update-2026-10-27/`，截图和原始逐阶段数据在忽略目录 `artifacts/z62-reference-2026.10.27-r1/`。

## 2026.10.27-r2：上游对比与 SD 镜像入口

远端 `xiaoqingfeng0526/nikon-z62-qemu` 默认分支 `z62-r3` 仍为 `4f43899`，与本地固定版本一致。本地参考构建已带入上游全部30个C/头文件，不是只移植了菜单。旧v0.4严格探针与参考构建是两套环境，不能混为一谈。

新增 `start-z6ii-reference-2026.10.27-r2.cmd`，**宿主入口r2复用设备构建r1**，不重编译、不改变旧二进制/构建清单。`python tools/run_reference_console.py --version` 返回宿主版本；`session.json` 记录 `host_version`、卡路径/大小及快照边界。控制台设备 `package_version` 仍为r1。

```bash
python tools/run_reference_console.py z62 --z62-updates --input-trace --experimental-parameters --qemu .build/z62-reference-2026.10.27-r1/runtime/qemu-system-arm.exe --sd-card C:/images/card.img
```

`--sd-card` 是可选的**普通raw镜像文件**，不接受物理磁盘设备；目前要求ASCII且无逗号路径，大小为正的512字节倍数。此校验不保证容量符合SD规格或文件系统可挂载。默认不挂卡；Z72入口拒绝此参数。上游将卡接到从侧SD总线，使用 `format=raw,snapshot=on`，客体写入临时覆盖层，退出/重启不保留写入到原镜像。本入口不创建、不格式化、不改写用户镜像。

本机实际验证了64MiB空白测试镜像接入、QEMU运行、有效快照参数、正常关闭与原镜像哈希不变；**未验收FAT32挂载、写入照片或持久化**。上游已有4GiB SDHC/FAT32挂载证据，但不等于本轮已复现该结果。

完整回归101项通过、零跳过；新CMD的`--help`也已运行。没有新增分发安装包，不附带固件。原有Error、菜单重开失败和像素/DMA/ISP缺口仍在；主屏实验及边界注入仍不启用。对比与验证见 `analysis/z62-upstream-comparison/` 和 [对比报告](../history/2026-10-27_对比-Z62上游与本地推进-report.md)。

## 2026.10.28-r3：受控完成源与严格生命周期验收

**仍未修复稳定菜单循环，未实现取景/拍照。** r3 是宿主启动配置版本，继续复用 r1 QEMU 二进制；旧入口、固件和固定源代码均保留。默认 `baseline` 不启用额外完成源。

在 Windows CMD 中按需启动（两条命令择一，不要同时运行）：

```bat
start-z6ii-reference-2026.10.28-r3.cmd
rem 显式实验：额外启用现有 init/mode 完成源，非真实传感器
start-z6ii-reference-2026.10.28-r3.cmd --capture-preset init-mode
```

`init-mode` 仅对现有初始化/模式握手作功能性假设，不生成 RAW 像素，也不提供 DMA/ISP。五组实验复核结果：延迟首次 MENU 的单轮可以重开并导航；三循环组第一轮可交互，第二轮已有 `0x35/0x3F`，第三轮显示原固件 Error、无法重开。单轮改善不能作为稳定修复。退出画面可能黑屏或残留旧帧，不能据此验收主屏/取景。

探针 `tools/probe_z62_menu_timing.py` 0.2.1 要求全部运行样本的状态计数、类型和长度一致且列表为空；重开导航还要求 MENU 索引、LCD 开启、输入队列空及实际像素变化。未知状态也拒绝健康验收，但不把每个状态都命名为致命错误。历史较弱结果不改写，使用 `python -B analysis/z62-z6-transfer/summarize.py --check` 校验派生复核。

本轮全量回归 **156 项通过，零跳过**；五组实验57个文件校验通过，原包/成员哈希和CRC通过，数字签名未验证。详见 `analysis/z62-z6-transfer/` 及 [本轮报告](../history/2026-10-28_实施-Z62参考Z6推进与循环复核-report.md)。本轮未访问相机、未发送PTP、未重编译设备、未提交或推送代码。
