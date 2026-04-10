import os
import shutil
import subprocess
import sys
import ctypes
from threading import Lock
from pathlib import Path


def _bootstrap_sofa_python():
    """Allow running this script with a regular Python by discovering SOFA bindings."""
    def _is_sofa_root(path):
        path = Path(path)
        return (path / "bin" / "runSofa").exists() or (path / "bin" / "runSofa.exe").exists()

    def _candidate_sofa_roots():
        here = Path(__file__).resolve()
        seen = set()

        env_root = os.environ.get("SOFA_ROOT", "").strip()
        if env_root:
            candidate = Path(env_root).expanduser().resolve()
            if candidate not in seen:
                seen.add(candidate)
                yield candidate

        # If runSofa is available in PATH, infer SOFA root as <...>/bin/runSofa(.exe) -> <...>
        for cmd in ("runSofa", "runsofa", "runSofa.exe", "runsofa.exe"):
            runsofa = shutil.which(cmd)
            if not runsofa:
                continue
            runsofa_path = Path(runsofa).resolve()
            if runsofa_path.parent.name.lower() == "bin":
                candidate = runsofa_path.parent.parent
            else:
                candidate = runsofa_path.parent
            if candidate not in seen:
                seen.add(candidate)
                yield candidate

        for parent in here.parents:
            if parent not in seen:
                seen.add(parent)
                yield parent

        for parent in here.parents:
            try:
                siblings = sorted(parent.iterdir(), key=lambda item: item.name)
            except OSError:
                continue

            for sibling in siblings:
                if sibling in seen or not sibling.is_dir():
                    continue
                if _is_sofa_root(sibling):
                    seen.add(sibling)
                    yield sibling

    venv_site_packages = (
        Path(__file__).resolve().parent
        / ".venv"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if venv_site_packages.exists() and str(venv_site_packages) not in sys.path:
        sys.path.insert(0, str(venv_site_packages))

    sofa_root = None
    for candidate in _candidate_sofa_roots():
        if _is_sofa_root(candidate):
            sofa_root = candidate
            break

    if sofa_root is None:
        raise RuntimeError(
            "Cannot locate SOFA installation. Set SOFA_ROOT to your SOFA root folder "
            "or place this demo next to a SOFA install containing bin/runSofa."
        )

    site_packages = sofa_root / "plugins" / "SofaPython3" / "lib" / "python3" / "site-packages"
    bin_dir = sofa_root / "bin"

    if site_packages.exists() and str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))

    if bin_dir.exists():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(bin_dir))

    return sofa_root


SOFA_ROOT = _bootstrap_sofa_python()

try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None

import Sofa
import Sofa.Core
import Sofa.Simulation
import Sofa.constants.Key as Key


class FingerController(Sofa.Core.Controller):
    def __init__(self, *args, **kwargs):
        Sofa.Core.Controller.__init__(self, *args, **kwargs)
        self._root = kwargs["node"]
        self._step = kwargs.get("step", 0.1)
        self._p_min = kwargs.get("p_min", -2.0)
        self._p_max = kwargs.get("p_max", 3.0)
        self._debug_key_logs = 0
        self._win_user32 = ctypes.windll.user32 if os.name == "nt" else None
        self._last_down = {}
        self._key_down = {}
        self._key_lock = Lock()
        self._system_keyboard_enabled = False
        self._keyboard_listener = None

        self._pressure_constraint = (
            self._root.getChild("Finger")
            .getChild("Cavity")
            .getObject("SurfacePressureConstraint")
        )

        if os.name != "nt" and pynput_keyboard is not None:
            self._start_global_keyboard_listener()

    def _set_pressure(self, value):
        clamped = max(self._p_min, min(self._p_max, value))
        self._pressure_constraint.value = [clamped]
        print(f"[Pressure] {clamped:.3f}")

    def _normalize_key_token(self, key):
        if key is None:
            return None

        char = getattr(key, "char", None)
        if char is not None:
            return char.lower()

        name = getattr(key, "name", None)
        if name:
            return name.lower()

        token = str(key)
        if token.startswith("Key."):
            token = token[4:]
        return token.strip("'").lower()

    def _set_key_state(self, token, is_down):
        if token is None:
            return
        with self._key_lock:
            self._key_down[token] = is_down

    def _is_key_state_down(self, token):
        with self._key_lock:
            return self._key_down.get(token, False)

    def _on_global_key_press(self, key):
        self._set_key_state(self._normalize_key_token(key), True)

    def _on_global_key_release(self, key):
        self._set_key_state(self._normalize_key_token(key), False)

    def _start_global_keyboard_listener(self):
        if self._keyboard_listener is not None:
            return

        try:
            listener = pynput_keyboard.Listener(
                on_press=self._on_global_key_press,
                on_release=self._on_global_key_release,
            )
            listener.daemon = True
            listener.start()
            self._keyboard_listener = listener
            self._system_keyboard_enabled = True
            print("[Keyboard] Ubuntu system keyboard listener enabled.")
        except Exception as exc:
            self._keyboard_listener = None
            self._system_keyboard_enabled = False
            print(f"[Keyboard] Ubuntu system keyboard listener unavailable: {exc}")

    def onKeypressedEvent(self, event):
        if os.name != "nt":
            return

        key = event["key"]
        key_str = str(key)
        key_code = ord(key) if isinstance(key, str) and len(key) == 1 else None
        if self._debug_key_logs < 20:
            print(f"[KeyEvent] key={key_str!r} code={key_code}")
            self._debug_key_logs += 1

        self._set_key_state(self._normalize_key_token(key), True)

    def onKeyreleasedEvent(self, event):
        if os.name != "nt":
            return

        key = event["key"]
        self._set_key_state(self._normalize_key_token(key), False)

    def _is_key_down_windows(self, vk_code):
        if self._win_user32 is None:
            return False
        return (self._win_user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

    def _on_edge(self, name, is_down):
        was_down = self._last_down.get(name, False)
        self._last_down[name] = is_down
        return is_down and not was_down

    def onAnimateBeginEvent(self, event):
        inflate_down = (
            self._is_key_state_down("plus")
            or self._is_key_state_down("+")
            or self._is_key_state_down("=")
            or self._is_key_state_down("kp_add")
            or self._is_key_state_down("numpadadd")
            or self._is_key_state_down("add")
            or self._is_key_state_down("uparrow")
            or self._is_key_state_down("p")
            or self._is_key_state_down("i")
            or self._is_key_down_windows(0xBB)  # VK_OEM_PLUS
            or self._is_key_down_windows(0x6B)  # VK_ADD
            or self._is_key_down_windows(0x50)  # P
            or self._is_key_down_windows(0x49)  # I
        )
        deflate_down = (
            self._is_key_state_down("minus")
            or self._is_key_state_down("-")
            or self._is_key_state_down("_")
            or self._is_key_state_down("kp_subtract")
            or self._is_key_state_down("numpadsubtract")
            or self._is_key_state_down("subtract")
            or self._is_key_state_down("downarrow")
            or self._is_key_state_down("m")
            or self._is_key_state_down("k")
            or self._is_key_down_windows(0xBD)  # VK_OEM_MINUS
            or self._is_key_down_windows(0x6D)  # VK_SUBTRACT
            or self._is_key_down_windows(0x4D)  # M
            or self._is_key_down_windows(0x4B)  # K
        )

        current = float(self._pressure_constraint.value.value[0])
        if self._on_edge("inflate", inflate_down):
            self._set_pressure(current + self._step)
        if self._on_edge("deflate", deflate_down):
            self._set_pressure(current - self._step)

    def onEvent(self, event):
        if self._debug_key_logs >= 20:
            return
        evt_name = type(event).__name__ if event is not None else "None"
        if "Key" in evt_name:
            print(f"[Event] {evt_name}: {event}")
            self._debug_key_logs += 1


def _update_pressure(root, delta, p_min=0.0, p_max=1.5):
    constraint = (
        root.getChild("Finger")
        .getChild("Cavity")
        .getObject("SurfacePressureConstraint")
    )
    value = float(constraint.value.value[0]) + delta
    value = max(p_min, min(p_max, value))
    constraint.value = [value]
    print(f"[Pressure] {value:.3f}")


def _run_batch_with_keyboard(root):
    print("Batch mode detected: no graphical GUI backend available.")
    print("Terminal keys: '+' inflate, '-' deflate, 'q' quit.")

    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    while True:
        if msvcrt and msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("+", "="):
                _update_pressure(root, +0.1)
            elif ch == "-":
                _update_pressure(root, -0.1)
            elif ch in ("q", "Q"):
                print("Exiting simulation.")
                break

        Sofa.Simulation.animate(root, root.dt.value)


def _launch_runsofa_gui():
    runsofa = SOFA_ROOT / "bin" / "runSofa"
    if not runsofa.exists():
        runsofa = SOFA_ROOT / "bin" / "runSofa.exe"
    scene = Path(__file__).resolve()
    if not runsofa.exists():
        print(f"runSofa not found: {runsofa}")
        return False

    # SofaPython3 must be loaded before loading a .py scene file.
    gui = os.environ.get("PNEUNET_GUI", "").strip() or "imgui"
    cmd = [str(runsofa), "-l", "SofaPython3", "-g", gui, "-a", "-i", str(scene)]
    print("Launching GUI with:", " ".join(cmd))
    env = os.environ.copy()
    env["PNEUNET_FROM_RUNSOFA"] = "1"
    subprocess.run(cmd, cwd=str(scene.parent), env=env, check=False)
    return True


def _detect_gui_backends():
    import Sofa.Gui as SofaGui

    try:
        import SofaRuntime

        for plugin in ("Sofa.GUI.Component", "Sofa.GL.Component"):
            try:
                SofaRuntime.importPlugin(plugin)
            except Exception:
                pass
    except Exception:
        pass

    supported = SofaGui.GUIManager.ListSupportedGUI(",")
    available = [g.strip() for g in supported.split(",") if g.strip()]
    return SofaGui, supported, available


def _pick_gui_backend(available):
    for candidate in ("imgui", "qglviewer", "glfw"):
        if candidate in available:
            return candidate
    return None


# Function called by SOFA when loaded as a scene file.
def createScene(rootNode):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    mesh_dir = os.path.join(base_dir, "details", "data", "mesh")

    rootNode.dt = 0.02
    rootNode.gravity.value = [-9810, 0, 0]

    plugins = rootNode.addChild("Plugins")
    plugins.addObject("RequiredPlugin", pluginName="SoftRobots")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Correction")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Solver")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Engine.Select")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.IO.Mesh")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Mapping.Linear")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.Spring")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Constant")
    plugins.addObject("RequiredPlugin", name="Sofa.Component.Visual")
    plugins.addObject("RequiredPlugin", name="Sofa.GL.Component.Rendering3D")
    rootNode.addObject("VisualStyle", displayFlags="showVisualModels showBehaviorModels")

    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("BlockGaussSeidelConstraintSolver", tolerance=1e-7, maxIterations=1000)

    finger = rootNode.addChild("Finger")
    finger.addObject("EulerImplicitSolver", rayleighStiffness=0.1, rayleighMass=0.1)
    finger.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixd")
    finger.addObject("MeshVTKLoader", name="loader", filename=os.path.join(mesh_dir, "pneunetCutCoarse.vtk"))
    finger.addObject("MeshTopology", src="@loader", name="container")
    finger.addObject("MechanicalObject", name="tetras", template="Vec3", showObject=False)
    finger.addObject(
        "TetrahedronFEMForceField",
        template="Vec3",
        name="FEM",
        method="large",
        poissonRatio=0.3,
        youngModulus=500,
    )
    finger.addObject("UniformMass", totalMass=0.04)

    box_roi_sub_topo = finger.addObject(
        "BoxROI", name="boxROISubTopo", box=[-100, 22.5, -8, -19, 28, 8], strict=False
    )
    box_roi = finger.addObject("BoxROI", name="boxROI", box=[-10, 0, -20, 0, 30, 20])
    finger.addObject(
        "RestShapeSpringsForceField",
        points=box_roi.indices.linkpath,
        stiffness=1e12,
        angularStiffness=1e12,
    )
    finger.addObject("GenericConstraintCorrection")

    sub_topology = finger.addChild("SubTopology")
    sub_topology.addObject(
        "MeshTopology",
        position="@../loader.position",
        tetrahedra=box_roi_sub_topo.tetrahedraInROI.linkpath,
        name="container",
    )
    sub_topology.addObject(
        "TetrahedronFEMForceField",
        template="Vec3",
        name="FEM",
        method="large",
        poissonRatio=0.3,
        youngModulus=1500,
    )

    cavity = finger.addChild("Cavity")
    cavity.addObject("MeshSTLLoader", name="cavityLoader", filename=os.path.join(mesh_dir, "pneunetCavityCut.stl"))
    cavity.addObject("MeshTopology", src="@cavityLoader", name="cavityMesh")
    cavity.addObject("MechanicalObject", name="cavity")
    cavity.addObject(
        "SurfacePressureConstraint",
        name="SurfacePressureConstraint",
        template="Vec3",
        value=0.0001,
        triangles="@cavityMesh.triangles",
        valueType="pressure",
    )
    cavity.addObject("BarycentricMapping", name="mapping", mapForces=False, mapMasses=False)

    visu = finger.addChild("VisualModel")
    visu.addObject("MeshSTLLoader", name="loader", filename=os.path.join(mesh_dir, "pneunetCut.stl"))
    visu.addObject("OglModel", src="@loader", color=[0.7, 0.7, 0.8, 1.0])
    visu.addObject("BarycentricMapping")

    rootNode.addObject(FingerController(name="FingerController", node=rootNode))
    print("GUI keys: + or P/I inflate, - or M/K deflate")

    return rootNode


def main(use_gui=True):
    if use_gui and os.environ.get("PNEUNET_FROM_RUNSOFA") != "1":
        _, supported, available = _detect_gui_backends()
        print("Supported GUIs:", supported)
        gui = _pick_gui_backend(available)
        if gui is None and _launch_runsofa_gui():
            return

    root = Sofa.Core.Node("root")
    createScene(root)
    Sofa.Simulation.initRoot(root)

    if not use_gui:
        for _ in range(300):
            Sofa.Simulation.animate(root, root.dt.value)
        return

    SofaGui, supported, available = _detect_gui_backends()
    gui = _pick_gui_backend(available)
    print("Supported GUIs:", supported)
    if gui is None:
        _run_batch_with_keyboard(root)
        return

    print("Using GUI:", gui)
    SofaGui.GUIManager.Init("pneunetgripper", gui)
    SofaGui.GUIManager.createGUI(root, __file__)
    SofaGui.GUIManager.SetDimension(1280, 800)
    SofaGui.GUIManager.MainLoop(root)
    SofaGui.GUIManager.closeGUI()


if __name__ == "__main__":
    main()
