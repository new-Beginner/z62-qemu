# r20 原 copied-message SDK 的 ARM32 核心兼容性

继续原Fenestra＋自研z62qemu路线。目标是实际编译、链接及执行未修改的上游 fenestra_sdk.h / services.c / memory.c 的协议核心，保留服务消息、序列/代际/能力/错误/停止合同，不以另写插件系统替代。当前PORT仍loader-only；本轮不等于完整SDK原厂后端集成。

- 离线、无相机USB/PTP/物理卡磁盘/外部服务，不刷机、不生成Nikon更新镜像，不提交推送发布固件或密钥。
- 固定Fenestra b199dcdf及现有原两loader修改不变；实际使用文件必须逐字节匹配git原HEAD（不使用修改的module.c）。r1～r19绑定文件和失败保持；README仅追加并先冻结旧前缀。
- 使用原SDK submit/take与原fx_service_dispatch/stop/fault。上游源不删检查或改原语义；与架构无关、未引用函数仅由链接器GC节裁剪，清楚记录其不被本夹具覆盖。
- 新夹具运行于无Nikon固件的自研r13-03 QEMU。boot-image预装自有代码、复位初始化、其余核自有停机循环单列；无原厂指令/运行状态补写、无原厂RTOS/文件/菜单/MMIO绑定。不能称原厂启动/集成/镜像认证/刷入恢复通过。
- 模拟后端是显式固定错误返回及停止状态测试，不能冒称真实Nikon服务。读写/patch仅夹具自有数组，不写固件或设备内存。此阶段只核copied-message核心，不授予ARM32 AAPCS64、EL0/SIMD、原子/cache-DMA、任务同步/文件/菜单资格。
- 原 SDK 指针无关wire request/reply预计各816字节；FxServiceModule和base含指针、需独立测布局，不沿用A64 sizeof。发现native头ABI断言错误保留，不跳过或强降检查。
- 工具固定本机Zig0.13.0/Clang18.1.6、Thumb-v7/AAPCS/soft-float/integer/strict-align；整数aeabi辅助沿用已核本地源，不启NEON/未对齐宽访存。所有临时/cache用本会话D盘PI scratch，不采用guard旧C盘scratch。
- 构建输出全新.build/fenestra-z62-sdk-r20-*，SHA冻结所有实际传递头/源、配方、ELF/段/符号/镜像；上游HEAD/源码事前事后核。既有r13 EXE8DLL及完整source/recipe核，旧r69精确来源仍缺。
- 至少两自有进程，-nic none、QMP/qtest仅127.0.0.1；qtest只读邮箱结果，不写运行中客体。固定wall30秒/邮箱64KiB以内/预设全部case；失败/异常向量单独记录，不补结果或放宽case。只清理自有Popen/Q:映射；宿主退出不是相机正常关机。
- 每case独立结果由客体发布并宿主读回，核magic/版本/长度/数量/布局/预定预期/实际值/完整case索引，不只看总数。错误结果和未完成保留；两进程或主机对照不替真实原厂错误模块矩阵。

阶段门槛仍为：Q1～Q6完整候选及模型矩阵全部过，才能冻结同一镜像进入U1～U6；二阶段及独立物理恢复条件未齐不上真机。absolute_safety_verified/phase1_passed/phase2_entered/physical_gate_open保持false。

E-imports等价锚点：原SDK头的submit/take、服务分发核心调用及ELF符号/段/实际依赖，原生后端A64专用指令另列未移植。不是原厂SDK地址表。tool-index/precedent/ops技能参考缺失如前轮，只使用实际已核本地工具；报告flavor=null/severity=n/a_re。
