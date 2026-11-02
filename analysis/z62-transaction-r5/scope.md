# Z72 图示参考与 Z62 r5 实验范围

用户提供一张称来自他人 Z72 QEMU 公开资料的架构图，要求分析并尝试推进 Z62；随后明确要求继续。图本身没有仓库 URL 或 commit，不能当作硬件规范。

## 图示中有用的界限

- MAS/SLA 私有执行环境、EX/SPI、描述符选定内存、实际事务完成与中断分开。
- 图明确写了 `natural scanout join unverified`、`natural display producer join unverified`、`original capture/save join unverified`。
- `request-only processor / bootstrap store` 的 `no execution provider` 表明请求存储不是处理器执行实现。
- 因此“有画面合成器/有NVMe接口”不能证明从传感器到取景、拍照保存已经贯通。

## 公开来源核对

本轮两次只读查询 JKWTCN/z72-qemu 得到 HEAD `8645e29393cc993ae96d31c906e01695b927f4de`，相对我们固定的 `4a7bed36b6e747f58d5ab25f31b06a31fa7c6ec2` 领先21提交、39文件变化。未更新或 checkout 本地 donor；下载仅在本会话 scratch。

| 图中标记 | 查到的公开实现 | 结论 |
|---|---|---|
| graphics actual output IRQ129 | graphics上传 IRQ129，绘制完成 IRQ130，错误 IRQ131 | 不能直接照搬标号 |
| ordinary byte-copy DMA IRQ130 | 0x20070000 两通道内存复制/填充连接 IRQ103/104 | 与图不符 |
| completed status58 read | 0x58 只读 pending 的 bit26；完成由虚拟时钟回调执行 | 读取不是执行或成功触发 |
| paired graphics LUT | nikon-gpu.h 明确说明不是 Nikon programmable LUT | 不能宣称已实现图中的LUT硬件 |
| CMOS timed DMA → IRQ94 | 当前输入帧源明确不产生 sensor pixels | 未找到图示完整链 |
| NVMe/BlockBackend | 板上实际挂载入口为 SDHCI；未找到图示 NVMe endpoint | 通用QEMU能力不等于机型已接通 |

公开源码固定链接：
- https://github.com/JKWTCN/z72-qemu/tree/8645e29393cc993ae96d31c906e01695b927f4de
- https://github.com/JKWTCN/z72-qemu/blob/8645e29393cc993ae96d31c906e01695b927f4de/qemu/nikon-z72-graphics.c
- https://github.com/JKWTCN/z72-qemu/blob/8645e29393cc993ae96d31c906e01695b927f4de/qemu/nikon-z72.c
- https://github.com/JKWTCN/z72-qemu/blob/8645e29393cc993ae96d31c906e01695b927f4de/research/z7ii/display_output.md

有限 GitHub 仓库及 fork 搜索未确认另一匹配实现；这不是证明图错误或全网无源码。图的确切来源仍需用户提供原帖/仓库链接。

## r5 的单一假设

r4原固件实跑在24.425/24.574/24.735客体秒完成三次RAW四槽写入；传感器mode寄存器20065504=8000、config20065400=10011、mask2006550C=F3，之后仍上报35/3F。原模型有mode2帧完成锁存IRQ92 bit1的入口；r4成功RAW的raw-complete未接该设备。

r5实验把**实际四槽写完后的raw-complete**连接到同engine传感器的专用输入。仅显式functional-raw-completion开启、mode2原谓词成立且mask bit1开启时锁存20065508 bit1，走原设备中断更新。状态已pending时合并，不强造新边沿；重复high不重发；失败DMA、单纯配置写或时钟推进不产生成功事件。

这属于transaction-linked功能性假设，不是已恢复芯片时序，也不预设能解决上层mask8等待。保留原init one-shot，禁止与旧laboratory-frame-completion同时开启；不补软件event8，不改固件指令、PC、返回值、错误列表或应用索引。

## 验收与保护

- 独立r5目录、manifest、入口，保留r4源码/runtime和正在8672运行的用户展示；测试只关闭自己创建的实例。
- 新开关默认关闭，启用要求同时真实RAW；合成packing仍未硬件验证。
- 先无固件qtest验证数据/事件/IRQ正反例，再原C1.70未加断点A/B：相同init-mode/RAW/按键，只改完成桥开关。
- 健康循环仍需完整空固件状态列表、退出/重开/导航。像素变化和计数增加不等同于通过。
- 本轮不接实机、不发PTP、不刷机、不写真实卡、不提交推送；不移植图示IRQ94、NVMe或假定ISP已实现。
