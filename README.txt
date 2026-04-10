独立版 Pneunet 气动夹爪 GUI 由AI生成，如有错误，请自行AI解决

项目简介
- 本仓库是一个基于 SOFA + SoftRobots 的 Pneunet 气动软体手指示例。
- 主交互场景脚本：pneunetgripper_keyboard.py
- 辅助场景脚本（手动压力配置）：my_pneunet.py
- 网格查看脚本：read_vtk.py

目录结构
- pneunetgripper_keyboard.py
- my_pneunet.py
- read_vtk.py
- details/data/mesh/pneunetCutCoarse.vtk
- details/data/mesh/pneunetCut.vtk
- details/data/mesh/pneunetCut.stl
- details/data/mesh/pneunetCavityCut.stl

环境要求
1) 已安装 SOFA，并可用以下插件：
   - SoftRobots
   - SofaPython3
   - Sofa.GL.Component
   - Sofa.GUI.Component
2) Python 环境：
   - 运行场景脚本需要：SOFA 自带的 Python 绑定
   - Linux 全局键盘回退（可选）：pynput
   - 网格查看脚本（可选）：pyvista、numpy
3) 建议设置 SOFA_ROOT 指向 SOFA 根目录。

Windows 示例：
set SOFA_ROOT=C:\path\to\SOFA\v25.12.00

PowerShell 示例：
$env:SOFA_ROOT = "C:\path\to\SOFA\v25.12.00"

运行方式（推荐）
1) 在本目录打开终端。
2) 使用 runSofa 启动交互场景：
   runSofa -l SofaPython3 -g imgui -a -i pneunetgripper_keyboard.py

备选运行方式
- 直接用 Python 启动：
  python pneunetgripper_keyboard.py

脚本会通过以下方式自动寻找 SOFA：
- SOFA_ROOT
- PATH 中的 runSofa
- 当前脚本附近的父目录/同级目录

键盘控制（交互场景）
- 充气：+, =, 小键盘 +, P, I
- 放气：-, _, 小键盘 -, M, K
- 每次按键压力步长：0.1
- 压力限制范围：[-2.0, 3.0]

运行辅助场景
- 使用 runSofa：
  runSofa -l SofaPython3 -g imgui -i my_pneunet.py
- 或用脚本内封装方式：
  python my_pneunet.py

查看网格文件
- 默认读取 details/data/mesh/pneunetCut.vtk：
  python read_vtk.py

常见问题排查
- 报错："Cannot locate SOFA installation"
  - 请正确设置 SOFA_ROOT 后重试。
  - 或将 SOFA 的 bin 目录加入 PATH，确保能找到 runSofa。
- 报错："runSofa not found"
  - 请检查 SOFA 安装是否完整，以及 PATH 是否配置正确。
- GUI 打开但按键无响应：
  - 先点击 GUI 窗口让其获得焦点。
  - 显式指定 imgui 后端再试：
    set PNEUNET_GUI=imgui
  - Linux 下可安装 pynput 作为全局键盘回退。
