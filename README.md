# z62-qemu

尼康 **Z6II / Z62 C1.70** 的 QEMU 系统仿真实验工程。运行原始固件，连接机身输入、虚拟场景、软件镜头、近似成像、虚拟存储和调试工具，逐步建设固件研究平台。

**当前为 2026-11-03 / r85 研究快照，尚未完成完整相机仿真，不能保证修改后的固件刷入真机不变砖。** 当前使用 **r69 QEMU 内核、r75 交互入口**；r76–r85 是后续诊断/研究编号，不表示又发布了多个新内核。原厂固件版本字段没有修改。

本项目基于他人的公开成果继续开发。直接基础包括 [xiaoqingfeng0526/nikon-z62-qemu](https://github.com/xiaoqingfeng0526/nikon-z62-qemu)、[JKWTCN/z72-qemu](https://github.com/JKWTCN/z72-qemu)、WonderLantern Z6/Z7 及其贡献者；近期内核研究还参考了 [nightglasses/z7ii-qemu](https://github.com/nightglasses/z7ii-qemu)。保留原作者、QEMU 和各依赖的许可证与署名，不把他人成果称为从零实现。

## 已实现、部分实现与缺失

层级：**A** 原始固件执行；**B** 有证据支持的设备/传输行为；**C** 显式软件替代；**D** 未实现或未验收。软件输出不能当作原厂 ISP、编码器或物理相机等价实现。

| 能力 | 当前状态 | 层级及主要限制 |
|---|---|---|
| C1.70 原厂/候选加载 | 同布局容器、成员边界和 CRC 检查，隔离运行及实际 ARM 指令执行已有验证 | A/B；不补齐完整 ROM/NOR，不验证实机升级与断电恢复 |
| 原厂 LCD、菜单、基础机身输入 | 菜单、导航和部分半按返回已有原始执行证据 | A/B；不是所有启动/菜单/拍摄循环均已完成 |
| 双段快门、拨轮、模式盘、ISO、AF-ON、Fn、摇杆、录像键等 | 输入通路与部分应用行为已验证 | A/B；输入到达不代表 AF、拍照或录像完成；拨轮不永久绑定快门/光圈 |
| RAW、有限/连续统计、近似 ISP、原厂 LCD 显示 | 受限描述符配方下实际 DMA、软件运算和显示 | B/C + A 消费；没有完整传感器/ISP 数学模型、全分辨率和硅片时序 |
| 虚拟场景、曝光、手动镜头 | 图像会随模型参数变化，来源/帧号/虚拟时间可追踪 | C；单平面近似、未校准，不是完整 Z 卡口协议或原厂 AF |
| JPEG、实验性 NEF、成组目录卡 | 独立解码、持久保存、回放、前后切换、2×放大和删除已验证 | C；JPEG 640×424；NEF 1514×1006、12 有效位存入 14 位，不等价原厂全分辨率 NEF |
| 已提交 ISP 来源上的照片操作 | r74 API 闭环、r75 实际网页控件和关闭重开检查通过 | C + A 输入/预览；来源确认不等于原厂编码或存入原厂 SD/DCIM |
| 软件视频 | 异步编码、进度、取消、H.264/MP4 保存、解码/时间/来源审计及回放已有有界验证 | C；640×424、VFR、静音；不同版本的已通过窗口分开记录，不称长稳或完整原厂录像 |
| 照片/视频模式往返 | **部分实现，完整交互验收失败** | 原厂选择值已能交付；未全按对照能确认视频新帧，拍照后切换及录像后返回仍有缺口 |
| 原厂采集/就绪/内核状态观测 | 已定位满队列拒绝、拍摄前就绪等待超时，读到实际内核事件 CB 和原始返回 | A + 宿主诊断；断点扰动，不是功能修复 |
| 原厂 JPEG/NEF 编码并存入客体卡 | **未完成** | D；目录卡的软件照片与原厂文件链分开 |
| 完整 Z 镜头通信、原厂 AF 多帧回放/闭环/评测 | **未完成** | D；没有自写 AF 冒充原算法，也未修改 AF 算法 |
| 合焦变绿、自动竖屏、新版 E7 自定义界面、内录 8-bit N-Log | **未作为可用固件功能交付** | 模拟器不能证明这些改动能在 Z6II 实机正常工作 |
| 真机刷写安全认证 | **不具备** | 模拟通过也不能排除实机黑砖、标定或更新路径问题 |

详细清单、失败范围及证据见 [能力覆盖表](docs/CAPABILITY-COVERAGE.md)。

## 当前进展与技术难点

- **r69/r71：**实际输出来源记录、模式提交确认、带来源的 JPEG/NEF 和短静音 MP4；完整模式往返未通过。
- **r73：**项目临时文件、缓存、工具链和会话迁入工作目录；Q: 仅是经过检查的工作目录 ASCII 别名，不另存数据。
- **r74/r75：**永久故障现场保存、软件照片整链、真实放大裁剪、参数/草稿同步；旧原始栈曾被清理的缺口如实记录。
- **r76–r79：**原厂采集入队在队列 60/60 时返回 0；未按快门的新会话也已满载并反复等待约 201 ms，不能把拥塞仅归因于全按。
- **r80–r82：**连续统计仍产出；捕获线路 101 通知调用。撤回把对象首字 `01000111h` 当作 flags 的错误解释。
- **r83–r85：**从 Z6II 原始 ARM 指令解析真实事件 CB；实际观察内核将 pattern 从 0 写为 `00800000h`、setter 返回 0，但 AND 等待 `05B00000h` 仍返回原始错误码 `FFCE0000h`，上层才转为 0。尚未补齐其它就绪生产者的合法设备合同。

主要难点是：多输入引擎、两银行及逐单元完成的合同不完整；真实帧对象、数据所有权与停止/重启依赖；NOR/个体标定缺失；镜头反馈与内部 AF/PDAF 数据格式未恢复。不能靠扩大队列、改原厂返回值、延长等待或补 ready 来宣布完成。公开 T-Kernel 2.0 的服务编号与目标不同，只用于语义参考，不据此宣称已确认整个 RTOS 产品和版本。

## 构建与运行

公开仓库是源码快照，**不附带 Nikon 固件、相机/NKN 原件、虚拟卡、工具链或已编译 EXE**。源码检查、原生设备测试、固件运行与实际界面验收是不同层级；首次克隆不会自动得到本地各阶段的 `.build` 缓存。

建议 Windows、Python 3.12 和 ASCII 的 D 盘工作路径。所有新产物留在项目目录：

```powershell
git clone --recurse-submodules https://github.com/new-Beginner/z62-qemu.git
cd z62-qemu
New-Item -ItemType Directory -Force .runtime/tmp | Out-Null
$env:TEMP=(Join-Path $PWD '.runtime/tmp')
$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=(Join-Path $PWD '.runtime/cache/pip')
$env:PYTHONDONTWRITEBYTECODE='1'
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-raw-verify.txt -r requirements-video.txt
```

固定 QEMU **10.2.4**。当前本机 r69 EXE SHA256 为 `37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`，VMState 55；这是已验收对象的身份，不要求另一台编译器生成相同字节。现有研究脚本有严格的源/二进制绑定，不应删检查或强改 manifest 来“修复”环境。

准备合法取得的 C1.70 输入、依赖及对应内核后，当前工作目录入口为：

```powershell
./start-z6ii-workspace.cmd --group23-fixture artifacts/fixtures/group23.bin --sd-card artifacts/fixtures/card.raw --software-card artifacts/my-photo-card
```

该入口使用 r75 界面/r69 内核，检查 Q: 是否确实指向当前目录；已被其它位置占用则拒绝。`group23` 是明确合成实验配置，非个体 NOR/标定。旧 `start-z6ii-qemu.cmd` 保留旧机身研究配置，不自动升级内核。

- [当前照片操作与限制](docs/profiles/README-Z62-COMMITTED-PHOTO.md)
- [输出来源、模式确认和 r69 构建边界](docs/profiles/README-Z62-OUTPUT-LINEAGE.md)
- [工作目录存储说明](docs/profiles/README-WORKSPACE-STORAGE.md)
- [异步软件录像路线](docs/profiles/README-Z62-ASYNC-VIDEO.md)
- [候选固件输入边界](docs/profiles/README-FIRMWARE-TEST.md)

未持有完整构建链时，可先运行公开仓库的 `tools/check_public_source.py` 所列无固件子集。它不等于重跑完整历史回归、原生 QEMU、LibRaw 解码或原厂窗口。本机最近一次历史全量为 r69 阶段的 635 项；后续只对新增范围做专项/实际运行，不能称为 r85 全量全部通过。

本轮独立公开副本已执行 **32 个模块、131 项测试，0 失败/错误/跳过**，并检查850个导出文件哈希、567份Python源码的内存编译及Markdown链接；没有加载固件或启动QEMU。该环境没有RawPy，因此本次公开检查不冒充重跑LibRaw/RawPy独立解码。源码检查结果与原厂实测记录分别保存。

## 开发过程、参考与许可证

开发顺序为：受控启动/菜单 → RAW/统计/近似 ISP → 机身输入 → 软件照片/NEF/视频 → 来源绑定与模式往返 → 当前原厂采集和内核等待定位。历史报告保留失败、未完成窗口和解释更正，不伪造逐日 Git 提交。

- [项目任务与逐阶段记录](docs/GOAL-Z62-QEMU.md)
- [r69–r71 输出来源和交互](docs/history/2026-11-03_实施-Z62输出来源与独立交互r69-r71-report.md)
- [r74/r75 照片闭环](docs/history/2026-11-03_实施-Z62永久诊断与照片闭环r74-r75-report.md)
- [r79–r82 无快门对照与字段更正](docs/history/2026-11-03_研究-Z62无快门拥塞与事件参数边界r79-r82-report.md)
- [r83–r85 真实内核事件与参考边界](docs/history/2026-11-03_研究-Z62真实内核事件与通知交付r83-r85-report.md)

上游来源包括 QEMU、xiaoqingfeng0526、JKWTCN、WonderLantern、R3tr0ooo、nightglasses 等作者及其贡献者；Nikon 官方资料用于机型/控件校对。Tornado NKN 仅作为 PC 维修软件协议和结构线索，不能当作镜头电气协议或 AF 源码，其原件/恢复包不公开。RawPy/LibRaw 用于独立 RAW 解码，PyAV/FFmpeg 用于 C 视频编码与审计。公开的 T-Kernel 2.0 仅为语义参考，目标代码仍独立核验。

本项目新增代码按仓库 GPL-2.0-or-later 声明及逐文件说明分发，第三方保留各自许可证；不对 Nikon/NKN 原件授予权利。公开副本会脱敏文档路径并保留源码字节，省略原始大轨迹/反汇编/固件；被省略的证据明确标作本地材料，不能把摘要当原始运行的替代。

## 公开仓库导航

- [构建与父依赖](docs/BUILD.md)
- [功能清单](docs/FEATURES.md)与[已知限制](docs/LIMITATIONS.md)
- [开发时间线](docs/DEVELOPMENT.md)
- [参考、作者与许可证](docs/REFERENCES.md)
- [本次源码验证范围](docs/VALIDATION.md)
- [最新内核事件验收摘要](docs/evidence/latest-kernel-events.json)（非完整原始轨迹）
