# Z6II JPEG／NEF 软件媒体配置 r25

在原有原生场景与共享机身输入上加入真正编码的 NEF、JPEG＋NEF 成组存卡，以及仅 NEF 回放。**这是 C 级软件编码，使用 1514×1006 预览 RAW；原厂全分辨率照片、原厂编码器、视频、AF 和完整更新流程仍未完成。**

## 拍摄和回放

在项目根目录运行：

```bat
start-z6ii-media.cmd
```

打开 <http://127.0.0.1:8682>。默认使用 C1.70 原包、JPEG＋NEF 和专用目录卡 `artifacts/z62-media-card-r25`。原厂主屏初始化需要约 17 秒客体时间，宿主等待可能是数分钟。硬件仍为冻结的 r24，主机媒体配置为 `2026.11.01-media-console-r25`。

1. 在“软件成像实验”中设置镜头和曝光。默认测试图位于归一化对焦位置 `0.65`；对焦、焦距、光圈及曝光会实际影响输入像素。
2. 选择 JPEG、NEF 或 JPEG＋NEF，点击“拍摄照片”或操作机身全按。两处使用同一按键边沿；排队成功后仍需等待实际保存回执。
3. 点击回放，使用放大／缩小或倍数选择检查照片。仅 NEF 模式显示该 NEF 内嵌的实际场景 JPEG 预览。
4. 下载当前照片；JPEG＋NEF 还可通过单独的“下载 NEF · C 模型”链接取伴生 NEF。
5. 删除会移除同一快门产生的全部成员，之后编号不回退。使用“关闭模拟器”退出会话。

下方软件开／关机只控制 C 级模型，不代表原厂机身电源拨杆。原厂屏幕与 C 模型曝光尚未完整同步，仍可能显示 F--、MF 或不同曝光值。

可选择其他格式、全新目录卡或固定布局候选包：

```bat
start-z6ii-media.cmd --photo-format nef --software-card artifacts\my-new-nef-card
start-z6ii-media.cmd --firmware "Z6_2_0170 (1).bin"
```

第二个例子是原包经候选分支加载；替换为修改包时仍受 [候选输入合同](README-FIRMWARE-TEST.md) 限制。候选健康未知；C 级照片成功不能证明候选中的原厂编码器或 AF 正确。

## RAW 来源与 NEF 格式

| 项目 | 实际行为 |
|---|---|
| 输入 | 只接受已经被 r24 原生四槽 DMA 消费的同源场景帧 |
| 来源校验 | 比对帧号、虚拟采样时间、RGB 像素 SHA256 和重构 packed12 的 SHA256 |
| RAW 几何 | 1514×1006、RGGB；不是 Z6II 全分辨率照片传感器 |
| 精度 | 原生 12 位样本左移 2 位写入 14 位；有效精度仍为 12 位 |
| 电平 | 源 black64／white4095；存储 black256／源 white16380，未作真实标定 |
| 编码 | Nikon F0 lossless14、四个 2048 预测器初值、真实 Huffman／差分比特流 |
| 容器 | TIFF NEF、Nikon type2 MakerNote、RAW 子 IFD、场景 JPEG 预览和拍摄元数据 |
| 身份 | `Model=Z62-QEMU C`，Software 与描述明确软件来源，不冒称实机输出 |
| 格式验证 | RawPy 0.25.1／LibRaw 0.21.4 独立解码，逐样本比较并核对内嵌预览 |

编码器没有复制固定样片、改扩展名或只伪造文件头。它避免 LibRaw 按载荷尺寸误入未压缩／packed RAW 回退分支。JPEG＋NEF 的主 JPEG 直接使用 NEF 内的同一份预览，保持拍摄信息和场景来源一致。两者来自已消费帧；JPEG 不是从 NEF RAW 重新去马赛克得到的原厂图像。

## 虚拟卡与错误处理

新卡格式为 `Z62-QEMU-media-card-C-v2`，一个快门编号对应一个照片组。JPEG＋NEF 在一次目录清单提交中发布，容量计算包括两个文件。成组删除在提交失败时回滚，文件读取核对长度和 SHA256。

新入口不会自动升级旧 v1 JPEG 目录卡，也不接受普通文件夹、外部改动、链接或越界文件名。卡满、无卡、非法模式、过期／失配场景及保存失败会显式报错。失败提交不产生可见的半组照片。异常断电后的整机／文件系统自动恢复尚未验收。

目录卡仅供 C 级媒体模型使用，不由原厂固件挂载。原厂 SD/DCIM 文件和原厂播放器互通仍未贯通。

## 独立验证

生产入口只使用项目现有 NumPy／Pillow，不依赖 RawPy。需要独立审计时使用单独环境：

```powershell
python -m venv .build/tools/raw-verify-r25
& .build/tools/raw-verify-r25/Scripts/python.exe -m pip install -r requirements-raw-verify.txt
python -X utf8 -B tools/probe_z62_media_console.py --output analysis/my-fresh-media-check
```

输出目录必须尚不存在。探测器启动并拥有一个独立 QEMU 会话，验证 JPEG＋NEF 拍摄、JPEG 独立解码、来源重放、4 倍回放、成组删除、仅 NEF 拍摄及回放；对两份 NEF 调用独立解码器，最后正常关闭并重开空卡。不会连接物理相机或写入物理盘。

已保留 原包实际流程（本地证据，未分发：`analysis/z62-raw-r25/live-media-flow-2/media-check.json`） 和早期 缺少 events 字段的失败记录（本地证据，未分发：`analysis/z62-raw-r25/live-media-flow-1/media-check.json`）。原包流程的两张 NEF 各有 1,523,084 个 RAW 样本全部匹配，内嵌预览逐字节一致。原厂 JPEG／NEF 等价、全分辨率、AF、视频及真机更新安全不在本次通过范围内。

## 格式依据和许可

- [尼康 Z7II／Z6II 官方 NEF 设置](https://onlinemanual.nikonimglib.com/z7II_z6II/en/09_menu_guide_03_09.html)：用于核对格式选项，不作为完整编码规格。
- [LibRaw 0.21.4 源码](https://github.com/LibRaw/LibRaw/tree/9646d776c7c61976080a8f2be67928df0750493e)：固定提交研究 RAW 解码、元数据识别和预览提取；没有把 LibRaw 作为生产编码器。
- 工作区 `third_party/z9-qemu/qemu/nikon-expeed-lossless.h`：仅复用 F0 格式／预测／Huffman 思路，GPL-2.0-or-later、Copyright 2026 RdWing；适配后的 Python 编码器保留 SPDX 与版权说明。没有复用 Z9 硬件地址、几何或验收结论。
- 来源与下载哈希（本地证据，未分发：`artifacts/nef-format-reference-r25b/manifest.json`） 保存资料 URL、版本、字节数和 SHA256。

原生设备与文件邮箱合同沿用 [r24 说明](README-Z62-NATIVE-SCENE.md)。其 QEMU SHA256 为 `dbe36d222dbfa633086f906f626968635c61d9825eaee8174480bef22a39abf2`，本阶段没有修改冻结设备后沿用旧 EXE。
