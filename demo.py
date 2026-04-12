import os  # 提供路径拼接、绝对路径等操作系统相关功能
import shutil  # 提供 which，用来在系统 PATH 中查找可执行文件
import subprocess  # 用来启动外部程序（这里用于启动 runSofa）
import sys  # 用于获取/返回脚本退出码


def createScene(rootNode):  # SOFA 入口函数：搭建整个仿真场景树
    base_dir = os.path.dirname(os.path.abspath(__file__))  # 当前 py 文件所在目录的绝对路径
    mesh_dir = os.path.join(base_dir, "details", "data", "mesh")  # 网格文件目录（vtk/stl 都在这里）

    rootNode.dt = 0.02  # 仿真步长（秒），每一步推进 0.02s
    rootNode.gravity.value = [-9.81, 0, 0]  # 重力方向和大小（沿 x 负方向）

    plugins = rootNode.addChild("Plugins")  # 专门放 RequiredPlugin，便于集中管理依赖
    plugins.addObject("RequiredPlugin", name="SoftRobotsPlugin", pluginName="SoftRobots")  # 软体机器人核心组件
    plugins.addObject("RequiredPlugin", name="AnimationLoopPlugin", pluginName="Sofa.Component.AnimationLoop")  # 动画/仿真循环组件
    plugins.addObject("RequiredPlugin", name="ConstraintCorrectionPlugin", pluginName="Sofa.Component.Constraint.Lagrangian.Correction")  # 约束修正组件
    plugins.addObject("RequiredPlugin", name="ConstraintSolverPlugin", pluginName="Sofa.Component.Constraint.Lagrangian.Solver")  # 拉格朗日约束求解器组件
    plugins.addObject("RequiredPlugin", name="IOMeshPlugin", pluginName="Sofa.Component.IO.Mesh")  # 网格读写（VTK/STL 加载）
    plugins.addObject("RequiredPlugin", name="LinearSolverDirectPlugin", pluginName="Sofa.Component.LinearSolver.Direct")  # 直接线性求解器（SparseLDL）
    plugins.addObject("RequiredPlugin", name="MappingLinearPlugin", pluginName="Sofa.Component.Mapping.Linear")  # 线性映射（父子节点力/位移映射）
    plugins.addObject("RequiredPlugin", name="MassPlugin", pluginName="Sofa.Component.Mass")  # 质量模型组件
    plugins.addObject("RequiredPlugin", name="ODESolverBackwardPlugin", pluginName="Sofa.Component.ODESolver.Backward")  # 隐式时间积分组件
    plugins.addObject("RequiredPlugin", name="FEMElasticPlugin", pluginName="Sofa.Component.SolidMechanics.FEM.Elastic")  # FEM 弹性力学组件
    plugins.addObject("RequiredPlugin", name="SpringPlugin", pluginName="Sofa.Component.SolidMechanics.Spring")  # 弹簧/形状保持组件
    plugins.addObject("RequiredPlugin", name="StateContainerPlugin", pluginName="Sofa.Component.StateContainer")  # 状态容器（位置、速度等）
    plugins.addObject("RequiredPlugin", name="TopologyContainerPlugin", pluginName="Sofa.Component.Topology.Container.Constant")  # 拓扑容器组件
    plugins.addObject("RequiredPlugin", name="VisualPlugin", pluginName="Sofa.Component.Visual")  # 可视化组件
    plugins.addObject("RequiredPlugin", name="Rendering3DPlugin", pluginName="Sofa.GL.Component.Rendering3D")  # OpenGL 3D 渲染组件
    plugins.addObject("RequiredPlugin", name="EngineSelectPlugin", pluginName="Sofa.Component.Engine.Select")  # ROI 选择等几何筛选组件

    rootNode.addObject("VisualStyle", displayFlags="showVisualModels showBehaviorModels")  # 同时显示外观模型和行为模型
    rootNode.addObject("InteractiveCamera", name="camera", position=[0.12, 0.08, 0.12], lookAt=[-0.04, 0.02, 0.0])  # 设置初始相机位置和观察点
    rootNode.addObject("FreeMotionAnimationLoop")  # 常用于含约束场景的主循环
    rootNode.addObject("BlockGaussSeidelConstraintSolver", tolerance=1e-7, maxIterations=1000)  # 约束求解参数：误差阈值和迭代上限

    finger = rootNode.addChild("Finger")  # 软体手指主节点（物理主体）
    finger.addObject("EulerImplicitSolver", rayleighStiffness=0.1, rayleighMass=0.1)  # 隐式欧拉积分，附带少量 Rayleigh 阻尼
    finger.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixd")  # 稀疏 LDL 线性求解器
    finger.addObject(
        "MeshVTKLoader",  # 读取四面体体网格（用于力学计算）
        name="loader",  # 给加载器命名，后续用 @loader 引用
        filename=os.path.join(mesh_dir, "mypneunetCut_all.vtk"),  # 体网格文件路径
        scale3d=[0.001, 0.001, 0.001],  # mm 转 m（缩放 0.001）
    )
    finger.addObject("MeshTopology", src="@loader", name="container")  # 从 loader 建立拓扑（点/四面体连接关系）
    finger.addObject("MechanicalObject", name="tetras", template="Vec3", showObject=False)  # 力学自由度（每个节点 3D 坐标）
    finger.addObject(
        "TetrahedronFEMForceField",  # 四面体有限元弹性力场
        template="Vec3",  # 位移是三维向量
        name="FEM",  # 力场名字
        method="large",  # 大变形模型（非线性几何）
        poissonRatio=0.3,  # 泊松比（横向收缩程度）
        youngModulus=5e5,  # 杨氏模量（材料刚度）
    )
    finger.addObject("UniformMass", totalMass=0.04)  # 给整体赋总质量 0.04 kg

    return rootNode  # 返回场景根节点给 SOFA


def _find_runsofa():  # 在 PATH 里查找 runSofa 可执行文件
    for cmd in ("runSofa", "runsofa", "runSofa.exe", "runsofa.exe"):  # 兼容大小写和 Windows 后缀
        path = shutil.which(cmd)  # 找到就返回绝对路径，找不到返回 None
        if path:  # 只要命中任意一个名字就可用
            return path  # 返回找到的可执行文件路径
    return None  # 全部没找到


def _launch_imgui_scene():  # 组装命令并启动 runSofa + imgui
    scene_file = os.path.abspath(__file__)  # 当前场景脚本的绝对路径
    runsofa = _find_runsofa()  # 查找 runSofa 程序位置
    if not runsofa:  # 如果没找到，给出可理解的报错
        print("[ERROR] 未找到 runSofa，可执行文件未在 PATH 中。")  # 报错信息 1
        print("请确认 runSofa 已加入系统环境变量后重试。")  # 报错信息 2（如何修复）
        return 1  # 非 0 退出码表示启动失败

    cmd = [runsofa, "-l", "SofaPython3", "-g", "imgui", "-i", scene_file]  # 不加 -a：默认暂停启动，便于手动控制
    print("[INFO] Launch:", " ".join(cmd))  # 打印完整命令，方便排查问题
    return subprocess.run(cmd, cwd=os.path.dirname(scene_file), check=False).returncode  # 在脚本目录执行并返回 runSofa 退出码


if __name__ == "__main__":  # 只有直接运行本文件时才执行
    sys.exit(_launch_imgui_scene())  # 用 runSofa 的返回码作为脚本退出码
