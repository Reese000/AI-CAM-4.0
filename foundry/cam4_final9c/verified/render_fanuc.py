def render_fanuc(ir_segments: list[dict]) -> str:
    return "\n".join(
        f"{segment['cmd']} " +
        " ".join(f"{k.upper()}{v}" for k, v in segment.items() if k != 'cmd')
        for segment in ir_segments
    )