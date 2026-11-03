# r55 paired／MAIN／WORK 合同交叉核实

授权：仅本地源码、原始载荷和既有仿真证据的离线分析；没有设备、刷写或发布。复用固定nightglasses Z7II文档的方法，不将其VA直接当作Z62入口。

E-imports等价锚点：输入是原始裸ARM更新载荷，不是PE／ELF，无Windows IAT或动态导入表。以master含CRC SHA256 `bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4`、基址10020000、Thumb上下文和MMIO字面量引用作为来源锚点。载荷不执行、不修改；Ghidra只生成独立数据库和伪代码。

首批 `analysis/z62-ghidra/paired-video-r55/` 是参考VA候选验证，不能作Z62 setter：1036a2ac实际为MMU相关片段，1036aac2为数值运算片段，102be8a0有bad-instruction；manifest的structural audit为false。保留原失败。后续从目标自身20380000／20380488字面量及原Thumb指令重新定位。

交付是独立配置解码和明确的实现前提，不增加设备接受范围、不补IRQ／ready／软件计数。MAIN、WORK的可读RAM或非零值不证明新帧生产；所有物理像素语义仍需区分B级来源事实与C级数值假设。
