"""
AI CAM 4.0 — GL Constants, Shader Sources, Color Palette
=========================================================

Central location for all OpenGL constants, shader source strings,
and application color definitions. Keeps shader code out of the
renderer and makes tweaking visuals trivial.

Key lessons from v3:
- Keep shader source as raw strings in one place
- Color palette uses linear-space floats (0-1), not sRGB hex
- All constants are immutable module-level values
"""

from __future__ import annotations

import ctypes
from typing import Final

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# GL Version / Profile
# ---------------------------------------------------------------------------
GL_MAJOR: Final[int] = 3
GL_MINOR: Final[int] = 3
GL_PROFILE: Final[str] = "core"

# NVIDIA RTX 4070 Ti workarounds
SAMPLES: Final[int] = 0          # MSAA=0 avoids driver crashes
SWAP_INTERVAL: Final[int] = 0    # VSync off to prevent hangs

# ---------------------------------------------------------------------------
# Buffer / Attribute sizes
# ---------------------------------------------------------------------------
FLOAT_SIZE: Final[int] = ctypes.sizeof(ctypes.c_float)
VEC3_SIZE: Final[int] = 3 * FLOAT_SIZE
VEC4_SIZE: Final[int] = 4 * FLOAT_SIZE

# Stride for interleaved vertex data: position (3) + normal (3) = 6 floats
VERTEX_STRIDE: Final[int] = 6 * FLOAT_SIZE
POSITION_OFFSET: Final[int] = 0
NORMAL_OFFSET: Final[int] = 3 * FLOAT_SIZE

# ---------------------------------------------------------------------------
# Color Palette (linear RGB, 0-1)
# ---------------------------------------------------------------------------
COLOR_BACKGROUND: Final[NDArray[np.float32]] = np.array(
    [0.18, 0.18, 0.20, 1.0], dtype=np.float32
)
COLOR_GRID_MAJOR: Final[NDArray[np.float32]] = np.array(
    [0.35, 0.35, 0.38, 1.0], dtype=np.float32
)
COLOR_GRID_MINOR: Final[NDArray[np.float32]] = np.array(
    [0.25, 0.25, 0.28, 0.6], dtype=np.float32
)
COLOR_STOCK: Final[NDArray[np.float32]] = np.array(
    [0.45, 0.55, 0.65, 1.0], dtype=np.float32
)
COLOR_STOCK_NORMAL: Final[NDArray[np.float32]] = np.array(
    [0.5, 0.7, 1.0], dtype=np.float32
)
COLOR_MESH: Final[NDArray[np.float32]] = np.array(
    [0.85, 0.65, 0.13, 1.0], dtype=np.float32
)
COLOR_MESH_NORMAL: Final[NDArray[np.float32]] = np.array(
    [0.9, 0.8, 0.3], dtype=np.float32
)
COLOR_TOOLPATH: Final[NDArray[np.float32]] = np.array(
    [0.2, 0.8, 0.3, 1.0], dtype=np.float32
)
COLOR_RAPID: Final[NDArray[np.float32]] = np.array(
    [0.8, 0.2, 0.2, 0.5], dtype=np.float32
)
COLOR_AXIS_X: Final[NDArray[np.float32]] = np.array(
    [0.9, 0.2, 0.2, 1.0], dtype=np.float32
)
COLOR_AXIS_Y: Final[NDArray[np.float32]] = np.array(
    [0.2, 0.8, 0.2, 1.0], dtype=np.float32
)
COLOR_AXIS_Z: Final[NDArray[np.float32]] = np.array(
    [0.2, 0.4, 0.9, 1.0], dtype=np.float32
)
COLOR_WHITE: Final[NDArray[np.float32]] = np.array(
    [1.0, 1.0, 1.0, 1.0], dtype=np.float32
)
COLOR_OVERLAY_TEXT: Final[NDArray[np.float32]] = np.array(
    [0.85, 0.85, 0.85, 1.0], dtype=np.float32
)

# ---------------------------------------------------------------------------
# Shader: Basic Lit (position + normal → color)
# ---------------------------------------------------------------------------
VERTEX_SHADER_LIT: Final[str] = """
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;
uniform mat3 u_normal_matrix;

out vec3 v_normal;
out vec3 v_frag_pos;

void main() {
    vec4 world_pos = u_model * vec4(a_position, 1.0);
    v_frag_pos = world_pos.xyz;
    v_normal = normalize(u_normal_matrix * a_normal);
    gl_Position = u_projection * u_view * world_pos;
}
"""

FRAGMENT_SHADER_LIT: Final[str] = """
#version 330 core

in vec3 v_normal;
in vec3 v_frag_pos;

uniform vec3 u_color;
uniform vec3 u_light_dir;
uniform vec3 u_light_color;
uniform vec3 u_ambient;
uniform float u_alpha;

out vec4 frag_color;

void main() {
    vec3 norm = normalize(v_normal);
    vec3 light_d = normalize(u_light_dir);

    // Diffuse
    float diff = max(dot(norm, light_d), 0.0);

    // Simple specular (Blinn-Phong)
    vec3 view_dir = normalize(-v_frag_pos);
    vec3 half_dir = normalize(light_d + view_dir);
    float spec = pow(max(dot(norm, half_dir), 0.0), 32.0);

    vec3 result = u_ambient * u_color
                + diff * u_light_color * u_color
                + spec * 0.15 * u_light_color;

    frag_color = vec4(result, u_alpha);
}
"""

# ---------------------------------------------------------------------------
# Shader: Solid Color (no lighting, for grid/overlay lines)
# ---------------------------------------------------------------------------
VERTEX_SHADER_SOLID: Final[str] = """
#version 330 core

layout(location = 0) in vec3 a_position;

uniform mat4 u_mvp;
uniform vec4 u_color;

out vec4 v_color;

void main() {
    v_color = u_color;
    gl_Position = u_mvp * vec4(a_position, 1.0);
}
"""

FRAGMENT_SHADER_SOLID: Final[str] = """
#version 330 core

in vec4 v_color;

out vec4 frag_color;

void main() {
    frag_color = v_color;
}
"""

# ---------------------------------------------------------------------------
# Shader: Toolpath (position only, colored by uniform)
# ---------------------------------------------------------------------------
VERTEX_SHADER_TOOLPATH: Final[str] = """
#version 330 core

layout(location = 0) in vec3 a_position;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

void main() {
    gl_Position = u_projection * u_view * u_model * vec4(a_position, 1.0);
}
"""

FRAGMENT_SHADER_TOOLPATH: Final[str] = """
#version 330 core

uniform vec4 u_color;

out vec4 frag_color;

void main() {
    frag_color = u_color;
}
"""

# ---------------------------------------------------------------------------
# Shader: Stock heightmap (Z-map specific vertex layout)
# ---------------------------------------------------------------------------
VERTEX_SHADER_STOCK: Final[str] = """
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;
uniform mat3 u_normal_matrix;

out vec3 v_normal;
out vec3 v_frag_pos;

void main() {
    vec4 world_pos = u_model * vec4(a_position, 1.0);
    v_frag_pos = world_pos.xyz;
    v_normal = normalize(u_normal_matrix * a_normal);
    gl_Position = u_projection * u_view * world_pos;
}
"""

FRAGMENT_SHADER_STOCK: Final[str] = """
#version 330 core

in vec3 v_normal;
in vec3 v_frag_pos;

uniform vec3 u_color;
uniform vec3 u_light_dir;
uniform vec3 u_light_color;
uniform vec3 u_ambient;

out vec4 frag_color;

void main() {
    vec3 norm = normalize(v_normal);
    vec3 light_d = normalize(u_light_dir);
    float diff = max(dot(norm, light_d), 0.0);

    vec3 view_dir = normalize(-v_frag_pos);
    vec3 half_dir = normalize(light_d + view_dir);
    float spec = pow(max(dot(norm, half_dir), 0.0), 32.0);

    vec3 result = u_ambient * u_color
                + diff * u_light_color * u_color
                + spec * 0.1 * u_light_color;

    frag_color = vec4(result, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Default light parameters
# ---------------------------------------------------------------------------
DEFAULT_LIGHT_DIR: Final[NDArray[np.float32]] = np.array(
    [0.5, 0.8, 0.6], dtype=np.float32
)
DEFAULT_LIGHT_COLOR: Final[NDArray[np.float32]] = np.array(
    [1.0, 1.0, 1.0], dtype=np.float32
)
DEFAULT_AMBIENT: Final[NDArray[np.float32]] = np.array(
    [0.15, 0.15, 0.18], dtype=np.float32
)

# ---------------------------------------------------------------------------
# Camera defaults
# ---------------------------------------------------------------------------
CAMERA_DEFAULT_DISTANCE: Final[float] = 100.0
CAMERA_DEFAULT_FOV: Final[float] = 45.0
CAMERA_NEAR: Final[float] = 0.1
CAMERA_FAR: Final[float] = 10000.0
CAMERA_ORBIT_SENSITIVITY: Final[float] = 0.005
CAMERA_ZOOM_SENSITIVITY: Final[float] = 0.1
CAMERA_PAN_SENSITIVITY: Final[float] = 0.003

# ---------------------------------------------------------------------------
# Grid defaults
# ---------------------------------------------------------------------------
GRID_SIZE: Final[int] = 20
GRID_SPACING: Final[float] = 10.0
GRID_LINE_WIDTH: Final[float] = 1.0

# ---------------------------------------------------------------------------
# FPS calculation
# ---------------------------------------------------------------------------
FPS_SAMPLE_COUNT: Final[int] = 60

# ---------------------------------------------------------------------------
# Z-Map stock rendering
# ---------------------------------------------------------------------------
STOCK_DEFAULT_COLOR: Final[NDArray[np.float32]] = np.array(
    [0.45, 0.55, 0.65], dtype=np.float32
)
