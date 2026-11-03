# 构建、输入和运行

本仓库是源码快照。以下使用已验证工程的**原生 Windows Python + MSYS2 UCRT64** 路线；不宣称完整 Linux/macOS 构建和相机行为已验收。原本地构建已存在并验证，本次公开没有在空机器重建全部历史内核。

建议使用 ASCII 的 D 盘工作路径（如 `D:/camera-lab/z62-qemu`），所有新缓存、TEMP/TMP、工具链和运行文件放在项目目录。历史构建为保护证据保留多个独立源码/编译目录，完整链可能需要数十 GB；单个后续构建器还要求至少 12 GiB 空闲。已有或失败目录不会自动删除/覆盖。

## 2026-11-03 当前路线

当前为 r69 内核、r75 交互控制台、r85 研究快照。下文 r24/r48 是仍保留的历史路线；不是最新内核已经在空机器重新构建的声明。新克隆需自己准备固件、工具链及父构建。

在后文 r48 基础上，源中当前父依赖顺序为：

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_grid_geometry.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_photo_results.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_video_isp.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_video_isp_format.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_statistics_observe.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_raw_stop_control.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_mmio_filter.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_paired_ingress.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_paired_handoff.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_output_lineage.py --jobs 4
```

它们对应源码依赖，不要求编译不存在的 r75/r85 内核。本次发布没有重新运行整条构建链。宿主/观察器可能严格绑定历史源、输入和 EXE SHA；不同工具链的 fresh build 需要明确的新验收绑定，不能删除 guard 冒充原窗口。

构建和原厂输入准备好后，使用已安装依赖的 Python；r75 的永久宿主诊断还要求现有的 **Windows host GDB**。若默认路径不适用，显式传入本机实际 GDB 路径，例如项目内 MSYS2/UCRT64 的 gdb.exe：

```powershell
.venv/Scripts/Activate.ps1
./start-z6ii-workspace.cmd --host-gdb .runtime/tools/msys2/ucrt64/bin/gdb.exe --group23-fixture artifacts/fixtures/group23.bin --sd-card artifacts/fixtures/card.raw --software-card artifacts/my-photo-card
```

在克隆后先设置 `$env:TEMP`、`$env:TMP`、`$env:PIP_CACHE_DIR` 到项目 `.runtime` 子目录；详见 [工作目录存储说明](profiles/README-WORKSPACE-STORAGE.md)。Q: 必须空闲或已映射到此项目；不会覆盖另一个盘符映射。历史 r4/r24/r48 构建说明继续保留，单纯复制旧 CMD 不能提供编译缓存或合法固件。

## 1. 克隆与 Python

```powershell
git clone --recurse-submodules https://github.com/new-Beginner/z62-qemu.git
cd z62-qemu
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-raw-verify.txt -r requirements-video.txt
```

五个子模块的提交由 Gitlink 固定，见 [参考](REFERENCES.md)。Z62 使用可取得相同 R3 的公开副本；不要把 `main` 或随意的“最新版本”替代为固定 R3。原作者署名仍保留。

若只检查源码和软件媒体子集，可先初始化 `third_party/nikon-fw-key-tool`；完整构建/研究需要其余相关子模块，尤其 `nikon-firmware-tools` 的 `Nikon-Patch-JS/src/nikon_patch/xor.c` 和 Z62/Z72 donor。

```powershell
git submodule update --init third_party/nikon-fw-key-tool
```

纯 Python 依赖版本已固定在 requirements。PyAV 是 C 级视频后端，RawPy/LibRaw 用于独立 NEF 验证，不是原厂编码器。

## 2. MSYS2 与 QEMU 源码

安装 MSYS2 UCRT64 的 GCC/toolchain、binutils、pkgconf、GLib、Pixman、libfdt/dtc、zlib、Meson/Ninja、Python 等 QEMU 构建依赖。构建器检查它们已存在，不自动安装系统工具。后续例子假定目录为 `D:/camera-lab/z62-qemu/.runtime/tools/msys2`，请替换为自己的安装位置。

QEMU 固定为 **10.2.4**：

- 官方源码：[qemu-10.2.4.tar.xz](https://download.qemu.org/qemu-10.2.4.tar.xz)
- SHA256：`821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746`
- 缓存位置：`.build/downloads/qemu-10.2.4.tar.xz`

可以手工将官方包放到该缓存位置；各构建器会检查哈希。也可运行早期基线构建器，它会下载并核验，同时编译独立 v0.4 基线：

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/build_qemu.py --msys-root D:/camera-lab/z62-qemu/.runtime/tools/msys2 --jobs 4
```

这个早期 `nikon-z6ii` 基线不是后面的完整 Z62 donor 配置，不能把它的成功替代 r24/r48。

## 3. 按依赖构建独立内核

以下顺序来自现有构建器的父 manifest 依赖。**交互路线构建到 r24 即可；研究路线继续到 r48。** 不需要将每个宿主/观察编号都当成新内核，也不要求先编译一个 Z72 runtime。

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_functional.py --msys2-dir D:/camera-lab/z62-qemu/.runtime/tools/msys2 --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_transaction.py --msys2-dir D:/camera-lab/z62-qemu/.runtime/tools/msys2 --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_capcom.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_raw_stream.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_finite_stats.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_preview.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_capture_contacts.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_raw_boundary.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_continuous_stats.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_analog_input.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_scene_source.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_scene_file.py --jobs 4
```

上面依次生成 r4/r5/r6/r7/r8/r9/r13/r17/r18/r21/r23a/r24。各步保留独立源码与 manifest；命令/工作目录不应擅自改到旧树内部。

研究路线：

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_preview_results.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_preview_results_format.py --jobs 4
.venv/Scripts/python.exe -X utf8 -B tools/build_z62_grid.py --jobs 4
```

生成 r47/r47b/r48。初版 r47 对后续格式的拒绝作为历史边界保留，r47b 是对应修订；r49 没有单独的 QEMU EXE。

编译器/依赖不同可能产生不同 EXE SHA。应以自己的构建 manifest 和源码身份校验为准，历史 EXE SHA 用于识别本地验收对象，不要求其他机器字节相同。不要删 manifest 或跳过校验来“修复”启动。

## 4. 原厂与候选输入

用户自行取得 Z6II C1.70 原包；本工程固定输入 SHA：

`5a9640b4c07abe1ecbf5a52655cbec6b893bba045bb2a1a1d21055b9f8f9d06d`

默认文件名为仓库根目录的 `Z6_2_0170 (1).bin`。可以把自己合法取得的相同包放在这里，或对提取工具显式传 `--input`。它已被 Git 忽略。

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/prepare_firmware.py --input "Z6_2_0170 (1).bin"
.venv/Scripts/python.exe -X utf8 -B tools/prepare_reference_firmware.py z62 --input "Z6_2_0170 (1).bin"
```

第一条生成早期 payload，第二条保留三个 reference 成员的 CRC trailer。哈希/CRC 不等于密码学签名验证，也不补齐 ROM/NOR。

候选入口可显式传 `--firmware 候选包路径`，只支持已核对的 C1.70 容器布局、边界和 CRC。原包也可走候选分支，但这只能证明加载路线，不是所有修改都正确。完整健康状态继续可能是 unknown。

## 5. 交互场景、照片、NEF 与异步软件录像

构建至 r24，准备输入并使当前 `python` 指向已装依赖的环境后：

```powershell
.venv/Scripts/Activate.ps1
./start-z6ii-async-video.cmd
```

打开 `http://127.0.0.1:8684`。专用软件媒体目录卡在 `artifacts/z62-async-video-card-r27`。启动 CMD 的实验参数是合成参数，不是个体标定。原厂 LCD 取景与 C 媒体操作的实现层级在界面/文档中分开。

使用场景/软件曝光和手动镜头、拍照格式、列表回放/缩放/删除；软件模式切视频后开始录像，停止后等待真实 worker 退出、媒体/来源审计和卡提交。进度时间是宿主等待时间，不是影片时长。保存完成后再回放/导出。

详见 [r27 操作与限制](profiles/README-Z62-ASYNC-VIDEO.md)。原有 `start-z6ii-qemu.cmd` 是不同机身/采集研究入口（8675），不是自动升级的完整媒体主入口。

## 6. r48/r49 研究复现

先构建至 r48，并在 ASCII 路径创建普通卡与明确的合成 group23：

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/z62_virtual_sd.py --create artifacts/fixtures/card.raw --size-mib 4096
.venv/Scripts/python.exe -X utf8 -B tools/create_z62_group23.py --output artifacts/fixtures/group23.bin
```

group23 是 E0000 字节零体加 ENDM，SHA `c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700`，**不是相机标定**。工具不覆盖已有文件，不访问设备命名空间或物理卡。

```powershell
.venv/Scripts/python.exe -X utf8 -B tools/probe_z62_grid.py --output analysis/my-grid-native.json
.venv/Scripts/python.exe -X utf8 -B tools/trace_z62_grid_delivery.py --output analysis/my-grid-delivery --card artifacts/fixtures/card.raw --group23 artifacts/fixtures/group23.bin --duration 12
.venv/Scripts/python.exe -X utf8 -B tools/trace_z62_grid_lifecycle.py --output analysis/my-grid-lifecycle --card artifacts/fixtures/card.raw --group23 artifacts/fixtures/group23.bin --duration 55
```

输出必须是新文件/目录。最后一条本次记录为“观察完成、恢复失败”；CLI exit0 不等于恢复通过，请看 `assessment.recovery_observed`。卡使用 snapshot；不要改成真实相机或宿主物理盘。

更多严格原生数值、IRQ 和旧版本命令在 [r48 说明](profiles/README-Z62-GRID.md)。这些命令会执行固定原厂代码，耗时可能较长；它们不是新克隆后不准备输入就能运行的纯源码测试。
