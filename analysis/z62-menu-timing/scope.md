# Z62 MENU时序对照范围

- 目标：区分无按键后台错误与MENU触发采集停止错误；读取等待原始返回码。
- 授权：用户要求自主执行已讨论的QEMU/离线逆向方案。此实验不访问物理USB，不刷机、不改原固件/guest软件状态，不发布或提交。
- 输入：Z6II C1.70完整主成员SHA256 bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4；r1 QEMU SHA256 e169431ed0a24dded62c2d3e0ea2aba1056385ec96584c57b40cd4e5ab29fba4。
- 配置：固定Z62来源4f4389944fc339d107f22f5f7ca3f90cc34b78de，合成参数，sampling关闭，无SD卡，main-screen关闭，捕获边界注入0；frame-sync按原参考环境开启。
- 对照：auto-menu关闭，首次普通pin9输入分别在虚拟时间>=3和>=20秒；之后普通down/exit/reopen。
- 观测：QMP主核虚拟地址只读HMP x；状态列表C253E0C0、pending C181DAE8、应用管理器及MMIO。单份观测跨多个读请求，非原子；轮询只能限定首次错误出现区间，不能证明精确首次指令时间。
- 图像/运行日志：artifacts/z62-menu-timing-20261028/；分析脚本tools/probe_z62_menu_timing.py。独立临时stage保留原输入/生成fixture，不含于发布。
- imports等价：裸ARM/Thumb固件，非PE/ELF，无传统导入表；以固定固件哈希、原始调用点、状态谓词及MMIO为证据锚点。
- 后续若用RSP断点，仅暂停/继续及读寄存器/内存；结束移除断点、detach。时序结论以无断点组对照，不把调试暂停算作客体超时原因。
