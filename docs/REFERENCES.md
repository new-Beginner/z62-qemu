# 参考、复用与致谢

本工程不是从零实现 QEMU 或尼康硬件。直接基础、参考研究和外部工具分开列出；上游实现不能自动当作 Z6II 规格或本工程已验收功能。

## 直接基础与固定提交

| 项目 / 作者或贡献者 | 固定版本 | 使用范围 |
|---|---|---|
| [QEMU](https://www.qemu.org/) 及贡献者 | 10.2.4；源码包 SHA `821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746` | ARM system emulation、TCG、内存、设备、QMP/qtest/GDB、构建基础；保留逐文件许可 |
| [xiaoqingfeng0526/nikon-z62-qemu](https://github.com/xiaoqingfeng0526/nikon-z62-qemu) | R3，`4f4389944fc339d107f22f5f7ca3f90cc34b78de` | 直接 Z62 板型、原厂显示/控制器、准备脚本基础；保留原作者和上游署名 |
| [JKWTCN/z72-qemu](https://github.com/JKWTCN/z72-qemu) | 构建固定 `f6b80ec650116a6b0117d31f9ea112b05bb7f52a` | 双 E6 视图、设备/完成协议、输入/SD/肩屏和诊断对照；不照搬机型地址/几何 |
| [WonderLantern/z6-qemu](https://github.com/WonderLantern/z6-qemu)，vic2349 等 | `419a1f2a91a1f2d3a0209027c29606475f7fe26f` | LCD/覆盖层、软件 GPU/ISP、描述符和生命周期参考；Z62 R3 亦适配其 LCD |
| [WonderLantern/z7-qemu](https://github.com/WonderLantern/z7-qemu)，[R3tr0ooo](https://github.com/R3tr0ooo) 及贡献者 | 上游记录 `97abf0b81cd3211f8374a38987a0beaf4549b90f` | Z6/Z72/Z62 共同来源之一：实验板型、图像/网格、构建和测试 |
| [WonderLantern/nikon-fw-key-tool](https://github.com/WonderLantern/nikon-fw-key-tool)，mkx173 等 | `33426e892afd329a3b366b73776bcf53b9ac4ee8` | 外部固件包解析相关工具；GPLv3，保留独立条款 |
| [simeonpilgrim/nikon-firmware-tools](https://github.com/simeonpilgrim/nikon-firmware-tools) 及贡献者 | `de8019ee30db7fe7bc61e520da289078ae82dcaa` | 公开 XOR 表/格式研究线索；按原仓库各文件条款，不替其宣称统一许可 |

原始 NOTICE 与 QEMU 许可说明见 [LICENSES](../LICENSES)。完整贡献者以各仓库 Git 历史为准，不能把仓库所有者当所有代码的唯一作者。

上游自身还记录 WonderLantern Z6 `9848467e8d9d2fa73ee382f776278f1b91ba4352`，及 Z62 R3 最初基于的 Z72 `f5f4ba31b324de5abf6f24d399afff878ffd949a`。这是来源链的不同层次，不与本仓库工作区提交混用。

## 原 Z62 地址与可访问同源副本

2026-11-01～02 的多轮检查中，原 Z62 地址出现连接失败与 HTTP/API 404，具体原因未确认，不能据此断言仓库删除或停止维护。

[new-Beginner/nikon-z62-qemu](https://github.com/new-Beginner/nikon-z62-qemu) 的 `z62-r3` 和 `v2026.10.26-r3` 可取得相同 `4f438994…`，本仓库子模块采用这一可访问副本。**原始 Z62 作者仍按 xiaoqingfeng0526 署名**，不把副本当作重新创作或官方迁移。

已审阅 Z72 上游 `d91718fd5c7de88bb48abdc6469669170d6f20d6`，当时比固定提交多203次提交。只针对相关停止/结果、邮箱、描述符与显示线索交叉核对，未全量合并，不宣称所有新能力已在 Z62 通过。

## 其他资料与工具

- [nightglasses/z7ii-qemu](https://github.com/nightglasses/z7ii-qemu)，复用研究提交 `0e53ea5a6d4f3fc635d63c195a92e943370ac5e9`：内核SVC/事件处理入口，以及r86 CaptureWork分工和数据研究；Z6II事件CB、实际置位/等待、几何与LUT另用目标核对。r86在本项目实现两级有理采样与独立测试，不直接套用Z72的整数缩放约束、RAM地址或宣称硬件／整机等价。
- [TRON Forum T-Kernel 2.0](https://github.com/tron-forum/tkernel_2/tree/5778f619bdb354443551888dc2e9aa191e684da8)：事件语义参考，固定 `5778f619bdb354443551888dc2e9aa191e684da8`。公开服务编号 `80360500h` 与目标 `80300500h` 不同，不能据此认定具体 RTOS 版本；目标布局以 Z6II ARM 指令和运行结构为准。参考源码作为本地缓存不随本仓库复制，未并入设备模型。

- [tylermcm/WonderLanternZ7](https://github.com/tylermcm/WonderLanternZ7)，本地记录 `a99e5da7c41dd5931c35faa7287fa04dcc847ebc`：辅助硬件/图像研究对照，不是直接构建依赖；不替它增加许可证。
- Nikon Z6II 官方手册及用户合法取得的 C1.70 包：用于型号、控件和原厂行为交叉核对。更新包不等于完整 ROM，原件不随仓库分发。
- 本地 Tornado NKN 恢复资料：PC 端维修软件、数据结构、AF Shift 和固件行为线索。它是反编译恢复包，不是完整原始 Pascal 工程、相机 OS 或镜头协议规格；保护区未全部去虚拟化。原软件及恢复包不随仓库公开。
- NKN 的 PC→相机命令必须追到相机内部驱动，不能直接当 Z 卡口触点协议或 AF 替代实现。
- Ghidra、Capstone、Unicorn：静态/局部执行和原字节核对。局部导出可能有坏入口、PIC/尾跳等限制，需要动态证据。
- MSYS2 UCRT64、GCC、Meson/Ninja、GLib、Pixman：既有原生 Windows 构建工具链。
- NumPy/Pillow：场景、像素和 JPEG；[RawPy](https://github.com/letmaik/rawpy)/[LibRaw](https://github.com/LibRaw/LibRaw)：独立 NEF 解码；[PyAV](https://github.com/PyAV-Org/PyAV)/[FFmpeg](https://ffmpeg.org/)：C 视频编码、封装、解码和审计。

依赖版本见根目录 requirements 文件。工具及链接库遵循其自身许可，本项目 GPL 声明不覆盖第三方/Nikon/NKN 的权利。

## 本仓库新增范围

在上述基础上推进了有界 RAW/统计/近似预览与完成通知、机身输入、候选加载、虚拟场景及软件照片/NEF/视频、Windows 后台任务生命周期、严格取证和验证工具。具体实现、失败和限制见 [开发过程](DEVELOPMENT.md)，不能将本列表理解成完整相机/AF 交付。
