# 纤维拉伸强度分析工具

计算单根纤维最大拉伸强度的 Windows 桌面工具（Python + PySide6，中文界面）。

## 功能

**①–③ 纤维拉伸强度**

- **双模式计算**
  - 单丝模式（碳纤维/玻璃纤维等，参考 GB/T 31290、ASTM C1557）：σ = 4F/(πd²)，输出 MPa/GPa
  - 纺织纤维模式（化纤/棉等，参考 GB/T 14337）：断裂强度 = F/线密度，输出 cN/dtex；填写密度后可换算 MPa
- **数据录入**：手动录入 + 强度实时预览；Excel(.xlsx)/CSV/TXT 批量导入（含逐行校验与错误定位）
- **批量统计**：均值、样本标准差（n−1）、变异系数 CV%、最小/最大值
- **Weibull 分布分析**：median rank 法 + 最小二乘拟合，输出模数 m、特征强度 σ₀、R² 与拟合图
- **报告导出**：Excel（统计汇总/数据明细/Weibull 数据 3 个 sheet，含图）与 PDF（内置中文字体）
- **历史数据管理**：SQLite 保存，支持筛选查询、批次对比、删除、重算

**④ 表面能**

- **四种计算方法**：
  - OWRK 双液法：γ_L(1+cosθ) = 2(√(γ_S^d·γ_L^d) + √(γ_S^p·γ_L^p))，最小二乘解出色散/极性分量与总表面能
  - Wu 调和平均法：调和平均公式 + 迭代求解，适合低能表面
  - Fowkes 法：单液体求色散分量 γ^d
  - Zisman 法：cosθ–γ_L 回归外推临界表面张力 γ_c（含 Zisman 拟合图）
- **内置液体参数库**：水、二碘甲烷、乙二醇、甘油、甲酰胺、α-溴萘、十六烷、苯甲醇（可自定义添加）
- 自动计算各液体的**界面能 γ_SL 与粘附功 W_A**
- 手动录入（液体库下拉自动填充参数）+ Excel/CSV/TXT 批量导入
- 历史保存（SQLite）、Excel/PDF 报告导出

## ⚠️ 本机运行须知（重要）

本机 PATH 中 `python` 命令被 Windows 商店的存根程序遮蔽，直接运行会静默失败。
**所有命令一律使用 `py` 启动器（即 `py -3`），不要用 `python`。**

## 安装与运行

```bat
:: 1. 安装依赖（Python 3.14，需联网）
py -3 -m pip install -r requirements.txt

:: 2. 运行
py -3 main.py
```

数据保存在 `%LOCALAPPDATA%\FiberTensile\fiber_tensile.db`（可用环境变量 `FT_DB_PATH` 覆盖）。

## 使用流程

界面左侧为**模块导航栏**，在两个功能模块间切换（自动记忆上次位置）：

- **纤维拉伸强度**（内含三个子页签）
  1. **① 数据录入**：选择计算模式 → 填写批次信息与试样参数 → 查看强度实时预览 → 「添加数据」逐条录入，或「批量导入…」从文件导入（可先「下载导入模板」按格式准备数据）→ 「保存到数据库」
  2. **② 统计分析**：选择批次 → 查看统计结果与 Weibull 拟合图 → 导出 Excel/PDF 报告
  3. **③ 历史记录**：筛选查询批次 → 点击查看样本明细；按住 Ctrl 多选 ≥2 个同模式批次 → 「对比批次」
- **表面能**：选方法 → 「添加行」录入液体数据（下拉选库内液体自动填参数，填接触角）→ 「计算并保存」→ 历史里导出报告

### 表面能数据导入格式

一个文件 = 一条测量记录（多行液体数据），列名：

| 样品名称 | 方法 | 液体名称 | γ_L(mN/m) | γ^d(mN/m) | γ^p(mN/m) | 接触角(°) | 备注 | 测试日期 |

方法列可写中文别名（双液法/调和/Wu/Fowkes/Zisman）；γ^d/γ^p 可按方法留空；液体名称、γ_L、接触角必填。

### 导入文件列名规范

| 规范列名 | 别名 | 单丝模式 | 纺织模式 |
|---|---|---|---|
| 编号 | 样品编号/序号/sample_no | 可空 | 可空 |
| 批次 | 批次号/batch | 可空 | 可空 |
| 断裂强力 | 强力/force | **必填** | **必填** |
| 强力单位 | 单位/unit | 默认 cN（支持 cN/N/mN） | 默认 cN |
| 直径(μm) | 直径/diameter | **必填** | 出现即报错 |
| 线密度(dtex) | 线密度/Tt | 出现即报错 | **必填** |
| 密度(g/cm³) | 密度/density | 忽略 | 可选（填写后可换算 MPa） |
| 备注 / 测试日期 | remark / date | 可空（日期格式 2026-08-14） | 可空 |

列名匹配自动忽略大小写、全半角与空格差异。支持 .xlsx/.xlsm/.csv/.txt（CSV 编码自动识别 UTF-8/GBK）；不支持旧版 .xls，请另存为 .xlsx。

## 数值锚点（人工核对用）

| 输入 | 结果 |
|---|---|
| F = 10 cN，d = 7 μm（单丝） | σ = 2598.45 MPa ≈ 2.598 GPa |
| F = 10 cN，Tt = 2 dtex（纺织） | 5 cN/dtex |
| 5 cN/dtex，ρ = 1.14 g/cm³ | 570 MPa |

## 测试

```bat
:: 单元测试（计算/统计/Weibull/数据库/导入/报告，76 个用例）
py -3 -m pip install pytest
py -3 -m pytest tests/

:: UI 冒烟测试（自动跑全流程后退出，窗口会闪现约 1 秒）
py -3 scripts/smoke_ui.py
```

## 打包成 EXE

```bat
:: 直接双击 scripts\build.bat，产出两种形态：
::   文件夹版  dist\FiberTensileAnalyzer\FiberTensileAnalyzer.exe   启动快（1-3 秒），推荐日常使用
::   单文件版  dist\FiberTensileAnalyzerOneFile.exe                 一个 exe 便携，但每次启动需自解压（5-10 秒）
```

程序已做启动优化：pandas/openpyxl/reportlab/matplotlib 全部按需加载（只在导入文件、导出报告、绘制图表时才加载），启动时只加载录入界面必需的组件。

## 分享给他人

**别人不需要安装 Python 或任何环境**——程序已把运行所需的全部组件打包进去，只需满足：

- Windows 10 / 11 64 位系统（Win7 不支持）
- 把 `dist\FiberTensileAnalyzer` 整个文件夹压缩成 zip 发给对方，解压后运行里面的 exe 即可（推荐：启动快）
- 或直接发送单文件版 `FiberTensileAnalyzerOneFile.exe`（方便，但对方每次启动会慢几秒）

注意事项：

- 首次运行时 Windows SmartScreen 可能提示「已保护你的电脑」（程序未做数字签名）——对方点「更多信息」→「仍要运行」即可
- 个别杀毒软件可能误报（PyInstaller 打包程序的常见现象），加入白名单即可
- 数据保存在**每台电脑自己的** `%LOCALAPPDATA%\FiberTensile` 目录；若要把测试数据一并分享，用「批量导入/导出」的 Excel 文件传递

## 常见问题

- **启动慢**：单文件版每次启动都要自解压（正常现象），改用文件夹版可 1-3 秒启动。
- **图表中文显示为方块字**：删除 matplotlib 缓存目录后重启（`%LOCALAPPDATA%\matplotlib` 下删除 `fontlist-*.json` 或整个缓存目录）。
- **杀毒软件误报 EXE**：PyInstaller 打包的程序偶发误报，将 EXE 加入白名单即可；或改用 onedir 模式打包。
- **导入报「无法识别文件编码」**：把 CSV 另存为 UTF-8 或 GBK 编码。
- **Weibull 提示「拟合斜率为负」**：数据分散性过大或存在异常低值，请检查数据。

## 项目结构

```
main.py                  入口
fiber_tensile/
├── config.py            应用配置、matplotlib 中文配置（数值范围再导出自 core/modes.py）
├── logging_setup.py     日志配置与未捕获异常钩子（app.log 与数据库同目录）
├── core/                纯计算层（numpy）：单位换算、强度公式、统计、Weibull 拟合、数据模型
│   └── modes.py         计算模式注册表：新模式的单一事实来源（标签/单位/维度字段/公式）
├── data/                持久层：SQLite 版本化迁移（v1 纤维 + v2 表面能）、批次/样本 CRUD
├── fileio/              文件层：Excel/CSV/TXT 导入校验、模板生成、Excel/PDF 报告导出
├── plotting.py          Weibull 拟合图构建（UI 与报告共用，含拟合方程标注）
├── surface_energy/      表面能模块：四种方法计算核心、液体库、导入、报告、Tab④
└── ui/                  Qt 界面：主窗口（左侧导航切换模块）、导入向导、批次对比、偏好记忆、中文图工具
scripts/
├── smoke_ui.py          UI 冒烟测试
├── generate_test_data.py  随机测试数据生成（参数化，--skip-db 不入库）
├── build.bat            一键双打包（文件夹版 + 单文件版）
├── verify_exe.ps1 / measure_startup.ps1  打包验证与启动测速（用临时库，不碰真实数据）
tests/                   pytest 单元测试（125 个用例）
```

**扩展指南**：新增计算模式 → `core/modes.py` 注册表加一条 `ModeSpec` + `core/formulas.py` 写公式函数，录入表单/导入校验/报告列自动适配；新增功能域（如 EMI）→ 加迁移建表 + 独立模块 + 新 Tab。
