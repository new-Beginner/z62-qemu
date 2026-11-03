# nightglasses Z7II QEMU 本地构建与 Z6II 参考报告

日期：2026-11-02。分析版本：`0e53ea5a6d4f3fc635d63c195a92e943370ac5e9`。本报告采用普通技术文档结构，`flavor=null`。范围见 [scope](../../analysis/nightglasses-z7ii-0e53ea5/scope.md)。

## 1. 结论与阅读顺序

正确参考仓库 [nightglasses/z7ii-qemu](https://github.com/nightglasses/z7ii-qemu) 已拉取到本地，固定版本也与本轮重新查询的远端 HEAD 一致。它提供可实际执行的 QEMU ARM/RX 机型、独立 GNU NDS32/TPJ 运行器，以及软件成像、虚拟镜头和大量原生边界测试，适合为 Z62 后续开发提供参考。它仍是有明确假设范围的诊断模型，不能用来保证修改固件刷入相机后不会变砖。

TPJ/NDS32 与 ARM/RX 均已完成本机构建；Nikon 的 57 个原生测试程序、903 个 TAP 子测试全部通过，NDS 三类检查也通过。可直接参考的是有限软件成像、数据/完成生命周期、虚拟镜头与焦点/曝光输入，以及原生验证方法。这里没有把上游原厂运行记录计作本机复现。

先看第 4 节了解图片八项能力的实现层级；后续开发优先阅读 源码参考映射（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/reference-map.md`）。该映射列出代码入口、适配条件和针对 Z62 r49 模式切换缺口的工作顺序。

## 2. 仓库、版本和输入身份

| 项目 | 本轮固定值 |
|---|---|
| 正确仓库 | `https://github.com/nightglasses/z7ii-qemu` |
| 本地完整参考目录 | `<WORKSPACE>/third_party/nightglasses-z7ii-qemu` |
| WSL ARM/RX 独立检出 | `/root/z7ii-0e53ea5/buildsrc`，同一父提交及同一 QEMU gitlink |
| 父仓库提交 | `0e53ea5a6d4f3fc635d63c195a92e943370ac5e9`，detached HEAD |
| 标题 | `Merge pull request #2 from nightglasses/codex/sla-research-image` |
| 提交时间 | 2026-11-01 23:22:27 -0800，即北京时间 2026-11-02 15:22:27 |
| 作者 | Auturora；相关原始研究引用指向 `mashiro01/nightglass` |
| QEMU 子模块 | `qemu/qemu`，`4fc49f46dc95d4a27de2509e7fceb2931e91faeb`，上游标记 v11.1.2 |
| Andes GNU 子模块 | `andestech/gdb`，`4327fa948f903c0705e0d87eed4cb182e24a6b6c` |
| 构建输出根目录 | `D:/z7work/0e53ea5`，WSL 对应 `/mnt/d/z7work/0e53ea5` |
| 原厂固件运行输入 | 本轮不新增原厂 Z7II 执行；原生测试使用上游自建合成输入 |

这个仓库与先前检查的 `JKWTCN/z72-qemu` 是两个不同项目。既有 `2026-11-02_分析-Z72图片能力与上游源码核对-report.md` 中针对另一仓库的判断保留历史价值，但不能据此否定本仓库已有实现，也不能把两者提交号混作同一条更新历史。

## 3. 本机构建与核验

### 3.1 实际环境

Windows x64，WSL `Ubuntu-24.04`，本轮 WSL 默认用户为 root，Linux x86_64，GCC 13.3.0，Python 3.12.3，CMake 3.28.3，GLib 2.80.0，pixman 0.42.2，Cairo 1.18.0，libfdt 1.7.0。补齐了 Meson/Ninja、Cairo 开发包、Python 构建依赖，以及 NDS32 所需 Autoconf 2.71、Automake、Bison、Flex、Texinfo、GMP/MPFR/MPC 开发依赖。QEMU 的官方 mkvenv 使用其随源码提供的 Meson 1.11.1、pycotap 1.3.1 等 wheel；不是把系统 Meson 1.3.2 当作满足 QEMU 最低版本。

构建产物为 **Linux ELF 程序，通过 WSL 运行**。Cairo 1.18.0 是本机版本；上游文档提到的 macOS/Cairo 1.18.6 验收不是本机结果。Darwin Metal 源文件只在相应宿主编译，本轮 Linux 构建不证明 Metal 后端可用。

### 3.2 拉取和环境问题

1. Windows Git 完成父仓库克隆、固定提交和主依赖取得。
2. 首次递归子模块更新因深层 edk2/OpenSSL 测试依赖路径过长而退出 1。
3. 单次 `-c core.longpaths=true` 修复部分路径，但更深层仍报 `$GIT_DIR too big`，该次也退出 1。
4. 改用 WSL Git 对同一 checkout 执行递归更新，退出 0。初次失败留下的 pyca 测试文件未完整写出，再由 Git 从该新取得子模块的 HEAD 补齐；没有语义修改上游源文件。
5. 第一次 QEMU prepare 仍退出 1，耗时 595.87 宿主秒；原始失败记录（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/qemu-prepare-first-failure.txt`） 保留 CMake 的 tracked-changes 拒绝。诊断发现 subhook、openbios、qboot、qemu-palcode、u-boot-sam460ex、vbootrom 这 6 个新拉取子模块的索引未完成，原始文件呈已暂存删除。逐一核对固定 gitlink 后，用 Git 从各自 HEAD 恢复索引和工作树，退出 0；没有放宽检查或改写设备实现。
6. 第二次 ARM/RX 尝试把 CONFIG_DIR 放入 WSL，但源目录仍在 Windows 挂载盘；依赖检查通过后，遍历约 113003 个文件仍很慢。在 581.69 宿主秒时终止本次自有 prepare 进程，退出 1，内部为 SIGTERM/143；这是主动中止的环境开销，不是编译通过，也不据此声称源代码有错误。
7. WSL 独立检出的准备过程还遇到两个问题：shallow QEMU 不能用作 `--reference`，而直接 GitHub 下载超时。一次人工离线补齐漏做 Git 根目录复核，因失败 clone 的元数据已清理，Git 回溯到父目录，使新建 `/root/z7ii-0e53ea5/src` 副本的父 HEAD 误切为 QEMU 提交；随后的 make 退出 1，未产生有效 Nikon 构建。该副本废弃，完整工作区参考源码未改变。
8. 最终使用新的 `/root/z7ii-0e53ea5/buildsrc`：父仓库从工作区固定副本 clone，QEMU 通过 Git 标准 `file://` 子模块传输从已取得的官方 checkout 离线获取。逐级 `rev-parse --show-toplevel HEAD` 确认父提交为 `0e53ea5…`、QEMU 为 `4fc49f4…`，不允许父目录回溯。完整递归源码保留在工作区；Linux 构建检出仅初始化本次需要的 QEMU gitlink。仍走上游 Makefile/CMake/官方 QEMU 流程，clean 检查保持有效。最终 CONFIG_DIR 为 `/root/z7ii-0e53ea5/native`，BUILD_DIR 仍在 D 盘；NDS 构建不变。

### 3.3 实测结果

| 操作 | 本机结果 | 证据范围 |
|---|---|---|
| `ls-remote origin HEAD` | 退出 0，与固定父提交相同 | 本轮远端核对；不是永久“最新”保证 |
| WSL 递归依赖更新 | 退出 0 | 在 Windows 两次路径失败后完成 |
| `make -j8 nds` | 退出 0，642.44 宿主秒 | 构建出 GNU `run`、`tpj` 和 `libsim.a`；不是原厂 TPJ 完整启动 |
| NDS 系统 / TPJ / budget 原生检查 | 全部通过，组合命令退出 0，335.36 宿主秒 | 5 组系统断言、16 组 TPJ 断言和 budget 检查；包括预期错误拒绝，详见 输出（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/nds-checks.txt`） |
| QEMU ARM/RX 构建 | 退出 0，1244.39 宿主秒，完成 3417 个 Ninja 步骤 | 配置日志（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/qemu-configure.txt`） 与 完成记录（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/qemu-build-end.txt`） |
| ARM/RX 版本及机型 smoke | 两者均为 QEMU 11.1.2，命令退出 0 | ARM：`nikonex`、`nikonsla`、`z7ii-mas-diagnostic`；RX：`nikonvr` |
| Nikon qtest / unit | **57/57 通过，903 个 TAP 子测试，0 失败、0 跳过**；命令退出 0，553.98 宿主秒 | CMOS 综合批次 153 个子测试，539.44 秒；虚拟镜头 unit 24 个子测试。批次输出（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/qemu-checks.txt`） |
| 收尾源码与基线核对 | 构建用父仓库和 QEMU 的 tracked 状态均干净；远端 HEAD 仍为 `0e53ea5…` | 原有 Z62 r48 EXE 的 SHA256 仍为 `9e6f7f8e…3b10f6`；完整值见产物清单 |
| 原厂 Z7II GUI / 媒体 / 模式运行 | 本轮未执行 | 第 4、6 节相应结果来自上游固定版本的记录 |
| 实体相机 | 本轮未连接 | 无刷写或不变砖结论 |

NDS/GNU 构建存在旧代码警告，包括 Autoconf 过时宏、readline 的 `wcwidth` 声明/格式警告，以及 `sim/common/hw-base.c` 返回局部数组地址的编译器警告。本轮保留官方源文件，未把“退出 0”写成“零警告”或无缺陷证明。

ARM/RX 构建也有警告，已观察到 `gate.c` 的局部 `index` 遮蔽，以及部分原生测试 argv 初始化丢弃 const 的警告；它们不是本轮源码修改。固定版本的默认配置本来包含 `--disable-werror`。本报告分别记录构建结果、测试结果和警告，不把警告等同于已验证的运行缺陷，也不声称代码零警告。

### 3.4 复现命令

以下在 Windows PowerShell 执行。目录变量只是命令参数，不创建自制构建脚本；编译、链接与测试由上游原生入口完成。WSL 的 `buildsrc` 已存在时，跳过这段一次性的准备命令，直接执行后一段 make。

```powershell
wsl -d Ubuntu-24.04 -- git clone --no-checkout --shared '/mnt/d/32057/Files_of_Desktop/Academic/AI/固件Z6II/third_party/nightglasses-z7ii-qemu' /root/z7ii-0e53ea5/buildsrc
wsl -d Ubuntu-24.04 -- git -C /root/z7ii-0e53ea5/buildsrc checkout --detach 0e53ea5a6d4f3fc635d63c195a92e943370ac5e9
wsl -d Ubuntu-24.04 -- git -C /root/z7ii-0e53ea5/buildsrc -c protocol.file.allow=always -c 'submodule.qemu.url=file:///mnt/d/32057/Files_of_Desktop/Academic/AI/固件Z6II/third_party/nightglasses-z7ii-qemu/qemu' submodule update --init --depth 1 -- qemu
wsl -d Ubuntu-24.04 -- git -C /root/z7ii-0e53ea5/buildsrc rev-parse --show-toplevel HEAD
wsl -d Ubuntu-24.04 -- git -C /root/z7ii-0e53ea5/buildsrc/qemu rev-parse --show-toplevel HEAD
```

```powershell
$Z7Repo = '<WORKSPACE>/third_party/nightglasses-z7ii-qemu'
wsl -d Ubuntu-24.04 --cd $Z7Repo -- git -c http.version=HTTP/1.1 submodule update --init --recursive --depth 1
wsl -d Ubuntu-24.04 --cd /root/z7ii-0e53ea5/buildsrc -- make -j8 BUILD_DIR=/mnt/d/z7work/0e53ea5/build CONFIG_DIR=/root/z7ii-0e53ea5/native
wsl -d Ubuntu-24.04 --cd $Z7Repo -- make -j8 nds NDS_BUILD_DIR=/mnt/d/z7work/0e53ea5/ndsbuild NDS_CONFIG_DIR=/mnt/d/z7work/0e53ea5/ndscfg
wsl -d Ubuntu-24.04 --cd $Z7Repo -- make ndscheck tpjcheck budgetcheck NDS_BUILD_DIR=/mnt/d/z7work/0e53ea5/ndsbuild NDS_CONFIG_DIR=/mnt/d/z7work/0e53ea5/ndscfg
wsl -d Ubuntu-24.04 -- make -C /mnt/d/z7work/0e53ea5/build -j8 check-nikon MTESTARGS=--num-processes=2
wsl -d Ubuntu-24.04 -- /mnt/d/z7work/0e53ea5/build/qemu-system-arm --version
wsl -d Ubuntu-24.04 -- /mnt/d/z7work/0e53ea5/build/qemu-system-rx --version
wsl -d Ubuntu-24.04 -- /mnt/d/z7work/0e53ea5/build/qemu-system-arm -machine help
wsl -d Ubuntu-24.04 -- /mnt/d/z7work/0e53ea5/build/qemu-system-rx -machine help
```

QEMU 默认配置来自根 Makefile：`--target-list=arm-softmmu,rx-softmmu --enable-tcg --disable-docs --disable-tools --disable-user --disable-guest-agent --disable-werror`。其中 Nikon 自有工具仍通过项目 Meson 入口链接，不因上游 `--disable-tools` 被一并禁用。

测试调用的是根 Makefile 本身使用的正式 `check-nikon` 目标。注意本轮生成命令为 `meson test --num-processes=2 --no-rebuild -t 1 --num-processes 8 --print-errorlogs --suite nikon`，后置参数实际选择 8 并发；不能把本轮描述为两并发测量。此处也不作物理相机性能比较。

### 3.5 本地产物

| 程序 | 路径 | 实际身份 |
|---|---|---|
| QEMU ARM | qemu-system-arm（本地证据，未分发：`D:/z7work/0e53ea5/build/qemu-system-arm`） | Linux x86-64 ELF 宿主程序，执行 ARM 客体 |
| QEMU RX | qemu-system-rx（本地证据，未分发：`D:/z7work/0e53ea5/build/qemu-system-rx`） | Linux x86-64 ELF 宿主程序，执行 RX 客体 |
| TPJ | tpj（本地证据，未分发：`D:/z7work/0e53ea5/ndsbuild/sim/nds32/tpj`） | Linux x86-64 ELF 宿主运行器，内部使用 GNU NDS32 sim |
| GNU 通用 runner | run（本地证据，未分发：`D:/z7work/0e53ea5/ndsbuild/sim/nds32/run`） | 同一固定 GNU provider 的通用执行入口 |

以上通过 WSL 启动；原厂 Z7II 运行还需要上游定义的解包五成员容器及显式输入，不应直接把 Z62 更新文件当作 Z7II bundle。原生测试使用的合成 bundle 不等于这些原厂输入。

完整二进制大小、SHA256、依赖版本、构建路径、退出码和验收边界已保存到 verified-artifacts.json（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/verified-artifacts.json`）。57 个原生程序各自的 TAP 计划、实际 OK 数、跳过数和耗时见 test-summary.json（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/test-summary.json`）；完整 Meson 原始日志仍在 `D:/z7work/0e53ea5/build/meson-logs/`。903 是本次 TAP 子测试数，NDS 的断言组单独记录，没有把不同粒度相加为“相机功能数量”。

## 4. 图片八项能力逐项核对

下表的“上游运行”仅指固定版本内的运行文档和归档；“模型/fixture”指实际存在的实现及其合成测试边界。整行不能都解释为本机原厂固件验证通过。

术语上，`bank` 表示相应设备的寄存器或工作状态分组，不应按字面理解为“银行”，也不能直接等同于两颗 E6。`slot` 是具体队列/环中的槽位，`kind` 是固件的软件资源类别；它们的含义必须跟随各自生产者和消费者。`VA` 是客体虚拟地址，`PA` 是相应模型地址空间中的物理地址，跨机型不能直接混用。

| 图片范围 | 源码中已实现的内容 | 上游原厂运行记录 / 限制 | Z62 可参考程度 |
|---|---|---|---|
| 固件与多执行域 | 五成员容器边界/CRC 校验；MAS 两核、SLA 两核、EX 一核组合；独立 RX/VR 与 GNU NDS32/TPJ | 五个成员被解析，不等于五个域自动共同运行。VR/TPJ 要显式启动和连接；复位/loader 包含声明假设 | 高，参考分域、隔离地址空间、loader 和传输；不能直接照搬地址 |
| 底层设备 | 有界 RAM/MMIO、GIC/NVIC、定时器、DMA/HDMAC、SPI、I2C、UART、GPIO 及若干跨域通道 | 未知地址、位、宽度和命令仍明确拒绝；不是完整芯片外设表。宿主时序不等于物理时序 | 高，尤其 IRQ/W1C、token、取消与背压 |
| 外部输入 | 有限电池 peer、虚拟普通族镜头、按键、保持式照片/视频选择、模式 ADC 与正交拨轮 | 电池/镜头身份、时延及部分标定是虚拟输入；不涵盖全部真实镜头族与电池行为 | 高，需核对本机型总线、引脚和命令消费者 |
| 图像链 | 照片→CMOS→RAW→统计/grid/paired→MAIN 图→三输出 DMA→原厂显示队列；有实际数值和像素搬运 | 上游有 1200×800 输入在原厂 1024×682 GUI 显示及动态替换记录；有限算法与物理 ASIC 保真度分开 | 很高，可参考软件 ISP 结构、输入归属与生命周期 |
| 原厂界面 | 原厂绘制图形、字形、图像合成及扫描输出，包含 Cairo image/A8 有限路径 | 上游有照片、状态界面、菜单及按键驱动高亮变化；全部菜单操作、设置接受和正常返回 live view 未完整验收 | 高，适合后续 OSD/布局实验；不等于 E7 界面功能已移植 |
| 相机操作 | P/S/A/M 输入路径；快门 Tv、光圈 Av、P 程序偏移等原厂设置变化；新增有限马达和曝光软件模型 | 设置变化、命令发出、马达完成和像素曝光分别验收；稳定覆盖全部模式、AF 端到端运行仍未证明 | 高，但必须分层描述 |
| 存储 | 原有 QEMU NVMe/PCI/块层接入，显式 slot0 介质、错误传播、独立保存测试 | 有原厂首个扇区读；完整原厂拍照/录像落盘仍未证明。slot1 SD 路径未实现 | 高，优先复用标准控制器；不把宿主写文件当原厂保存 |
| 诊断 | 官方 GDB/QMP、QOM 状态、原始图像检查、显式访问错误及停点；native qtest/unit | 诊断器和 fixture 不能保证完整相机启动，更不能保证刷写安全 | 可直接参考方法及证据分层 |

## 5. 图片之外的新实现：焦点、曝光与测试的真实边界

### 5.1 可以参考的新增代码

`lens.c` 已实现有限焦点 `70`、查询 `71`、停止 `78`，包含 busy、当前位置、目标、完成代数、运动插值、限位、取消和 reset/unrealize。范围 `[-4096,4096]`、每步 100 微秒、非零最短 2 毫秒均为明确的软件假设。

`cmos.c` 捕获时可以取得镜头焦点/光圈，按场景焦差产生有限模糊；`exposure-scale`、`iso-gain` 和光圈衰减控制软件 RAW 响应。存在 `optical-exposure-response`、focus sweep、lens-focus-loop，以及 AF-S/AF-C 命名的原生测试。本轮相关 CMOS 153 个子测试、镜头 unit 24 个子测试全部通过；其中曝光响应、AF-S 搜索/低纹理/取消/MF 切换及 AF-C 追踪/丢锁恢复/清理的测试均有实际 OK 输出。它们为可控对焦/亮度实验提供了实际代码。

### 5.2 不能仅根据测试名称宣布原厂 AF 完成

关键反查为 `tests/qtest/nikon/cmos.c:171` 及 `:3051`：`pipeline_start` 使用 `functional_bundle()` 和 qtest；`test_group_afs_closed_loop_lock` 由测试端通过 QMP 逐次设置 `/machine/lens` 的 `focus-position`，触发输入、读取锐度，再由宿主选峰和写回位置。AF-C 相应测试也直接设置焦点位置。

因此这些测试的成立条件是合成设备模型与对比度响应，而不是未修改原厂 AF 任务自主完成搜索。`docs/devices/capturegroup/protocol.md:919` 起的 AF-S/AF-C 说明出现较强的“Firmware Decision / complete end-to-end”表述；本报告依据具体测试实现，将它限定为原生软件模型实验。原厂真正读取统计→自主发镜头命令→接收反馈→锁焦/跟踪，需要独立连续运行证据。

同理，曝光响应 fixture 不能证明原厂 Tv/Av/ISO 已全部连接到传感器曝光/增益控制，也不能证明真实光学曝光、PDAF、人眼识别及运动目标跟踪精度。

## 6. 上游当前仍未解决的难点

当前 `docs/validation/frontier.md` 不只包含早期成功截图，还保留了后续失败。不能把不同修订、不同输入、调试器停顿和独立原生测试相加成一次完整验收。

| 难点 | 固定版本中记录的状态 | 对后续 Z62 的意义 |
|---|---|---|
| 长期取景和 FIFO 有界性 | 有一次 143.15 宿主秒的两轮 A/S/P/M 切换通过；之后更长窗口仍出现 AF 异常、60/60 输入 FIFO，以及模式请求未真正交付 | 每个模式 dwell 都要验新帧与队列回收；旧成功窗口不能覆盖新版本全部输入 |
| 后处理/模式参数 | 插值 POST 参数、BB 六参数、`11c=0` split129-knot 等仍有未恢复分支；C 曲线只支持明确有限合同 | 不能只改白名单接纳所有新参数；需要恢复对应数值与依赖 |
| 停止和完整关机 | 已增加 paired 银行局部收尾、shared-input hold 等有限合同；正常 OFF 清理和稳定模式变化仍未完成 | 区分取消、host 子任务排空、保留结果、ACK 与原厂 stop 完成 |
| 独立原厂错误 | 历史 AF 空指针、resource74 的十记录生命周期、软件 event pool 压力和 SPI 共享事务问题分别有诊断 | 不把所有停顿都归因于一个缺少的 IRQ；对首个失败作生产者/消费者审计 |
| 最新输入组合 | 最新一组 RAW 优化后的首个无调试 cold-neutral 加物理 ACCELE 叠加窗口，在约 1.89 秒出现 loader prefetch abort，尚未产生 paired 任务 | 构建通过及数值等价不能保证特定原厂输入组合可启动 |
| 完整拍摄与录像 | 全分辨率 still acquisition、原厂保存、内录/录像及长期稳定性仍在 frontier 未完成项中 | 无法据此保证 JPEG/NEF/视频功能或 8-bit N-Log 已完整实现 |
| 硬件与更新安全 | 原始 BootROM、完整板级 flash、物理传感器、真实镜头和升级/断电恢复链不完整 | 不能用此 QEMU 为刷机出具“不黑砖”结论 |

上述宿主秒数来自不同上游记录，不是实机帧率，也不是本轮的本机性能测试。

## 7. 对本项目的建议顺序

最先参考 r49 的模式数据合同，而不是先移植更多界面功能。Z62 已观察到命令组 0 第二字 `40→34`，组 1 第一字 `305→300`、第二字 `1002→846`；原厂视频 OSD 出现但有效图像与回切恢复失败。单独扩大允许值无法证明新 RAW、统计/grid、MAIN 和实际完成来源正确。

先采集新模式的完整输入/输出与归属，再实现独立数值生产和完成，接着验照片→视频→照片、菜单和 OFF 生命周期。之后复用虚拟镜头、可控纹理和焦点/曝光输入，建立原厂 AF 消费与自主运动验证。具体代码入口和每一步门槛见 reference-map（本地证据，未分发：`<WORKSPACE>/analysis/nightglasses-z7ii-0e53ea5/reference-map.md`）。

本轮只提炼参考，没有实施上述 Z62 功能，也没有改变其冻结 r48 设备、r49 观察工具或默认入口。

## 8. 来源、许可与贡献归属

- 参考实现：[nightglasses/z7ii-qemu 固定源码](https://github.com/nightglasses/z7ii-qemu/tree/0e53ea5a6d4f3fc635d63c195a92e943370ac5e9)。机器、设备、peer、测试及中文报告中的实现分析均明确归于该参考项目。
- 原始研究：[mashiro01/nightglass](https://github.com/mashiro01/nightglass)，由上游 `startup/components.md`、`startup/system.md` 和各设备合同引用；本轮不宣称重新完成其固件逆向。
- CPU/TCG/QOM/总线等基础：[qemu/qemu](https://github.com/qemu/qemu/tree/4fc49f46dc95d4a27de2509e7fceb2931e91faeb)；NDS32 ISA 执行：[andestech/gdb](https://github.com/andestech/gdb/tree/4327fa948f903c0705e0d87eed4cb182e24a6b6c)。
- 父仓库根部本轮未找到统一 LICENSE。抽查 Nikon QEMU 文件 SPDX 为 `GPL-2.0-or-later`，NDS32 自有文件为 `GPL-3.0-or-later`；官方依赖另有 COPYING 等文件。未来复制/修改/分发须核对具体文件与依赖，保留原版权、许可证及来源。
- 本轮贡献仅为本机依赖准备、构建与核验，以及中文参考整理；未将上游实现冒称为 Z62 新完成代码，未发布上游固件。

## 9. Evidence → Finding → Path

| Evidence | 内容与位置 | 可支持的结论 |
|---|---|---|
| E1 | 本轮 `ls-remote`、checkout、gitlink 与提交元数据 | F1：本次分析的是指定仓库与固定版本 |
| E2 | 第 3 节正式命令；`qemu-configure.txt`、`qemu-build-end.txt`、`qemu-checks.txt`、`nds-checks.txt`、`test-summary.json`、`verified-artifacts.json` | F2：ARM/RX/TPJ 本机构建及原生检查通过；二进制 SHA 可复核，范围不超过这些结果 |
| E3 | 固定版本 `README.md`、`docs/architecture.md`、`docs/validation/frontier.md` | F3：上游有边界的原厂进展及未完成项；不是本机复现 |
| E4 | `cmos.c`、`lens.c`、`tests/qtest/nikon/cmos.c`、`tests/unit/nikon/lens.c` | F4：有限焦点/曝光模型存在；宿主测试搜索不能等同原厂 AF 算法运行 |
| E5 | 本项目冻结 r48/r49 报告，及本轮参考映射 | F5：Z62 下一阶段应先恢复新模式数据合同，不能只改参数白名单 |

P1，`path_type=callflow`：显式场景输入→CMOS 的有限曝光/失焦→实际 RAW→统计/grid/paired→MAIN→DMA→原厂显示队列；每个生产者拥有自己的配置、代数、容量与完成条件。

P2，`path_type=callflow`：合成 AF fixture→宿主 QMP 设焦点→CMOS/统计→宿主选峰→宿主 QMP 写回。它解释测试覆盖的真实调用路径，并明确缺少“原厂 AF 自主决策”的运行证明。

P3，`path_type=development`：固定源码/依赖→官方 native 构建→机型与原生测试→保留失败/成功边界→提炼 Z62 适配条件。完整实机验证在本次授权范围之外。
