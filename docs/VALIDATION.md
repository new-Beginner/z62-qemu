# 验证与公开证据

## r98 本次公开副本检查（2026-11-04）

实际执行**35模块、143项无固件测试，0失败／错误／跳过**；GCC16.2.0以C11／O2／Wall／Wextra／Werror／pedantic编译并通过**16个C case**（8像素、3 MAIN、5 transfer，单独计数）。同时核对962个导出文件SHA、635份Python内存编译、本地Markdown链接、被排除产物和凭据形态；819个未转换导出文件另与研究目录逐字节核对，零差异。结果见[JSON](../analysis/publication/source-check-r98-20261104-1.json)和[日志](../analysis/publication/source-check-r98-20261104-1.log)。

```powershell
python -X utf8 -B tools/check_public_source.py --output analysis/publication/my-r98-check.json --native-compiler .runtime/tools/msys2/ucrt64/bin/gcc.exe
```

使用已有Python依赖、Node与实际GCC位置，工作目录为ASCII路径或已核对别名，TEMP／TMP留在项目内。新增虚拟参数完整性与原时钟资格9项；MAIN stream测试另属本地Q:别名环境，没有悄悄计入公共可移植子集。此次公开检查没有加载固件、启动QEMU、重跑715项或RawPy／LibRaw；原厂与native设备结果属于下节独立证据。最终文档回写后只重核静态清单／链接／差异，不重复计为运行143项。

## r98 本地实现与原厂窗口（2026-11-04）

本次新增r92–r98，默认仍r75界面／r69内核。已有完整本地回归为**715项、0失败／错误／跳过，187.344秒**；其完整日志和源绑定在本地留存，没有RawPy，不称新一轮LibRaw验证。r98原生4个进程exit0，两输入／122次DMA／93,696字节独立重算通过；旧finite原生回归通过。

本次继续等待既有16秒原厂探针至真实终态，实际运行`verify_z62_retained_finite.py`：原厂122次采样／2批／0拒绝，两批同publication33／frame61；每批保存一份768B scalar，总1,536B从保留packed12和冻结LUT重算零差异。CPU0 bit7 ACK写7次，不称7批。原厂3个成员及输入卡未变，进程exit0。verifier归档24份源／生成源／构建元数据，原厂窗口归档7份。

最终LCD已人工查看，出现`Error. Turn camera off and then on again.`，preview0、CW未恢复。`LCD_all_black=false`仅指非黑像素，不能称预览／相机成功。完整摄影、AF和刷机安全保持false。摘要见[r98证据](evidence/retained-finite-r98.json)，原件身份见[哈希索引](evidence-index-20261104.json)，失败及复现见[r96–r98报告](history/2026-11-04_实施-Z62连续供帧与保留帧有限采样r96-r98-report.md)。

下面r91和r86公开检查为历史范围；本次r98公开副本检查单独记录，不把本地715项混计进无固件子集。

## r91 本次公开副本验证（2026-11-04）

本次发布新增 r87–r91 源码，默认仍为 r69 内核／r75 界面。独立公开副本实际执行 **33 模块、134 项无固件测试，零失败／错误／跳过**；以 GCC 16.2.0、C11、O2、Wall、Wextra、Werror、pedantic 编译公开头文件及探针，**16 个 C case 全部通过**：8 个像素、3 个 MAIN 解析／生命周期／拒绝、5 个 transfer 量化／无损 RAW16／未知码拒绝。C case 独立于 134 项计数。结果见 [JSON](../analysis/publication/source-check-r91-20261104-1.json) 和 [完整日志](../analysis/publication/source-check-r91-20261104-1.log)。

同时通过 902 个导出文件 SHA、593 份 Python 内存编译、本地 Markdown 链接、被排除产物及凭据形态检查。767 个未转换导出文件另与研究目录字节核对，零差异。最终文档和导出清单回写后另做静态核验，不将其计为再次运行测试。Git 差异检查按仓库保留原始 CRLF 的约定使用 `git -c core.whitespace=cr-at-eol diff --check`。

```powershell
python -X utf8 -B tools/check_public_source.py --output analysis/publication/my-r91-check.json --native-compiler .runtime/tools/msys2/ucrt64/bin/gcc.exe
```

需要已有 Python 依赖、Node 和实际 GCC 路径，使用 ASCII 克隆路径；所有 TEMP／TMP 指向工作目录内 `.runtime/tmp`，输出必须用新文件名。实际借用了已有依赖环境，没有在空机器重建。该检查没有启动 QEMU、加载固件、连接相机、重跑本地 701 项、重新验证全部 9,138,504 样本或重跑 LibRaw；RawPy 未安装。

[r91 选定摘要](evidence/capturework-original-r91.json)来自已有原厂实验及本地完整回归，原件哈希见 [索引](evidence-index-20261104.json)。导出时实际核对原厂窗口、数值复核与回归记录的 SHA 绑定。13 次 DMA／CPU ACK 仅适用于该 8.003 秒受控执行窗口；统计／预览为 0、LCD 全黑。它不是新克隆检查的产物，不是原厂摄影、AF 或刷写安全验收。历史摘要中的发布状态按当时记录保存，当前版本以 README 为准。

## r86 本次公开副本验证（2026-11-04）

运行基线仍为r69内核／r75界面，r86只新增独立C像素核心。独立公开副本实际执行 **32模块、131项无固件测试，零失败／错误／跳过**，另以GCC 16.2.0／C11／O2／Wall／Wextra／Werror／pedantic编译公开核心并执行 **8个native C case全部通过**。检查862个导出文件哈希、573份Python内存编译、Markdown链接及被排除产物／凭据形态均通过。结果见[本次JSON](../analysis/publication/source-check-20261104-1.json)和[测试日志](../analysis/publication/source-check-20261104-1.log)。

native检查直接使用公开头文件和probe，不读取私有relocation manifest，不依赖原`.build`内核。它与32模块计数分开，未重复计入131项。实际借用既有Python依赖环境，没有在空机器重建；RawPy未安装，未重跑LibRaw独立解码、完整历史635项、QEMU或原厂固件窗口。

```powershell
python -X utf8 -B tools/check_public_source.py --output analysis/publication/my-r86-check.json --native-compiler .runtime/tools/msys2/ucrt64/bin/gcc.exe
```

须在ASCII路径的公开克隆根目录使用现有GCC和Python依赖，输出用新文件名；所有临时文件在克隆`.runtime/tmp`。编译／运行失败会保留状态，stderr使用可保留异常字节的信息解码。最终文档和导出清单变更后另做哈希／语法／链接核验，不冒充又重跑整套测试。

r86全1,523,084像素的独立C／NumPy验证发生于本地数值case；见[选定摘要](evidence/capturework-pixels-r86.json)和[原件哈希索引](evidence-index-20261104.json)。MAIN是合成梯度、几何／LUT来自只读快照；QEMU设备集成、来源／commit、硅片等价及AF均false。摘要不分发原始RAM、RAW输出或完整轨迹。

## 四种证据不要混用

1. **源码/宿主单测**：验证解析、数值、文件事务、输入封装、后台任务和观察器合同。不能单独证明原厂流程。
2. **无固件原生 QEMU 检查**：验证真实设备内存、DMA、IRQ、W1C、屏蔽/背压、取消、复位与错误数据拒绝。
3. **固定原厂固件运行**：验证固件自己提交、消费、回调/发布及应用状态；断点会扰动时序。
4. **实际界面/媒体独立检查**：原厂 LCD、JPEG/NEF/视频解码、逐样本或逐帧来源/时间/颜色审计。截图或文件存在不能独立代替前面各层。

## 历史记录

上一公开快照为2026-11-03/r85，r69阶段最近一次历史全量为635项。此后仅做新增专项、原生检查及实际窗口；下面保留历史范围，本次发布没有在新克隆中重跑635项或全固件链。

当时的 `check_public_source.py` 增加提交来源状态、r75 JavaScript状态迁移、队列/等待/内核CB观察器等无固件子集。需要Node以执行实际JS状态检查；不加载固件、不启动QEMU或连接相机。**32个模块、131项测试全部通过，0失败/错误/跳过**；850个导出文件哈希、567份Python内存编译及Markdown链接通过。见 [r85源码结果](../analysis/publication/source-check-20261103-2.json) 和 [日志](../analysis/publication/source-check-20261103-2.log)。下面98项为更早公开提交的历史记录，不冒充r86本次计数。

首次源码检查因文档提前链接尚未生成的结果文件而停止，尚未运行测试，失败记录保留在 `analysis/publication/source-check-20261103.json`。取得实际结果后更新了链接，随后单独复核最终文档/哈希，不反复重跑同一套测试。当前借用既有Python依赖环境，没有在空系统重建全部依赖和历史内核，也没有RawPy独立解码。

最近内核事件的 [公开验收摘要](evidence/latest-kernel-events.json) 只分发选定字段；原始完整轨迹未分发。[本次证据索引](evidence-index-20261103.json)记录其原件SHA。r83失败、同VM恢复、r84/r85成功的有界观察分别保留，断点窗口功能资格仍false。

| 阶段 | 已有记录 | 适用范围 |
|---|---|---|
| r27 | 438项通过的当次摘要；缺完整全量 stdout 已注明 | 异步 C 视频及当时回归；不称原厂视频完成 |
| r47b | 524项、原生设备检查和原厂逐单元结果观察 | 有限预览配方 |
| r48 | 530项、原生/父模型检查、19,200样本、5次目标等待成功 | 初始配置软件 ISP/硬件通知，不覆盖新视频配方 |
| r49 | 534项/184.194秒、完整测试日志；55.051秒原厂观察 | 观察完成但恢复失败，初始5次成功与切换后19次超时分别记录 |

原始完整环境包含合法固件、本机独立构建、上游源树和实验输入。**本仓库不把旧环境的534项通过称为新克隆无条件可运行。** 多个原测试依赖这些文件；缺依赖产生的跳过也不能作为通过。

## 新源码目录可运行的检查

安装根目录依赖，并初始化 `third_party/nikon-fw-key-tool` 后：

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/check_public_source.py --output analysis/publication/my-source-check.json
```

这个明确列出的子集不加载固件、不启动相机、不依赖原 `.build` 内核缓存。它检查公开文件哈希、Python 编译、Markdown本地链接、被排除产物/凭据形态，以及场景/媒体/视频/网格/观察器等源码测试。结果记录实际执行数、依赖版本、失败/错误/跳过；有任何跳过不会标为完成。

本次独立发布目录实际结果：**20个模块、98项测试通过，0失败/错误/跳过**；746个导出文件哈希、382个Python文件内存编译及本地文档链接检查通过。见 [实际结果](../analysis/publication/source-check-1.json) 和 [完整日志](../analysis/publication/source-check-1.log)。这是独立源码目录中的测试，借用现有的 Python 依赖环境；没有宣称新建空系统或重编全部历史内核。

该环境包含 NumPy 2.4.1、Pillow 12.2.0、Capstone 5.0.7、Unicorn 2.1.4、PyAV 19.0.2，**没有 RawPy**。因此这98项不能被描述成重跑 LibRaw/RawPy 独立解码；NEF 独立逐样本验证仍是 r25 的历史证据，单独环境要求见 `requirements-raw-verify.txt`。

新增 group23 输入生成工具另经实际运行验证长度、ENDM、完整 SHA，并确认拒绝覆盖已存在文件；只产生本地合成夹具。

它不是全量534项，也不证明双向切换、原厂拍照或AF。模块列表保存在脚本与结果中，不隐瞒测试选择。

## 原生与原厂复现

准备完整构建和合法输入后，遵循 [BUILD](BUILD.md) 的新输出路径示例。实际原厂观察可能较慢，退出必须确认自有进程正常结束。不要因读取超时重启实验或自动重发控制。

新设备需要实际源数据供给、全部输出和失败路径；不能只看“完成”位。原厂等待按线程、SP和操作身份配对，窗口末尾未返回保留为未完成。

## 哪些证据公开了

- 全部阶段报告、当前能力/难点/过程、源码和测试。
- 选取的原生检查、媒体审计、回归、摘要、身份清单与范围记录。
- r49四张明确来自合成场景的原厂LCD，及完整观察 stdout、紧凑 lifecycle 记录。
- 本地原始证据的路径、大小和 SHA：[evidence-index.json](evidence-index.json)。它是索引，不是下载原始内容。

大型原始 trace、固件/卡/媒体原件、反汇编或 NKN 恢复包未分发。历史文档中的相应链接转为“本地证据，未分发”文字。源码字节保留；文档和部分 JSON 的个人路径被替换，原始与公开副本 SHA 在 [publication-manifest](../publication-manifest.json) 中分别记录，不能拿公开副本哈希冒充原件。

引用结果时应同时写明版本、A/B/C/D层级、输入、开关、验证窗口和未通过项。完整系统和实机更新安全保持未验收。
