import pyvista as pv
import os
import numpy as np

mesh_dir = os.path.join(os.getcwd(), "details", "data", "mesh")
file_path = os.path.join(mesh_dir, "mypneunetCut_all.vtk")
# file_path = os.path.join(mesh_dir, "pneunetCutCoarse.vtk")
mesh = pv.read(file_path)
print(f"Loaded mesh from {file_path}")
# ======================
# 打印网格报告
# ======================
print("\n========== MESH REPORT ==========")
print(mesh)

print("\nPoints:", mesh.n_points)
print("Cells :", mesh.n_cells)

cell_types, counts = np.unique(mesh.celltypes, return_counts=True)
print("\nCell type distribution:")
for c, n in zip(cell_types, counts):
    print(f"  type {c}: {n}")

print("================================\n")

# ======================
# 可视化
# ======================
plotter = pv.Plotter()

plotter.add_mesh(
    mesh,
    color="lightgray",
    opacity=0.4,
    show_edges=True
)

plotter.add_axes()
plotter.enable_eye_dome_lighting()
plotter.set_background("white")

plotter.show()