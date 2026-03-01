"""
Off-season analysis tools.

- Contract expiration tracker
- Keeper analysis (who to keep vs drop)
- Cap space projections
- Draft/auction value calculator
"""
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.valuation import age_curve_multiplier


@dataclass
class ContractStatus:
    name: str
    salary: float
    contract: str
    years_remaining: int
    is_expiring: bool
    z_total: float
    z_per_dollar: float
    age: int
    recommendation: str  # "must_keep", "keep", "tradeable", "drop_candidate"
    reason: str


@dataclass
class CapProjection:
    current_salary_total: float
    salary_cap: float
    cap_room: float
    expiring_salary: float        # Salary coming off the books
    committed_salary: float       # Salary locked in for next year
    projected_cap_room: float     # Cap room after expirations
    num_expiring: int
    num_kept: int


def analyze_contracts(z_df: pd.DataFrame, salary_cap: float = 200.0) -> dict:
    """
    Full contract analysis for off-season planning.

    Returns:
        - expiring: players whose contracts expire
        - keepers: recommended keepers sorted by value
        - drop_candidates: players to consider not re-signing
        - cap_projection: projected cap situation
    """
    contracts = []

    for _, row in z_df.iterrows():
        name = row.get("name", "")
        salary = row.get("salary", 0)
        z_total = row.get("z_total", 0)
        yrs = int(row.get("years_remaining", 1))
        age = int(row.get("age", 0))
        contract = row.get("contract", "")
        is_expiring = yrs <= 1
        z_per_dollar = z_total / max(salary, 0.5)

        # Recommendation logic
        if z_total > 4 and z_per_dollar > 0.5:
            rec = "must_keep"
            reason = f"Elite production (z:{z_total:+.1f}) at good value (z/$:{z_per_dollar:.1f})"
        elif z_total > 2 and z_per_dollar > 0:
            rec = "keep"
            reason = f"Solid contributor (z:{z_total:+.1f})"
        elif z_total > 0 and salary <= 3:
            rec = "keep"
            reason = f"Cheap positive value (${salary:.0f}, z:{z_total:+.1f})"
        elif z_total < -2 or (z_total < 0 and salary > 5):
            rec = "drop_candidate"
            reason = f"Negative value (z:{z_total:+.1f}) at ${salary:.0f}"
        else:
            rec = "tradeable"
            reason = f"Marginal value (z:{z_total:+.1f}, ${salary:.0f})"

        # Age adjustment for dynasty
        if age > 0:
            af = age_curve_multiplier(age)
            if af < 0.6 and z_total > 0:
                rec = "tradeable"
                reason += f" — aging (age {age})"
            elif af > 1.1 and z_total > 0:
                if rec != "must_keep":
                    rec = "keep"
                reason += f" — young upside (age {age})"

        contracts.append(ContractStatus(
            name=name, salary=salary, contract=contract,
            years_remaining=yrs, is_expiring=is_expiring,
            z_total=round(z_total, 2),
            z_per_dollar=round(z_per_dollar, 2),
            age=age, recommendation=rec, reason=reason,
        ))

    # Separate by category
    expiring = [c for c in contracts if c.is_expiring]
    keepers = sorted(
        [c for c in contracts if c.recommendation in ("must_keep", "keep")],
        key=lambda c: c.z_total, reverse=True,
    )
    drop_candidates = sorted(
        [c for c in contracts if c.recommendation == "drop_candidate"],
        key=lambda c: c.z_total,
    )
    tradeable = sorted(
        [c for c in contracts if c.recommendation == "tradeable"],
        key=lambda c: c.z_per_dollar, reverse=True,
    )

    # Cap projection
    current_total = sum(c.salary for c in contracts)
    expiring_salary = sum(c.salary for c in expiring)
    committed = current_total - expiring_salary
    # Assume keepers from expiring are re-signed at same salary
    keeper_expiring = [c for c in expiring if c.recommendation in ("must_keep", "keep")]
    re_sign_cost = sum(c.salary for c in keeper_expiring)

    cap_proj = CapProjection(
        current_salary_total=round(current_total, 2),
        salary_cap=salary_cap,
        cap_room=round(salary_cap - current_total, 2),
        expiring_salary=round(expiring_salary, 2),
        committed_salary=round(committed, 2),
        projected_cap_room=round(salary_cap - committed - re_sign_cost, 2),
        num_expiring=len(expiring),
        num_kept=len(keeper_expiring),
    )

    return {
        "all_contracts": contracts,
        "expiring": expiring,
        "keepers": keepers,
        "drop_candidates": drop_candidates,
        "tradeable": tradeable,
        "cap_projection": cap_proj,
    }


def format_offseason_report(analysis: dict) -> str:
    """Format off-season analysis as a readable report."""
    lines = []
    cap = analysis["cap_projection"]

    lines.append("=" * 100)
    lines.append("OFF-SEASON CONTRACT ANALYSIS")
    lines.append("=" * 100)

    # Cap situation
    lines.append(f"\n  CAP SITUATION:")
    lines.append(f"    Current salary:    ${cap.current_salary_total:.1f} / ${cap.salary_cap:.1f}")
    lines.append(f"    Current cap room:  ${cap.cap_room:.1f}")
    lines.append(f"    Expiring salary:   ${cap.expiring_salary:.1f} ({cap.num_expiring} players)")
    lines.append(f"    Committed:         ${cap.committed_salary:.1f}")
    lines.append(f"    Projected room:    ${cap.projected_cap_room:.1f} (after re-signing {cap.num_kept} keepers)")

    # Must keeps
    lines.append(f"\n  MUST KEEP ({len([c for c in analysis['keepers'] if c.recommendation == 'must_keep'])}):")
    for c in analysis["keepers"]:
        if c.recommendation == "must_keep":
            exp = " [EXPIRING]" if c.is_expiring else f" [{c.years_remaining}yr]"
            lines.append(f"    {c.name:25s}  ${c.salary:5.1f}  z:{c.z_total:+5.1f}  z/$:{c.z_per_dollar:+.1f}{exp}")

    # Keepers
    keep_only = [c for c in analysis["keepers"] if c.recommendation == "keep"]
    lines.append(f"\n  KEEP ({len(keep_only)}):")
    for c in keep_only:
        exp = " [EXPIRING]" if c.is_expiring else f" [{c.years_remaining}yr]"
        lines.append(f"    {c.name:25s}  ${c.salary:5.1f}  z:{c.z_total:+5.1f}  z/$:{c.z_per_dollar:+.1f}{exp}")

    # Tradeable
    lines.append(f"\n  TRADEABLE ({len(analysis['tradeable'])}):")
    for c in analysis["tradeable"]:
        exp = " [EXPIRING]" if c.is_expiring else f" [{c.years_remaining}yr]"
        lines.append(f"    {c.name:25s}  ${c.salary:5.1f}  z:{c.z_total:+5.1f}  {c.reason[:40]}{exp}")

    # Drop candidates
    lines.append(f"\n  DROP CANDIDATES ({len(analysis['drop_candidates'])}):")
    for c in analysis["drop_candidates"]:
        exp = " [EXPIRING]" if c.is_expiring else f" [{c.years_remaining}yr]"
        lines.append(f"    {c.name:25s}  ${c.salary:5.1f}  z:{c.z_total:+5.1f}  {c.reason[:40]}{exp}")

    return "\n".join(lines)
