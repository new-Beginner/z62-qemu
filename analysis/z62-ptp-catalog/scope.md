# 有界离线任务范围

- 输入：`artifacts/z62-reference-1.70/master.bin`，完整主成员 38,750,138 字节，BASE `0x10020000`，SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4`。
- 输入：`analysis/camera-usb/device-info-rw-20261028-162139.json`，SHA256 `88f4618b7c2b1a07c7542de724c488f7d3aa733df6d02dbdbafd855af05c0f83`。它是历史记录，不是本次实机结果。
- 仅新建指定分析脚本、对应测试及本目录的范围、报告、JSON 证据。无 CSV、临时固件副本、密钥或其他交付文件。
- 禁止 USB/相机/WPD、未知 opcode 发送、固件修改、提交/推送、RAW 解锁脚本执行或密钥保存；本次均未进行。
- 已阅读本地 `<USERPROFILE>/.agents/skills/ida-reverse/SKILL.md`，参考其静态交叉引用思路；受本任务离线/写入范围约束，不启动其 IDA 服务或 bootstrap。使用已安装 Python 与 Capstone 5.0.7，不安装工具。
- 只恢复四张具有真实消费者引用的表及 13 个明确代码窗口。表外同值整数、疑似其他布局不自动成为操作。
- 能力来源分为 operations/events/properties；固件私有操作表与历史公布能力分开记录。C101/C102 数值碰撞不能跨命名空间合并。
- 证据等级：原字节/表记录/直接分支/literal 引用为静态证据；BLX/BX 寄存器目标即便可给出初始化候选，也不等于运行时调用已验证。
- 读取候选只给函数及已见 RAM 写入/间接调用边界，不宣称安全、只读或不存在持久副作用。未恢复事件及属性自己的固件分发表。
- 单元测试的损坏输入只在 Python 内存中构造，绝不写回固件。

## 验证记录

- `python -B tools/analyze_z62_ptp_catalog.py`：通过；输出 97 操作、27 事件、21 属性、4 表、276 条记录，匹配 97/97 操作。
- `python -B -m unittest discover -s tests -p test_z62_ptp_catalog.py -v`：12/12 通过（0.102 秒）。覆盖输入哈希拒绝、命名空间隔离、全部映射、锚点、终止记录、literal、直接与间接调用、RAM context、表外同值整数反例。
- 无实机验证。完整固件控制流、其他表、后端持久写入及所有运行时权限条件均不在本次验证结论内。
