"""
Player valuation for salary cap dynasty leagues.

Computes:
- z-score per salary dollar
- Surplus value (actual z vs expected z for salary level)
- Dynasty value (age-curve adjusted, contract-length weighted)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class PlayerValuation:
    name: str
    salary: float
    age: int
    years_remaining: int
    z_total: float
    z_per_dollar: float
    surplus_value: float
    dynasty_value: float
    age_factor: float
    category_zscores: dict[str, float] = field(default_factory=dict)


def age_curve_multiplier(age: int) -> float:
    """NBA age curve for dynasty valuation."""
    if age <= 22:
        return 1.15   # Still developing, upside
    elif age <= 25:
        return 1.25   # Approaching prime
    elif age <= 28:
        return 1.10   # Prime
    elif age <= 30:
        return 0.95   # Starting decline
    elif age <= 32:
        return 0.75   # Declining
    elif age <= 34:
        return 0.55   # End of career
    else:
        return 0.35   # LeBron exception territory


def compute_valuations(
    z_df: pd.DataFrame,
    salary_col: str = "salary",
    age_col: str = "age",
    years_col: str = "years_remaining",
) -> pd.DataFrame:
    """
    Compute player valuations from z-scores and contract data.

    Input z_df must have: name, z_total, salary, age, years_remaining,
    and z_<cat> columns for each category.

    Adds columns: z_per_dollar, surplus_value, age_factor, dynasty_value
    """
    df = z_df.copy()

    # Z per dollar
    df["z_per_dollar"] = df["z_total"] / df[salary_col].clip(lower=0.5)

    # Surplus value: regression of z_total ~ salary across the pool
    # Expected z = a * salary + b
    valid = df[(df["z_total"].notna()) & (df[salary_col] > 0)]
    if len(valid) >= 3:
        coeffs = np.polyfit(valid[salary_col], valid["z_total"], deg=1)
        df["expected_z"] = np.polyval(coeffs, df[salary_col])
    else:
        df["expected_z"] = 0.0
    df["surplus_value"] = df["z_total"] - df["expected_z"]

    # Age factor
    df["age_factor"] = df[age_col].apply(age_curve_multiplier)

    # Dynasty value: production * age trajectory * contract length
    # Normalize: 3-year contract = 1.0x, 1-year = 0.33x, capped at 1.5x
    contract_factor = (df[years_col] / 3.0).clip(upper=1.5)
    df["dynasty_value"] = df["z_total"] * df["age_factor"] * contract_factor

    return df


def format_valuations_report(df: pd.DataFrame) -> str:
    """Format a valuations DataFrame as a readable report."""
    lines = []
    lines.append("=" * 110)
    lines.append("PLAYER VALUATIONS (Dynasty Salary Cap)")
    lines.append("=" * 110)
    lines.append(
        f"  {'Name':25s}  {'$':>5s}  {'Age':>3s}  {'Yrs':>3s}  "
        f"{'Z-Tot':>6s}  {'Z/$':>6s}  {'Surplus':>7s}  "
        f"{'AgeFctr':>7s}  {'Dynasty':>7s}"
    )
    lines.append("-" * 110)

    sorted_df = df.sort_values("dynasty_value", ascending=False)
    for _, row in sorted_df.iterrows():
        lines.append(
            f"  {row['name']:25s}  {row['salary']:5.1f}  {int(row['age']):3d}  "
            f"{int(row.get('years_remaining', 1)):3d}  "
            f"{row['z_total']:+6.2f}  {row['z_per_dollar']:+6.2f}  "
            f"{row['surplus_value']:+7.2f}  "
            f"{row['age_factor']:7.2f}  {row['dynasty_value']:+7.2f}"
        )

    return "\n".join(lines)
