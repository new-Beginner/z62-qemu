# Z6II QEMU v0.3.0 分析范围

- auth：用户拥有 Z6II，授权搜索、拉取、读取 Z7II 开源 QEMU，并自主改进本地 Z6II 模拟器。
- in_scope：`JKWTCN/z72-qemu` 固定提交 `f6b80ec650116a6b0117d31f9ea112b05bb7f52a` 的源码对照；本地 Z6II 1.70 两份原始 ARM payload；独立 Unicorn 探针；Windows 原生 QEMU 板型、构建包、回归测试与文档。
- out_of_scope：相机连接、刷写或安装固件；签名重打包；向外上传尼康固件；把未验证 Z7II 寄存器、地址窗口、GPIO 接线和菜单补丁直接用于 Z6II。
- network_profile：仅公开 GitHub 仓库搜索与源码拉取；本轮使用已有固定摘要 QEMU 源码和隔离 MSYS2 工具链，不上传本地样本。
- 样本等价入口：裸 ARM little-endian 固件无 PE/ELF 导入表；用复位分支、CP15 页表启用、原厂配置例程与状态轮询作为入口/依赖锚点。固件指纹沿用并复核 `artifacts/z6ii-1.70/manifest.json`，不是宿主可执行样本。
- 工具：Capstone 5.0.7、Unicorn 2.1.4、QEMU 10.2.4、Python 3.12、已有 MSYS2 UCRT64。IDA 启动脚本返回 `IDADIR not set and IDA Pro not found`，本轮使用可用替代工具完成分析；技能所述 `tool-index.md` 在本地技能树中未找到，工具路径直接核验。
- 模型：61 个被动 uint32 配置字，零复位为明确实验假设。不提供 `0x20022300` 完成位；不模拟时钟/供电/内存训练真实效果。未知地址和错误访问维持严格拒绝。
- 对比限制：Z7II 部分来自固定提交源码及其公开证据；未取得、执行或独立验证 Z7II 固件，也不把其文档中的历史辅助实验视为原固件自然启动。
- 固件只读；新包不含固件。MENU、双 EXPEED 传输、完整 RAM/BSS 和整机迁移仍不在本轮已验证功能中。
