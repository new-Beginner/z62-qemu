# r87 独立 MAIN 输入合同

层级 C，2026-11-04。本合同是模型内部接口，不是 Nikon 寄存器或传感器协议。当前仍未绑定 QEMU 设备；默认运行入口和 r69 EXE 保持不变。

## 帧格式

`Z62M` v1 为96字节小端头＋RAW16 LE载荷。与旧`Z62S`后级packed12帧分开，不能互相冒充。

| 偏移 | 类型 | 含义 |
|---:|---|---|
| 0 | 4 bytes | `Z62M` |
| 4/8/12 | 3×u32 | version=1，header bytes=96，role=1（MAIN） |
| 16/20/24/28 | 4×u32 | width、height、stride、payload bytes |
| 32/40/48/56 | 4×u64 | epoch、publication、frame ID、virtual time ns |
| 64/68 | 2×u32 | domain=1（linear16 LE）、CFA=1（RGGB） |
| 72/76 | 2×u32 | black、white；当前C生产者为1024／65520 |
| 80 | u32 | 保留0 |
| 84 | u32 | IEEE CRC32（payload） |
| 88 | u32 | IEEE CRC32（头部0…87） |
| 92 | u32 | 保留0 |
| 96 | payload | 独立stride的RAW16 LE，行尾padding=0 |

输入限偶数CFA尺寸、边长≤4096、≤4 Mi samples、总跨度≤64 MiB；stride为偶数且≥width×2。publication为正数、≤INT64_MAX；时间同样有界，`frame_id=floor(time_ns*30/1e9)`。CRC用于意外损坏检测，不是身份认证；最终实验回执另存完整SHA256。

Python生产者从现有场景RGB图像重采样、sRGB逆传递、近似黑白电平和RGGB取样生成独立MAIN。它不是把旧1514×1006辅助RAW扩大后当作MAIN，也不是恢复出的物理传感器、PDAF或尼康标定。

## C 缓存和读占用

调用者提供专属缓存，初始化一次；同一序列化执行者访问，后续QEMU绑定应持有BQL。发布先验证整个头、载荷、padding、容量和帧时间，再改变当前缓存。失败不改变旧数据。epoch固定，publication严格递增，时间不倒退；允许同一外部frame的新参数重新发布。

显式start后才允许begin读占用。读占用包含const像素、帧元数据副本和递增serial；占用期间新发布／第二次begin返回背压，不扩队列。不依赖宿主耗时推进帧号。

release只释放所有权，没有DMA确认、完成或IRQ含义。cancel、stop、reset使旧serial失效；延迟或重复release拒绝。取消后旧像素指针失效，不能交给无序列化保护的异步读者。reset保留外部帧／epoch／publication，清运行和占用，需新start；这只是C模型策略，不是对真实硬件reset的结论。serial耗尽后拒绝新工作，不回绕。

## 当前验证与下一接点

7项专项覆盖Python与实际GCC的格式／CRC／样本互操作、错误数据保持、背压、取消／停止／复位／旧任务、两套完整场景的全样本独立解码。另用现有Scene的移动图块、r86实际读回几何／LUT运行两帧，共3,046,168输出像素零差异；结果和8份源码归档在`analysis/z62-main-source-r87/scene-2`。

该链仍为普通宿主文件和C运算。尚缺原厂有效run／commit、ring-bank、真实生命周期与DMA／IRQ绑定；LUT输出为编码域，缺不可变transfer描述及下游逆变换。完整模式往返、原厂照片文件和AF未验收。

本轮完整Python发现690项，结果为2 failures／8 errors／0 skips，不能称全量通过。详见本轮报告和完整日志；失败集中于旧构建测试的Q:/D:同路径比较及旧SD接口解析SUBST后拒绝中文路径。
