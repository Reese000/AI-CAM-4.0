"""
AI CAM 4.0 — Renderer Utilities
=================================

Shader compilation, linking, uniform helpers, and GL resource management.

Key constraints from v3 lessons:
- Shader compilation errors MUST be logged (never silently swallowed)
- All GL resources get None-guards before use
- Returns None on failure instead of crashing
"""

from __future__ import annotations

import logging
import sys
from typing import Optional, Sequence

import numpy as np
from numpy.typing import NDArray

from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shader compilation
# ---------------------------------------------------------------------------
def compile_shader(
    gl: QOpenGLFunctions_3_3_Core,
    shader_type: int,
    source: str,
    label: str = "shader",
) -> Optional[int]:
    """Compile a single GLSL shader. Returns shader handle or None on error.

    Args:
        gl: OpenGL functions handle (must be current context).
        shader_type: GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, etc.
        source: GLSL source code string.
        label: Human-readable label for error messages.

    Returns:
        Shader handle (int) on success, None on failure.

    Error handling:
        Shader errors are always logged via logger.error(). Never swallowed.
    """
    if not source or not source.strip():
        logger.error("Shader '%s' source is empty", label)
        return None

    shader = gl.glCreateShader(shader_type)
    if shader == 0:
        logger.error("glCreateShader returned 0 for '%s'", label)
        return None

    gl.glShaderSource(shader, source)
    gl.glCompileShader(shader)

    # Check compile status
    status = [0]
    gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS, status)

    if status[0] == gl.GL_FALSE:
        log_length = [0]
        gl.glGetShaderiv(shader, gl.GL_INFO_LOG_LENGTH, log_length)
        if log_length[0] > 0:
            log_data = gl.glGetShaderInfoLog(shader, log_length[0])
            if isinstance(log_data, bytes):
                log_text = log_data.decode("utf-8", errors="replace")
            else:
                log_text = str(log_data)
        else:
            log_text = "(no info log available)"
        logger.error(
            "Shader compilation FAILED for '%s' (type=%s):\n%s",
            label,
            _shader_type_name(shader_type),
            log_text,
        )
        gl.glDeleteShader(shader)
        return None

    logger.debug("Shader '%s' compiled successfully", label)
    return shader


def link_program(
    gl: QOpenGLFunctions_3_3_Core,
    vertex_shader: int,
    fragment_shader: int,
    label: str = "program",
) -> Optional[int]:
    """Link vertex + fragment shaders into a program. Returns handle or None.

    Args:
        gl: OpenGL functions handle (must be current context).
        vertex_shader: Compiled vertex shader handle.
        fragment_shader: Compiled fragment shader handle.
        label: Human-readable label for error messages.

    Returns:
        Program handle (int) on success, None on failure.

    Error handling:
        Link errors are always logged via logger.error(). Never swallowed.
    """
    program = gl.glCreateProgram()
    if program == 0:
        logger.error("glCreateProgram returned 0 for '%s'", label)
        return None

    gl.glAttachShader(program, vertex_shader)
    gl.glAttachShader(program, fragment_shader)
    gl.glLinkProgram(program)

    # Check link status
    status = [0]
    gl.glGetProgramiv(program, gl.GL_LINK_STATUS, status)

    if status[0] == gl.GL_FALSE:
        log_length = [0]
        gl.glGetProgramiv(program, gl.GL_INFO_LOG_LENGTH, log_length)
        if log_length[0] > 0:
            log_data = gl.glGetProgramInfoLog(program, log_length[0])
            if isinstance(log_data, bytes):
                log_text = log_data.decode("utf-8", errors="replace")
            else:
                log_text = str(log_data)
        else:
            log_text = "(no info log available)"
        logger.error(
            "Program linking FAILED for '%s':\n%s",
            label,
            log_text,
        )
        gl.glDeleteProgram(program)
        return None

    logger.debug("Program '%s' linked successfully (id=%d)", label, program)
    return program


def compile_program(
    gl: QOpenGLFunctions_3_3_Core,
    vert_source: str,
    frag_source: str,
    label: str = "program",
) -> Optional[int]:
    """Compile and link a vertex+fragment shader pair in one call.

    Returns:
        Program handle on success, None on failure.
        Cleans up intermediate shader objects on failure.
    """
    vs = compile_shader(gl, gl.GL_VERTEX_SHADER, vert_source, f"{label}.vert")
    if vs is None:
        return None

    fs = compile_shader(gl, gl.GL_FRAGMENT_SHADER, frag_source, f"{label}.frag")
    if fs is None:
        gl.glDeleteShader(vs)
        return None

    program = link_program(gl, vs, fs, label)

    # Shaders can be deleted after linking (program retains them)
    gl.glDeleteShader(vs)
    gl.glDeleteShader(fs)

    return program


# ---------------------------------------------------------------------------
# Uniform helpers
# ---------------------------------------------------------------------------
def set_uniform_mat4(
    gl: QOpenGLFunctions_3_3_Core,
    program: int,
    name: str,
    matrix: NDArray[np.float32],
) -> None:
    """Upload a 4x4 matrix uniform. None-guarded on program handle."""
    if program is None or program == 0:
        return
    loc = gl.glGetUniformLocation(program, name.encode("utf-8") if isinstance(name, str) else name)
    if loc < 0:
        return  # Uniform not found or optimized out — not an error
    # Ensure contiguous C-order float32
    mat = np.ascontiguousarray(matrix, dtype=np.float32)
    gl.glUniformMatrix4fv(loc, 1, gl.GL_FALSE, mat)


def set_uniform_mat3(
    gl: QOpenGLFunctions_3_3_Core,
    program: int,
    name: str,
    matrix: NDArray[np.float32],
) -> None:
    """Upload a 3x3 matrix uniform. None-guarded on program handle."""
    if program is None or program == 0:
        return
    loc = gl.glGetUniformLocation(program, name.encode("utf-8") if isinstance(name, str) else name)
    if loc < 0:
        return
    mat = np.ascontiguousarray(matrix, dtype=np.float32)
    gl.glUniformMatrix3fv(loc, 1, gl.GL_FALSE, mat)


def set_uniform_vec3(
    gl: QOpenGLFunctions_3_3_Core,
    program: int,
    name: str,
    value: NDArray[np.float32],
) -> None:
    """Upload a vec3 uniform. None-guarded on program handle."""
    if program is None or program == 0:
        return
    loc = gl.glGetUniformLocation(program, name.encode("utf-8") if isinstance(name, str) else name)
    if loc < 0:
        return
    v = np.ascontiguousarray(value, dtype=np.float32).flatten()[:3]
    gl.glUniform3f(loc, float(v[0]), float(v[1]), float(v[2]))


def set_uniform_vec4(
    gl: QOpenGLFunctions_3_3_Core,
    program: int,
    name: str,
    value: NDArray[np.float32],
) -> None:
    """Upload a vec4 uniform. None-guarded on program handle."""
    if program is None or program == 0:
        return
    loc = gl.glGetUniformLocation(program, name.encode("utf-8") if isinstance(name, str) else name)
    if loc < 0:
        return
    v = np.ascontiguousarray(value, dtype=np.float32).flatten()[:4]
    gl.glUniform4f(loc, float(v[0]), float(v[1]), float(v[2]), float(v[3]))


def set_uniform_float(
    gl: QOpenGLFunctions_3_3_Core,
    program: int,
    name: str,
    value: float,
) -> None:
    """Upload a float uniform. None-guarded on program handle."""
    if program is None or program == 0:
        return
    loc = gl.glGetUniformLocation(program, name.encode("utf-8") if isinstance(name, str) else name)
    if loc < 0:
        return
    gl.glUniform1f(loc, value)


def set_uniform_int(
    gl: QOpenGLFunctions_3_3_Core,
    program: int,
    name: str,
    value: int,
) -> None:
    """Upload an int uniform. None-guarded on program handle."""
    if program is None or program == 0:
        return
    loc = gl.glGetUniformLocation(program, name.encode("utf-8") if isinstance(name, str) else name)
    if loc < 0:
        return
    gl.glUniform1i(loc, value)


# ---------------------------------------------------------------------------
# Matrix utilities
# ---------------------------------------------------------------------------
def compute_normal_matrix(
    model: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Extract 3x3 normal matrix from a 4x4 model matrix.

    The normal matrix is the transpose of the inverse of the upper-left
    3x3 of the model matrix. For orthogonal transforms (rotation only),
    this simplifies to the upper-left 3x3 itself.
    """
    mat3 = model[:3, :3].astype(np.float32)
    try:
        inv = np.linalg.inv(mat3)
        normal = np.ascontiguousarray(inv.T, dtype=np.float32)
    except np.linalg.LinAlgError:
        # Singular matrix — fall back to identity
        normal = np.eye(3, dtype=np.float32)
    return normal


# ---------------------------------------------------------------------------
# GL resource cleanup helpers
# ---------------------------------------------------------------------------
def safe_delete_buffers(
    gl: QOpenGLFunctions_3_3_Core,
    *buffers: Optional[int],
) -> None:
    """Delete one or more GL buffers, skipping None or 0 values."""
    valid = [b for b in buffers if b is not None and b != 0]
    if valid:
        bufs = (gl.GLuint * len(valid))(*valid)
        gl.glDeleteBuffers(len(valid), bufs)


def safe_delete_vertex_array(
    gl: QOpenGLFunctions_3_3_Core,
    vao: Optional[int],
) -> None:
    """Delete a VAO, skipping None or 0."""
    if vao is not None and vao != 0:
        gl.glDeleteVertexArrays(1, (gl.GLuint * 1)(vao))


def safe_delete_program(
    gl: QOpenGLFunctions_3_3_Core,
    program: Optional[int],
) -> None:
    """Delete a shader program, skipping None or 0."""
    if program is not None and program != 0:
        gl.glDeleteProgram(program)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _shader_type_name(shader_type: int) -> str:
    """Map GL shader type enum to readable name."""
    from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core as GLFuncs
    # We use the raw GL constants for mapping
    types = {
        0x8B31: "VERTEX_SHADER",
        0x8B30: "FRAGMENT_SHADER",
        0x8B40: "GEOMETRY_SHADER",
    }
    return types.get(shader_type, f"UNKNOWN(0x{shader_type:04X})")
