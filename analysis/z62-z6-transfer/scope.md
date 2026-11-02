# Z62参考Z6推进：实验范围

- 目标：对照Z6的事务完成机制，验证Z62初始化提交是否已发生、现有受控完成源对菜单生命周期的影响，并恢复真实输入描述符。
- 固定Z62参考构建：2026.10.27-r1；SHA256 e169431ed0a24dded62c2d3e0ea2aba1056385ec96584c57b40cd4e5ab29fba4。Z62来源4f4389944fc339d107f22f5f7ca3f90cc34b78de；Z6参考419a1f2a91a1f2d3a0209027c29606475f7fe26f。
- 原C1.70主成员SHA256 bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4；基址10020000，裸ARM/Thumb无传统PE导入表，等价锚点为输入哈希、MMIO访问函数、固定模型源码和实际运行日志。
- 合成参数，不是实机NOR/校准；不连接相机、不发送PTP、不刷机、不改guest指令/返回值/错误列表；正常控制器按键，不使用主屏辅助函数或外部捕获边界注入。
- mode-only仅开现有laboratory-mode-completion；init-mode在其基础上只增加现有laboratory-init-completion，init-delay-ns保留默认33333333，不增加frame-start、metadata、frame-completion等其它源。
- 两者都是功能性握手假设，不含RAW像素/DMA/ISP；不能作为物理传感器或真实取景模型验收。
- 诊断观测通过QMP qom-get读取master/slave sensor计数器、主核HMP x读取既有配置；多请求快照非原子。缺失值保留unknown/error，不填0。
- 新入口2026.10.28-r3为宿主配置版本，复用r1设备二进制，旧入口/固定子模块保留。没有重编译或发布便携安装包。
- artifacts/z62-z6-transfer-20261028/各目录独立冷启动。初期单循环未做重开后像素变化判据；三循环和delayed组额外要求重开后方向键改变画面。退出截图可能残留旧菜单，不能仅凭旧帧判定主屏已恢复。
- 最终完整验收仍需实际数据事务与成像链，十轮/三次冷启动严格矩阵不以较少次数冒充。
