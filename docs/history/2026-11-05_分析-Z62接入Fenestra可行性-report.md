# Z6II C1.70 / Z62-QEMU 接入 Fenestra 可行性评估

> 日期：2026-11-05（UTC+08:00）。仅研究，未获实施批准。  
> **结论：可以立项做 ARM32 实验移植，但不能直接安装现成 Fenestra；当前不建议真机刷写。**

## 1. 决策摘要

Fenestra 符合“固件内运行一个核心，再从卡加载独立插件”的目标，不是电脑端遥控插件。但是本轮固定的上游只有 **ZR C1.10、Z9 C5.32** 两个主线配置，核心构建、原生汇编、模块打包和 `.wlm` 加载均建立在 **AArch64** 上。用户现有 Z6II C1.70 使用 ARM/Thumb 执行路径，QEMU 配置为 Cortex-A7；这里的 CPU 型号是模型选择，不当作物理芯片鉴定。

因此这不是“改型号、换地址、重编一次”的小改动，而是 **跨 ISA 后端 + 精确固件端口 + 原厂服务适配**。现有 `.wlm` 二进制不能直接使用；插件源代码也只有在所需能力已适配后才可能重新编译运行。

现有 Z62-QEMU 已有原厂菜单、按键、候选成员加载与独立观测机制，适合做离线原型。没有必要先修完所有拍照链路，才开始最小插件试验；但当前尚未实现的原厂文件保存、完整升级、真实 NOR／标定、DMA／缓存和电源路径，不能用软件目录卡或显示成功代替验证。

**建议：若用户批准，先做有明确退出条件的“Z62/ARM32 最小 Fenestra 端口”，只在 QEMU 中验证。不要先制作可刷固件，也不要声称兼容现成插件生态。**

## 2. 范围与对象

范围见 [scope.md](../../analysis/fenestra-feasibility/scope.md)。本轮读取公开源码、文档、issue 和本地现有文件；没有运行第三方构建／补丁脚本，没有下载固件／密钥，没有访问 USB/PTP 或物理卡。

| 对象 | 固定身份或状态 |
|---|---|
| Fenestra | `b199dcdfbb0ef536c6269ae5a9d97c376d488b8b` |
| Z62 基础子模块 | `4f4389944fc339d107f22f5f7ca3f90cc34b78de`；上层另有本地研究代码 |
| 当前工作区总览 | 已到 r104，另记录本地 r105–r109；默认交互 r75／r69；不把历史 r5 结论当作现状 |
| 原始更新包 | 49,002,888 字节；SHA256 `5a9640b4c07abe1ecbf5a52655cbec6b893bba045bb2a1a1d21055b9f8f9d06d` |
| 原始 master | 38,750,138 字节；SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4` |

输入身份和源码摘要保存在 source-check.json（本地证据，未分发：`<WORKSPACE>/analysis/fenestra-feasibility/source-check.json`）。本轮重新只读核对原包哈希，以及 master/slave/controller 的大小、哈希与 CRC；均符合当前基线。

## 3. Fenestra 已实现什么

根据固定提交的 [README](https://github.com/WonderLantern/Fenestra/blob/b199dcdfbb0ef536c6269ae5a9d97c376d488b8b/README.md)、[架构](https://github.com/WonderLantern/Fenestra/blob/b199dcdfbb0ef536c6269ae5a9d97c376d488b8b/docs/architecture.md)、[模块规范](https://github.com/WonderLantern/Fenestra/blob/b199dcdfbb0ef536c6269ae5a9d97c376d488b8b/docs/module-format.md)和实际加载器：

- 在原厂固件中加入启动、关机、菜单／输入等钩子和核心；激活前也会执行部分扩展钩子。
- 从存储卡 `FENESTRA/` 目录发现独立 `.wlm`，模块加入不需要重新编译核心。
- 提供模块管理、页面／控件、消息服务、命名原厂绑定和资源生命周期管理；示例包括 Hello 页面及字符雨动画。
- 模块与精确固件身份绑定，不是只按相机型号兼容。
- 当前模块格式 ISA=1 为 AArch64；重定位为内部 64 位指针，打包器要求 ELF64/AArch64 和 `R_AARCH64_RELATIVE`。
- 自动激活默认关闭；卡上异常关机标记可阻止后续自动加载。但它不是硬件恢复模式，不保证所有故障均能靠拔卡解决。
- 禁用驻留模块通常在下一次启动生效，不提供通用热卸载。
- SHA256 是完整性／身份检查，不是模块发布者数字签名，也不证明模块安全。原生调用、硬件访问和 panic 机制不能视为对任意插件的完整隔离。

**授权条件：** 项目采用 CC BY-NC-SA 4.0，并有商拍／影视制作额外许可；不是可无条件商业分发的宽松许可证。收费拍摄与出售受许可软件／插件、收费刷机服务是不同事项。重新分发需核对项目及依赖的各自条款，不把 Fenestra 代码直接混入 QEMU 后忽略许可证边界。

## 4. Z62 适配缺口与可复用基础

| 层面 | 本轮证据 | 对实施的影响 |
|---|---|---|
| 指令集／调用 ABI | Z62 原厂 ARM/Thumb；Fenestra 构建固定 `aarch64-none-elf`，含 AAPCS64 调用和 EL1 寄存器代码 | 新增 AArch32 后端；适配寄存器／栈、结构布局、Thumb 状态、32 位重定位、异常／任务上下文；不能只改编译参数 |
| 模块格式与 SDK | C 加载器显式拒绝非 AArch64；重定位目标写 8 字节 | 明确定义新 ISA／ABI，修改打包器和加载器，重编插件；保持旧端口回归 |
| 精确固件绑定 | 上游 profile 只有 ZR/Z9 | 为 Z62 C1.70 独立恢复原厂函数、结构和事件语义；不能平移地址或仅更改 SHA |
| 启动／关机钩子 | 激活前即有扩展执行；需要替代指令与返回点 | 独立定位原始指令窗口，验证 PC-relative 重定位、现场保留和 task context；停用状态启动也要 A/B |
| 代码空间 | 现有候选器固定各成员名称和长度 | 先确认真实可执行空间和镜像／RAM 映射。若需追加／扩容，新增经验证的显式布局合同；不能关闭长度／身份检查冒充解决 |
| RTOS／内存／缓存 | 上游有专用任务、MMU、缓存与 IRQ 适配；现有 Z62 有部分原厂观测 | 重新验证 Z62 分配／释放、任务／等待、CP15／权限／缓存同步；不可照搬 AArch64 EL1 代码 |
| 卡文件 | Fenestra 要由客体原厂 API 打开、枚举、读取 `.wlm` | 先证明 Z62 客体实际从普通文件虚拟 SD 读模块字节；块级 SD 测试不等于原厂文件 API 合同 |
| 宿主目录卡 | `z62_directory_card.py` 明写不是 SD/FAT，也不被固件挂载 | 不能直接把其中的文件当作原厂已加载插件；宿主喂入只能标为早期注入试验 |
| 原厂菜单／按键 | 当前已有实际原厂执行和输入证据 | 可作为插件 UI 研究基础，但页面命名空间、字体、焦点、回调生命期要单独适配 |
| PTP 调试 | 已有 C1.70 静态操作表；不等于 Fenestra 调试扩展端口 | 第一阶段可不做；后续分别验证原有会话、取消／断连和新操作，不用主机调试接口冒充客体 PTP |
| 影像类插件 | 当前原厂拍照编码／客体存卡与部分恢复未通过 | 第一阶段排除 AF、RAW／LUT、编码等复杂插件；是否可用取决于各自原厂能力，不能由插件菜单存在推断 |

**等价依赖锚点（E-imports）：** 本轮是源码与文档评估，不是 PE/ELF 样本导入表恢复。Fenestra 的外部能力经 profile 命名绑定进入原厂 RTOS、内存／MMU、卡文件、UI／显示、IRQ 和 PTP；所需地址和 ABI 位于 `host/platform_profiles.py` 及 `src/platform/`。这些依赖类别已核对，Z62 对应绑定尚未实现；没有声称完成 Z62 二进制 IDA survey。

## 5. 上游风险记录

固定 README 第 5 行有明确的 **“DO NOT FLASH CURRENT VERSION”** 警告，当前不能忽略。

另核对 [原始 Zf 故障 #9](https://github.com/WonderLantern/Fenestra/issues/9) 与 [故障案例索引 #11](https://github.com/WonderLantern/Fenestra/issues/11)：Zf C3.01 曾出现视频模式下背光黑屏／循环启动，报告者在开机前切回 Stills 后恢复。索引明确区分用户恢复、候选机制、根因确认和修复认证；现场异常 PC、NVM 实际内容和复位原因仍不足，没有认证修复。

这不是“Z6II 已证实有同一故障”，也不是“永久变砖已确认”；它说明即使没有主动 Flash 写入，调用原厂配置保存／恢复仍可能产生持久化副作用，QEMU 也未覆盖所有相关路径。

## 6. 替代方案的选择边界

应区分三类：**Nikon 固件扩展参考、其他品牌模块系统、电脑端插件**。后者即使支持 Z6II，也不实现本次的“在相机固件里加载插件”。

| 候选及固定版本 | 已核对的加载机制 | 与本项目的关系 |
|---|---|---|
| [WonderLantern Z30](https://github.com/WonderLantern/wonder-lantern-z30/tree/b602735fbcdc47eec6300f0422b30a68110fc237) | C1.20；原厂文件 API 从 `Z30/CORE.ZMOD` 读取受信任 Thumb PIC 原生模块，成功后驻留到关机 | 最接近当前 ARM32 卡载目标的参考之一；目前固定一个模块路径，不等于完整多插件管理系统；不能装到 Z6II |
| [WonderLantern 初代 Z6](https://github.com/WonderLantern/WonderLantern-z6/tree/f63af8f21671013163ed2657b43d77ef9fda8b75) | C3.80；共用主固件配套卡根目录 Shuttersound／Slowshutter／Grid 等独立核心；缺一个核心不加载相应功能 | 可参考功能与固件分离，但不是通用 `.wlm` SDK，初代 Z6 不是 Z6II |
| [NikonHacker 工具集](https://github.com/simeonpilgrim/nikon-firmware-tools/tree/89ad7354b6d721260b3e999061fefc51f3580ee0) | 以离线解包、逆向和版本化静态补丁为主 | 有容器／补丁研究价值；未核实到 Z6II 通用动态插件运行时，不能因存在部分 Z 系列解码就推断支持插件 |
| [Magic Lantern](https://github.com/reticulatedpines/magiclantern_simplified/tree/142472e95054d73640f50789ac0fd66325499d82) | Canon EOS；`ML/MODULES/` 的 `.mo` 动态模块、符号绑定／事件与 Lua 扩展 | 原生模块／脚本分层参考；不是 Nikon 可安装端口 |
| [CHDK 镜像](https://github.com/AHOHNMYC/chdk/tree/012eb24f6b2387379d6ebccbd9cc31a080ce186e) | Canon PowerShot；CHDK-FLAT 模块加载与 Lua／uBASIC | 加载器和脚本接口参考；不是 Nikon 可安装端口；该镜像不是对最新主线的完整审计 |

Z30 关键源码复核：[modules.py](https://github.com/WonderLantern/wonder-lantern-z30/blob/b602735fbcdc47eec6300f0422b30a68110fc237/src/z30_extensions/modules.py)、[module_host.py](https://github.com/WonderLantern/wonder-lantern-z30/blob/b602735fbcdc47eec6300f0422b30a68110fc237/src/z30_extensions/features/module_host.py)。当前头部是 `<4s7I32s`（64 字节），ABI=2，包含精确原厂 SHA；不是只校验一个 CRC 的任意 Thumb 文件。宿主导出表为 `<5I`，位置无关代码、文件／内存／缓存和菜单适配仍需按 Z62 重新实现。上游关于 Z30 实机验证的注释是上游声明，不是本轮在相机上复现。

Magic Lantern 可查 `src/module.c`／`src/module.h`；CHDK 可查 `modules/module_load.c`／`modules/luascript.c`。不把 Canon 的启动标志、卡引导和恢复行为移植成对 Nikon 安全性的承诺。各项目许可证独立，代码复用前需核对具体文件。

本轮公开搜索与候选 README／源码核查没有发现已经验收的 Z6II C1.70 通用插件端口；这是本轮检索范围内的结果，不宣称 GitHub 上绝对不存在其他未索引项目、个人分支或未合并端口。

**两条路线：** 如果必须要 Fenestra 的 SDK、模块管理界面和统一命名服务，选择 Fenestra 的 Z62/ARM32 实验端口，并借鉴 Z30 机型层；如果核心诉求只是“从 SD 卡加载自己编写的新插件”，优先评估 Z30 ZMOD 式轻量宿主，所需后端范围更小，但多模块枚举／管理需要另加。后者不能称为完整 Fenestra，也不兼容其现成 AArch64 `.wlm`。Magic Lantern／CHDK 保持架构参考，不建议另开整套 Canon 移植。

检索记录（2026-11-05）：GitHub repository search 使用 `WonderLantern`、`nikon firmware`、`z62-qemu`、`nikon z62`、`magiclantern`、`CHDK mirror`；另做网页查询 `site:github.com/WonderLantern/Fenestra Z6 II ARM32` 和 `site:github.com Nikon Z6II plugin firmware loader`。只对上述最相关候选作有界核查，不把搜索无结果写成全网不存在。

## 7. 建议实施顺序（尚未执行）

| 阶段 | 工作与验收 | 不应扩大到 |
|---|---|---|
| A：可放置／可进入 | 固定 C1.70 哈希，定位空间与启动／关机窗口；ARM32 后端与最小核心；不激活时和原版同配置 A/B；原逻辑正常返回 | 完整插件市场、拍照插件、真机安装 |
| B：最小独立模块 | 新 ISA／ABI 的模块独立构建；先做纯计算或日志 Hello，证明实际 ARM32 指令执行、返回、错误 ISA／错误固件／损坏模块拒绝；再增加 Hello 页面 | 把现有 AArch64 Hello 直接改标识运行；把屏幕标签当执行证据 |
| C：真正卡载与管理 | 经 Z62 原厂文件 API 从虚拟 SD 读取，实际字节／哈希一致；菜单启用／禁用、方向输入、配置、异常标记、重开／关机与生命周期 | 用宿主目录卡注入冒充原厂卡载；通用热卸载 |
| D：逐项扩展 | 只接入已经独立确认的属性、显示／按键能力；多模块压力与故障回收单独验证 | 同时改 RAW、AF、编码、升级及全部机身接口 |
| E：硬件可行性另审 | 原厂启动加载边界、完整容器、摘要／签名规则、更新／断电恢复、真实 NOR 与缓存／设备效应另行分析；需用户新的明确决定 | 由 QEMU 通过推出安全刷机 |

P-1（`path_type=callflow`，拟实施路径）：原厂启动完成钩子 → 停用／手动激活检查 → Z62 原厂卡文件 API → 模块 ISA／固件身份／边界／哈希检查 → 私有内存／重定位／可执行权限／缓存同步 → 模块入口 → 命名服务及原厂菜单／输入 → 关机停止与资源保留策略。

阶段 A 的未知可执行空间和原厂绑定，是首要技术门槛；若尚不能验证，就应停在研究结论，不能以空白字节、模型多映射一段 RAM 或伪造返回值代替可安装性的证明。开发期可用显式 RAM 注入验证后端，但须单独标注，不冒充固件安装成功。

本轮不提供确定工期或成功率：地址数量、可用代码空间和原厂文件 ABI 尚未完成定点验证，给出精确天数没有依据。

## 8. Evidence → Finding → Path 与验证记录

| Evidence | 来源／复核 | Finding（严重性均 `n/a_re`） | 后续路径 |
|---|---|---|---|
| E-1 | 固定提交 README、profile AST；SHA 见 JSON | F-1：无 Z62 主线配置；高置信、已确认 | 新建精确端口，不套旧 profile |
| E-2 | `src/module.c`、`host/pack_module.py`、SDK flags、模块规范 | F-2：现成模块限 AArch64；高置信、已确认 | 新 ISA／32 位 ABI 与后端 |
| E-3 | 本地 QEMU CPU 配置、Z62 端口说明和 ARM/Thumb 路径 | F-3：当前执行环境与 AArch64 不兼容；高置信、已确认 | P-1／阶段 A–B |
| E-4 | 候选器源码；原包及三成员只读大小／SHA／CRC 检查 | F-4：具备隔离候选入口，但固定长度且不认证刷写；高置信、已确认 | 先定代码空间，保留输入护栏 |
| E-5 | 本地总览及目录卡源码头注释 | F-5：宿主软件卡不等于客体 SD／原厂 API；高置信、已确认 | 阶段 C |
| E-6 | README 警告；公开 #9／#11，访问于 2026-11-05 | F-6：需单独审视启动／持久化风险；高置信；Zf 现场根因未定 | 阶段 A／E；不跨机型外推 |

源码内容哈希使用 SHA256，见 JSON；公开 issue 为可变页面，`content_hash=n/a`，报告保留访问日期与准确 URL，不把后续页面修改算作本轮已知。

### 本轮实际执行

1. 读取项目记忆和工作区状态，保留既有未提交内容。
2. 将 Fenestra 源码仅克隆到 PI scratch，固定并核对提交。
3. 检查源码、文档、公开 issue，结合现有 Z62 入口作静态对照；独立检索替代项目。
4. 只读检查本地原始输入；12 项静态／身份检查通过，摘要落盘。首次内联核验因路径转义语法错误未执行，修正后完整执行成功。
5. 新增本报告、范围文件与 JSON 摘要；未修改固件、现有源码、QEMU 或子模块；未编译／启动移植版，未连接相机，未提交／推送。

### 可复核入口

- GitHub 固定提交可直接打开上述链接；重新检索时不要把移动的 `main` 当作同一版本。
- 本地对象身份来自 `tools/prepare_reference_firmware.py:PROFILES['z62']`；比较实际字节的大小、SHA256 和 `binascii.crc_hqx(data, 0)`，本轮三个成员余数均为 0。
- JSON 的 `sources` 数组记录已检查关键源码哈希，`checks` 列出 12 项检查；`port_built`、`port_runtime_verified`、`flash_safety_verified` 均为 false。

**未完成／待用户决定：** ARM32 后端、Z62 原厂绑定与代码空间、卡载模块、插件菜单实跑、完整打包与真机安全均未验收。本轮任务只完成可行性评估，不表示上述实现完成。
