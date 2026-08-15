"""单位换算。纤维强度常用单位：力 cN/N/mN，直径 μm，线密度 dtex，密度 g/cm³。"""

CN_PER_N = 100.0      # 1 N = 100 cN
CN_PER_MN = 0.1       # 1 mN = 0.1 cN
UM_PER_M = 1e6        # 1 m = 1e6 μm
GCM3_PER_KGM3 = 1000.0  # 1 g/cm³ = 1000 kg/m³


def force_to_cn(value: float, unit: str) -> float:
    """把断裂强力换算为 cN。unit 仅接受 cN/N/mN。"""
    if unit == "cN":
        return value
    if unit == "N":
        return value * CN_PER_N
    if unit == "mN":
        return value * CN_PER_MN
    raise ValueError(f"未知的强力单位：{unit!r}（仅支持 cN/N/mN）")
