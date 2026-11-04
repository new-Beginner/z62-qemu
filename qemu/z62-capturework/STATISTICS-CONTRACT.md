# r92 CaptureWork 到连续统计的显式来源接口

此模块是默认关闭的 C 级量化线性视图＋有限设备数据交付，不是原厂 ISP 或真实 PDAF。独立构建在 r91 源码上，默认 r75 界面／r69 内核保持。本合同描述实现；实际通过范围以阶段报告和运行回执为准。

## 资格与数据域

需同时启用 `nikon-z72-input-config.z62-capturework`、`functional-continuous-stats` 和 `z62-capturework-statistics`。原厂观察另显式启用外部 MAIN 的 `z62-capturework-policy0`。仅覆盖当前 `1514×1006`、stride 2272 的统计输入配方，不扩展旧统计几何或五路描述符。

worker 在私有输入及冻结 transfer 上完成原有编码 RAW；以 r88 的 C 解码得到 linear16 的量化代表值，再通过无 LUT／同尺寸的 C 像素核心打包为独立 linear12 视图。LUT8 对应区间 `[i*256,i*256+255]` 的代表值为 `i*256+128`，线性12位值为 `i*16+8`。这是量化近似，不恢复低8位，不把编码 RAW 直接送给假定线性的统计算子。

只有原有编码 RAW 的所有有效行都实际 DMA 成功，设备才接纳该私有视图及 epoch、publication、frame、虚拟时间、generation、bank、slot、地址与 transfer。客体编码 RAW 保持原样，`raw_accepted`、`raw_stream_frames` 和旧统计 seen-RAW 计数不增加。不能用计数伪装数据来源。

## 所有权与完成

- 一次最多保留一个待消费视图；待消费时拒绝新 MAIN 文件，且 CW admission 不开始下一任务。
- 连续统计保留原有 enable、边沿、commit、profile、geometry、RAM、输出重叠、六槽和 W1C 资格。原有统计时钟消费新视图，未产生额外软件 ready 或伪造 IRQ。
- 五路输出全部实际 DMA 后，才记录视图已消费，随后执行原有统计槽来源信号、事件101和六槽完成通知。
- 未确认的 `20068270 & 0xa0` 仍背压；部分／无 ACK 不产生下一槽结果。重复时钟不能重复消费同一 publication。
- CW 停止／取消／配置代次变化、统计 enable 变化和 reset 使缓存失效。worker 只持有自己的输入及结果，不可访问或改写客体软件状态。
- 默认关闭时，原有 RAW 来源门控和处理路径保持。启用 CW 时仍阻止迁移／完整快照；不宣称已穷尽 inflight 取消竞态。

只读 `capturework-statistics-status` 报告当前缓存身份、published／consumed／invalidated 和 pending。`statistics_slot` 是最后消费所用槽；当 pending=true 时，当前缓存身份可能属于下一帧，不能把该槽当成它已完成输出的证明。统计来源记录在 pending=false 且 consumed 递增时才能与当前身份配对。

## 实验配置与剩余工作

r91 原厂窗口没有传入 `nikon-z72-boot-config.z62-card-detect=on`。实际 r91 源码中，统计时钟和 preview_supported 都依赖此项；因此当时 grid 的 disabled 不能单独作为硬件缺失证据。r92 新原厂驱动在原有配置之上显式加入该项，并记录完整命令。即使修正配置，旧统计仍只认 raw_accepted，故需要上述独立来源接口。

照片预览需要四个槽的完整来源与生命周期，本模块没有将一个 CW 新帧伪装成四个新输入。readout、四槽预览／视频 ISP、完整模式恢复、原厂编码存卡、AF、物理共享源对及刷写安全继续未验收。
