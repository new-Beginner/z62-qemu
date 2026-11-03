# r57 序列化之前的原厂帧描述符

授权延续完整目标，仅离线开发／仿真，不接入设备或刷写。r56原厂55秒窗口已正常结束，source观察器因100条单点上限exit1，失败保持。r57观察不同边界：102C1D98与102C1E1E构造器入口及返回，记录输入frame-context、最多4个原始描述符、core模板与完整53词序列化根表，不重跑旧点来改变旧验收结果。

自身原厂102BFEBA从descriptor+26取stride、+34取DMA地址；102C13D6从descriptor+28／2A取几何；102C0678可以让core指向frame-context+35C的模板。记录这些来源事实，不将字段相同当作新DMA或真实图像转换。

完整根表的word51／52为标志，不能把全部53词统称指针。只读所有参数／寄存器／RAM，未知与短读保持unknown。冻结r53、原始固件、ready／软件队列／超时／IRQ保持原样。network_profile=offline。
