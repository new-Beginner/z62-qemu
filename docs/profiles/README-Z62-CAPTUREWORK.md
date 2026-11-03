# r86 采集像素核心

2026-11-04。本文保留 **r86 当时的独立软件数值核心范围**。后续 r87–r91 已增加 MAIN、transfer 和独立 QEMU 采集设备，当前状态见 [采集后端说明](README-Z62-CAPTUREWORK-DEVICE.md)，下表的“未实现”是 r86 阶段记录。当前可交互入口仍是 r75 界面／r69 内核；新增设备不使原厂拍照、模式往返或 AF 自动变为可用。

## 已实现和未实现

| 项目 | 状态 | 范围 |
|---|---|---|
| RAW16 LE 输入、独立输入／输出 stride | 已实现 C | 输入只读；先验证尺寸、跨度和地址重叠 |
| 两级有理 nearest 缩小 | 已实现 C | 逐级取整，不能合并为单级；不是恢复出的硅片采样公式 |
| CFA 2×2 相位保持 | 已实现 C | 各色相位分开采样；拒绝奇数 CFA 尺寸 |
| 256 项 RAW LUT | 已实现 C | 高 8 位索引；先复制 LUT、验证严格递增及位宽，输出属于编码域 |
| RAW12／14／16 LE 连续位流 | 已实现 C | 原始字节 golden、独立逐位解码；保留输出行填充 |
| 范围与失败行为 | 已实现 C | 输入边长≤4096、≤4 Mi samples、跨度≤64 MiB；拒绝上采样、非零 correction_flags、坏 stride／LUT／跨度／重叠，失败不改输出 |
| 虚拟 MAIN 生产者、来源和配置提交 | 未实现 D | 当前测试 MAIN 是合成梯度；寄存器读回不能证明原厂实际 commit |
| QEMU DMA、bank/ring、IRQ、生命周期 | 未实现 D | 未接 MMIO、timer、DMA、IRQ；stop/reset/cancel、generation、背压合同待建 |
| LUT 描述、下游逆变换 | 未实现 D | 不能将 LUT 编码 RAW 直接交给假定线性的旧 ISP |
| 全部 ISP／真实 AF 数据 | 未实现 D | 65 点曲线／24 系数等不由本核心代填；不生成真实 PDAF |

核心在 [nikon-z62-capturework-pixels.h](../../qemu/z62-capturework/nikon-z62-capturework-pixels.h)，测试在 [native probe](../../tests/native/z62_capturework_pixels_probe.c) 和 [Python harness](../../tests/test_z62_capturework_pixels.py)。不依赖 QEMU 即可编译核心。

## 实际验证

在 r69 原始固件会话中仅 GET 和短暂 GDB 快照，没有机身控制输入或完成注入。读回几何为 `2020×1342 → 1514×1342 → 1514×1006`，RAW12、stride 2272、有效行载荷 2271 字节；packing control 为 6，启用 256 项 LUT。两级缩放比非整数。

将此几何和 LUT 用于**合成 RAW16 MAIN 梯度**，得到 2,285,632 字节 RAW12。独立 C 参考先实化两级图像、用余数递推选样；NumPy 参考使用整数区间边界搜索、实化两级 CFA 数组和独立 RAW12 解码。全部 **1,523,084** 像素零差异，`A5` 行尾填充不变。

- 8 项实际 native C 测试通过，覆盖 golden、两级单色／CFA、LUT、padding 和拒绝路径。
- 输出 SHA256：`f8a5e164cb63b9040e9aa425b3b92f5c6d2fbfc3edd78ece9ca75e1746c6a1e1`。
- 数值验证原件：verified-pixels-1.json（本地证据，未分发：`analysis/z62-capturework-contract-r86/verified-pixels-1.json`）。公开仓库提供选定摘要及原件哈希，不分发 RAM 快照／原始输出。
- 状态与 native case 共 8 份源码原件已归档，原回执不改；历史 `native-observed-1` 不当作当前权威源码版本。

## 复现独立核心

本地研究环境已经有工作目录内 GCC 和 relocation manifest 时，在经过验证的 Q: 别名中运行：

```powershell
Set-Location Q:/
$env:TEMP='<WORKSPACE>/.runtime/tmp'
$env:TMP=$env:TEMP
$env:LANG='C'
$env:LC_ALL='C'
python -X utf8 -B -m unittest discover -s tests -p test_z62_capturework_pixels.py -v
```

Q: 必须确实指向工作区，不能占用其它已有映射。公开克隆没有私有 relocation manifest，也没有工具链；在 ASCII 路径准备合法 GCC 后，可以使用公开副本的独立检查入口：

```powershell
python -X utf8 -B tools/check_public_source.py --output analysis/publication/my-r86-check.json --native-compiler D:/z62-qemu/.runtime/tools/msys64/ucrt64/bin/gcc.exe
```

此命令分别记录无固件 Python 子集和 8 个实际 C case，不加载固件、不启动 QEMU。编译器示例路径需要换成自己已有工具链；工具链、TEMP 和构建输出都应位于工作目录。这里不宣称重跑完整历史 635 项或 RawPy 解码。

首次本轮重新验证在编译阶段失败，同时 stderr 的 UTF-8 解码失败；未改核心或绑定 helper，设置 ASCII 工作位置及 C locale 后 8 项通过。另一次仅编译检查也通过。未把这些检查合并为已证实的唯一环境根因；新检查器保留原始 stderr 的可解码错误信息。

## 集成前还要完成什么

1. 独立生成有来源标识、尺寸及虚拟时间的 MAIN 输入；不能将旧辅助／后级 RAW 冒充 MAIN。
2. 从原厂写入与 run 建立冻结配置，核对两套地址、ring/bank 和有效跨度；`BFI #1,#2` 仅证明一段独立参数，不足以否定旧 bit0 语义。
3. 验证停止、取消、复位、旧代次、背压及数据所有权，再执行实际 DMA 写回。
4. 为 LUT／transfer 建立不可变描述和明确的下游逆变换，拒绝域不匹配。
5. 在合法处理与写回后才交付对应 IRQ；不得把 standalone core 成功当作 unit 1/2/200 等其它单元完成。

组统计的曲线／系数本次读回为零，仅说明该快照读到零；不是“已擦除”“配置资源缺失”或可以补成功的证据。

## 参考与归属

参考 [nightglasses/z7ii-qemu](https://github.com/nightglasses/z7ii-qemu) 固定提交 `0e53ea5a6d4f3fc635d63c195a92e943370ac5e9` 的 CaptureWork 研究和工程划分。Z62 几何／LUT 独立读取，两级有理数采样和测试参考在本项目实现；不将 Z72 的整数缩放条件直接套用，也不据参考机型认定 Z62 硬件全部等价。新增核心按 GPL-2.0-or-later，原项目与第三方署名保留。
