# 小红书原帖调研与 Z6II C1.70 RAW 授权离线验证

## 结论先行

通过用户已登录的小红书侧栏浏览器，读取了 5 篇相关笔记的正文和初始可见评论。最有用的线索是白菜酱 Hakusai 原帖直接给出的 **NikonUnlock** 开源项目。本次不是复述搜索摘要：已固定其源码版本，并用用户提供的 **Z6II C1.70 原始主固件**执行局部授权函数。

- 两份公开二代 KEY 均通过原始比较函数；64 个逐字节 bit0 翻转、6 个错误长度和 2 个互换 KEY 对照全部被拒绝。
- 4 组口令比较、8 组状态写入/读回实验通过，整个执行 ROM 未改变。
- 完整回归 **63 项通过，零跳过**，耗时 51.412 秒，包含实际原生 Windows QEMU 回归。
- **没有连接相机、发送 PTP 命令、刷机、提交配置或测试 RAW 外录。不能称为实机解锁成功。**
- 本次没有更新 QEMU 机器模型或生成新版本模拟器，原始 MENU 尚未运行起来。

## 1. 授权范围与方法

对象是本地用户固件和公开技术资料；不读取私信、账户设置或登录凭据，不发表评论或联系作者。原帖链接不保存临时 `xsec_token`。视频没有观看，图片没有完整检查，折叠评论没有穷尽展开，因此“未发现代码”仅指本次已读范围。

本次只在宿主内存中设置函数调用 ABI 参数、测试输入和局部 RAM，执行原始 Thumb 指令。它不是从复位启动的整机实验，也不是恢复了实际相机运行现场。没有修改原始指令、跳过 guest 分支或强制设置返回值；函数自然返回，或在声明的边界之前停止。

## 2. 原帖证据与可用性

| 原始来源 | 已读到的内容 | 本次判断 |
| --- | --- | --- |
| [borui：Z62 自定义固件/重签名](https://www.xiaohongshu.com/explore/6ad4f4e1000000002901753b) | 声称重打包、签名、更新成功，展示剩余时间修改，提到以后开源 | 是直接作者陈述，但本次已读文字没有可复现签名材料或补丁；未复现 |
| [borui：Z62 九宫格](https://www.xiaohongshu.com/explore/6ad75a52000000002901adf7) | 后续修改展示；作者可见回复表示等 QEMU 做好再开源 | 不能把展示等同于已有可移植源码 |
| [白菜酱 Hakusai：RAW/语言解锁](https://www.xiaohongshu.com/explore/6add8c58000000002c03a2f5) | 明确链接 NikonUnlock；一代有验证记录，二代 C1.70 为实验性 RAW-only | 有实际公开源码，选择进行独立本地验证 |
| [seed8/SHA-1 讨论](https://www.xiaohongshu.com/explore/6ad62c510000000026031158) | 作者提到双 EXPEED、HDMI 和 QEMU 外设仍在进行；另有 AI 账号补充解释 | 未获得可复现 seed/签名实现；AI 评论不是跨机型密钥通用的证据 |
| [技术进展汇总](https://www.xiaohongshu.com/explore/6adf182a0000000018009f6e) | 汇总、愿望和评论中的 GitHub 包线索 | 已读文字无具体仓库链接；配图截图超时，不作为技术验证依据 |

结构化来源摘要：sources.json（本地证据，未分发：`<WORKSPACE>/analysis/xiaohongshu-research/sources.json`）。登录限制已在用户登录后解除，不再列作当前阻碍。

## 3. 开源项目核对

仓库：[summershrimp/NikonUnlock](https://github.com/summershrimp/NikonUnlock)，固定提交 `edf2274143f25f3d159efeffa2bc70ef3002e34e`。

审读了该提交的 `README.zh.md`、`unlock_hdmi_raw_ii.py`、一代共用 `unlock_core.py`。二代脚本 SHA-256 为：

```text
87a042818366f9a88252d9dd4cb5124e0cab445d51fdd60f1fcb8d0698f2a1ab
```

脚本通过厂商服务命令更改功能配置，而非重打包固件。项目明确写明：

1. Z6II/Z7II C1.70 为静态分析/离线模拟支持，尚未验证二代实机、重启持久化和实际外录。
2. 二代仅提供 RAW 脚本，不提供二代语言解锁工具。
3. 二代 `HDMIARAW.KEY` 文件名比一代多一个 `A`；两份 KEY 内容也不能跨代混用。
4. 配置读回屏蔽部分字节，不是可整块恢复的完整备份。

源码下载到会话临时目录，没有导入、执行其 Python 模块，也没有生成 KEY 文件、安装 WPD 依赖或启动传输层。Git 连接曾被重置，改用固定提交的 GitHub API 和 raw 内容读取。

这里的功能授权 KEY、固件解包材料、固件重签名 K8 是不同用途，不能相互替代。功能比较函数接受某份输入，也不代表取得官方升级凭证或证明刷机安全。

## 4. 原始 Z6II 证据与局部执行

主固件 SHA-256：

```text
7b85aa96ea25d6b23481627313082476619ccb4dd3634a585de4ed896d350071
```

### 4.1 KEY 文件路径与比较函数

通过主固件原始初始化数据搬移表恢复运行时指针，再对 16 字节路径执行固件对应的逐字节取反解码，确认：

| 路径 | 原始校验入口 |
| --- | --- |
| `A:\HDMIARAW.KEY` | `0x10437D6C` |
| `A:\SRF_FUNC.KEY` | `0x10437DA0` |

原比较函数要求长度正好 32 字节，用倒序输入与 ROM 表选定字节逐一比较；这里不是声称破解了签名算法。

对公开脚本的字面常量只进行 AST 白名单解析，不使用 `eval` 或模块导入。正确输入两例返回 `1`；每份输入分别翻转各字节的 bit0，合计 64 例均返回 `0`。长度 0/31/33 的 6 例和互换 KEY 的 2 例也均返回 `0`。新增回归还检查了 bit7 翻转和极大错误长度。

### 4.2 命令表与口令检查

原始命令表位于 `0x119F5C20` 起，28 字节一项，确认 C051/C052/C101/C102 的前置校验与处理函数指针；这只是静态表核对，没有执行完整 PTP 分派链。

C102 前置逻辑在 `0x10779488` 附近比较参数，原始字面常量为 `0x28CD7EE8`。局部执行结果：

- 二代常量和 `0` 均到达此比较段的接受边界。
- 二代常量翻转一位、一代常量 `0x548B3FBA` 均进入拒绝路径，得到 `0x201D`。
- **接受比较不等于授权已完成**：在随后的文件检查之前停止，未执行文件系统或完整服务流程；零参数的其他语义不在本实验中推断。

### 4.3 状态字节写入/读回

执行原始 setter `0x103C313E` 和 getter `0x103C3114`，局部配置指针来自 ROM 中的 `0xC20D2954`：

| 选择器 | 配置相对偏移 | 请求值为 1 时写入 | 其余测试请求值 |
| --- | --- | --- | --- |
| `0x12` | `4` | `0xB2` | 0/2/255 均写入 0 |
| `0x14` | `5` | `0x6A` | 0/2/255 均写入 0 |

8 组测试中，32 字节观察区只有目标字节改变，getter 按原始逻辑读回布尔状态。setter 在进入 `0x103C221E` 同步逻辑**之前**停止，未执行同步、持久化或 F030 提交。这里的偏移是局部配置缓冲区偏移，不是建议对固件文件或相机闪存直接写入的偏移。

机器可读结果：raw-authorization-evidence.json（本地证据，未分发：`<WORKSPACE>/analysis/xiaohongshu-research/raw-authorization-evidence.json`）。

原始指令摘录：original-authorization.asm（本地证据，未分发：`<WORKSPACE>/analysis/xiaohongshu-research/original-authorization.asm`）。不保存完整 KEY 字节，只保存哈希与实验结果。

## 5. 复现与回归

工具：[analyze_raw_authorization.py](../../tools/analyze_raw_authorization.py)。测试：[test_raw_authorization.py](../../tests/test_raw_authorization.py)。在项目根目录的 Git Bash 执行：

```bash
PYTHONIOENCODING=utf-8 python tools/analyze_raw_authorization.py \
  --reference-source "$PI_SCRATCH_DIR/NikonUnlock-source/unlock_hdmi_raw_ii.py"
PYTHONIOENCODING=utf-8 Z6II_QEMU_REQUIRED=1 \
  python -m unittest discover -s tests -v
```

参考源文件需取自上述固定提交、保持原始字节；脚本先核验 SHA-256，不执行该参考代码。临时目录清理后，可重新下载同一提交文件并显式指定路径。回归测试依赖本地已准备的固件和 QEMU，但不依赖临时目录中的参考源码。

实际结果：63 项、51.412 秒、OK，零跳过。日志：tests.log（本地证据，未分发：`<WORKSPACE>/analysis/xiaohongshu-research/tests.log`）。没有改动 QEMU C 代码，因此本次不进行无关重编译或重新发布 ZIP。

## 6. 剩余限制与后续路径

- 可确认的本地结论是：原 Z6II C1.70 的这些局部函数与公开二代 KEY、口令和状态逻辑相符。无法由此推出真实 RAW 输出、录像质量、重启持久化或安全完整恢复。
- borui 的重签名和九宫格路线仍缺本次可取得的公开实现，不能凭作者陈述拼出签名/刷机流程，也不复制别机型密钥或偏移试刷。
- 原始 MENU 仍需适配已有 Z72 项目的启动、双引擎/控制器、图形和输入链。本次授权分析不解除 v0.4.0 在 `0x20016020` 的启动边界，也不是用网页重新画一个菜单。
- 当前不需要用户拆机或提供额外文档才能继续离线开发。任何未来实机写入应作为独立任务，明确确认授权、备份/恢复条件和风险后再决定。

本次必要的长期结论已写入项目原生记忆，并收到知栈回读确认；未保存完整 KEY 或登录凭据。
