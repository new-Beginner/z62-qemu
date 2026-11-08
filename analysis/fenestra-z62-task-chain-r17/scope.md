# r17 同进程创建—启动—共享BX—回调首指令

仅第一阶段的局部合同观测，不是完整Fenestra端口、完整启动、业务完成或刷入验收。沿用原Fenestra路线和r13可追溯自研z62qemu，原C1.70主从、无参数/卡/控制器/候选；默认gate/sequencer/transfer-reset completion仍开，其他成功假设未关闭。

r1～r16绑定文件不改，README仅追加。r16的56份交付已逐项核长度/SHA；清单SHA06604c40f432ebe45e749510093e7ac1ef106a6c2f958a72af224ec4b8709eb3。新输出必须不存在。r17将独立读取共享入口r1起8字节，与同次创建对象前8字节及原输入回调交叉核；真实LDR后隔离执行原BX，核目标PC/ISA/参数、原目标ROM16字节/current TCB/系统寄存器，然后核原首指令及实际PUSH内存。不拼接r11/r16不同进程样本。

保留r16对象+8原STR实测快照、角色/句柄/TCB/对象/时间唯一配对、未匹配与未见启动另列。创建/启动各128、事件2048、quiet15宿主秒、wall240（允许范围仍30～300）、minimum8、目标2/3模型秒；不足/歧义/触界拒绝，不补调度、不扩界晋升。

只读有界RSP、硬件执行断点、原指令vCont;s:<CPU>、暂停/继续。禁止补写客体代码/PC/RAM/寄存器/返回值/ready，禁止注入调用/成功事件。QMP仅capabilities/qtree/status/quit。-nic none、仅127.0.0.1；无外部服务/USB/PTP/相机/物理介质/刷机。QMP退出不是正常关机。

回调首指令不是回调返回/业务完成/退出删除复用或完整ABI。r10的73待配对仍未解释；完整SDK/同步/文件/菜单/空间所有权/cache-DMA/模型真实事务与35/3F仍缺。Q1～Q6全过才进入同一冻结候选U1～U6，之后仍需物理恢复条件；目前全部阶段门槛保持关闭，不宣称绝对安全。

技能参考precedent-reverse.md/tool-index.md本地仍缺失，已实际检查；使用现有Python3.12/Capstone5.0.7及既有只读协议，不冒称IDA survey完成。裸ARM/Thumb固件无PE imports，等价证据沿用并扩展原wrapper/index1、0A、index3/PUSH/POP/共享LDR/BX与字段目标字节，不假定完整业务导入表。
