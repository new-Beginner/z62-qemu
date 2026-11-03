# Z62 已完成输出的来源记录 r69

r69 为软件 ISP 的实际输出增加只读来源记录。它用于判断 C 级照片或录像采用了哪个场景输入，以及当前设置是否已到达输出端。独立交互入口 r71 仍在验收；默认启动入口没有升级。

## 当前边界

| 能力 | 本轮证据 | 限制 |
|---|---|---|
| 照片／视频实际输出来源 | 原生检查（本地证据，未分发：`analysis/z62-output-lineage-r69/native-1.json`）通过 | 设备输入到 C ISP 输出的来源，不是硅片协议或逐像素身份认证 |
| 发布与实际输出区分 | 发布、RAW成功而ISP拒绝、背压等检查通过 | 不把发布ID、寄存器形状或消费计数当作输出成功 |
| 原 RAW／新 paired 来源 | 旧 paired 回归（本地证据，未分发：`analysis/z62-output-lineage-r69/paired-regression-1.json`）通过 | 受支持配方内的 C 模型；原厂统计恢复仍未完成 |
| JPEG＋NEF 成组存卡 | 实际HTTP检查（本地证据，未分发：`analysis/z62-paired-console-r71/http-2/result.json`）含照片验证 | JPEG 640×424；NEF 1514×1006、12有效位存入14位，非原厂全分辨率 |
| 拍照后切视频 | 同一HTTP检查失败，输出仍为photo | 输入读回成功不能证明原厂应用完成切换；未将此路径标为通过 |
| 未按全快门先切视频 | 独立对照（本地证据，未分发：`analysis/z62-paired-console-r71/selector-before-shutter-1/result.json`）通过 | 21.017秒虚拟时间确认；不能据此宣称拍照后的切换也通过 |
| 新来源上的C录像与回放 | 实际录像（本地证据，未分发：`analysis/z62-paired-console-r71/recording-1/result.json`）保存、解码、逐帧来源及视频回放通过 | 仅9帧／0.296543秒；返回照片观察（本地证据，未分发：`analysis/z62-paired-console-r71/recording-2/result.json`）失败，完整流程仍未通过 |
| AF、原厂编码、刷写安全 | 未完成 | 本版本不能证明固件可安全刷入实机 |

## 构建与运行

固定核心 QEMU 10.2.4。r69 EXE：`.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe`。

SHA256：`37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9`。

26层身份、VMState55及七份生成源见构建清单（本地证据，未分发：`.build/z62-output-lineage-2026.11.03-r69/output-lineage-build-manifest.json`）。父 r66 EXE 和所有既有绑定源保持。新私有工具链的139个包另存锁；GCC16.2.0、GLib2.90.1、Python3.14.10及DLL与旧工具链不同，不宣称二进制等价。

从项目根运行独立控制台：

用户现已要求所有产物存入工作目录，请使用[工作目录存储入口](README-WORKSPACE-STORAGE.md)，不要再裸运行旧的系统临时目录命令。启动脚本已加入存储包装，原内核选择保持。

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/run_z62_workspace.py --entry run_z62_paired_console --port 8685
```

默认使用新的 `artifacts/z62-paired-card-r71` 目录卡；可用 `--software-card` 指定另一张新卡。固件虚拟SD使用专用镜像的快照，目录卡为软件媒体后端，两者没有原厂DCIM互通。

入口核对 r69 完整身份，只在新ASCII临时staging生成控制台。显式使用 `<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin`，SHA256 `c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700`。这是合成实验配置，没有恢复真实个体NOR或标定。支持通过 `--group23-fixture` 指向相同字节的其他位置。

构建产物已完成后不能原地续建。`--resume`仅用于同一 r69 未完成准备树，会逐文件核对准备源及实际安装包版本。以后修改设备实现应使用新版本和独立构建目录。

## 接口与确认规则

开启属性：`nikon-z72-boot-config.z62-output-lineage=on`，要求显式 paired 输入和预览结果配置；默认关闭。

主引擎 boot-config 的 `paired-output-lineage` 是原子读取的JSON字符串，只读。交互层先解析 `schema`、类型、来源和标签，再从自己持有的场景帧中匹配。

| 字段 | 含义 |
|---|---|
| `enabled`／`valid` | 功能是否启用；最近输出能否归属到已知输入 |
| `commits` | 实际输出提交累计数；无效来源的实际提交也会增加 |
| `mode` | 提交时照片／视频模式，不是随后读到的当前配置 |
| `source` | `legacy-raw-stream`、`software-paired`或`unknown` |
| `sequence` | 输出使用的来源序号 |
| `epoch`／`publish_id`／`frame_id`／`time_ns` | 不可混用的四个来源标签 |
| `scope` | 固定 `device-input-to-software-isp-output` |
| `pixel_identity_proven` | 固定false；来源可追溯不代表输出与原RGB逐像素相同 |

视频标签跟随模型私有的不可变RAW cohort；照片直接读取客体RAW，若提交时来源已不一致则拒绝归属。记录不增加IRQ、客体完成位或调度，不改变像素计算和接受条件。

交互入口经扩展器bit0交付持续选择值，保持其余23位，且不加入瞬时按键／watchdog集合。模式切换分两阶段：先观察目标模式的实际输出，再发布该模式和当前设置的新帧并等待其提交。超时、未知交付和陈旧输出都不能变成ready。实体拨杆身份仍未确认。

照片与录像使用匹配提交标签的外部RGB源帧进行 C 编码，并附带输出来源；没有把这些RGB字节说成原厂ISP输出字节。参数修订和帧年龄也必须通过。尚未满足条件时，启动拍摄应拒绝；停止和取消录像保持可用。

## 验证

```powershell
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_output_lineage.py --output analysis/z62-output-lineage-r69/native-new.json
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B -m unittest discover -s tests
```

HTTP整链检查会操作专用空测试卡、保存下载副本、独立解码，并在回放检查后删除自己刚生成的照片组。只能对为本检查新建的卡运行；输出目录必须不存在。

```powershell
& '.build/tools/raw-verify-r25/Scripts/python.exe' -X utf8 -B tools/probe_z62_paired_console.py --url http://127.0.0.1:8685 --output analysis/z62-paired-console-r71/http-new
```

验证进程使用 RawPy/LibRaw 环境，控制台使用 PyAV 视频环境。`--resume-missing-decoder`仅接续已记录的缺RawPy失败，会核对既有照片、事件与下载SHA，不重放快门。`--selector-only`用于空卡上“未按全快门先切视频”的对照，不代表整条照片／录像／回放通过。

本轮失败和已有通过同时保留；完整结果见[阶段报告](../history/2026-11-03_实施-Z62输出来源与独立交互r69-r71-report.md)。

已通过的设备门槛、媒体字节及会话副本可用 `tools/verify_z62_output_lineage_evidence.py --output 新文件.json`复核。该工具检查证据一致性，输出明确保留 `interactive_full_flow_verified=false`，不是另一次整机运行。
