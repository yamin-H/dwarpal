from fastapi.concurrency import run_in_threadpool

from app.core.errors import ApiError


class BudgetError(ApiError):
    def __init__(self, status: int, message: str, code: str, type_: str, kind: str) -> None:
        super().__init__(status, message, code, type_)
        self.kind = kind


async def enforce_budget(store, prices, tenant, model: str) -> None:
    """Soft cap: blocks once usage has reached the budget, so the last request can overshoot."""
    if tenant.monthly_token_budget is None and tenant.monthly_cost_budget_micros is None:
        return
    if tenant.monthly_cost_budget_micros is not None and not prices.knows(model):
        raise BudgetError(
            403,
            f"Model '{model}' has no configured price, so this tenant's cost budget "
            "cannot be enforced.",
            "model_not_priced", "permission_error", "unpriced",
        )
    tokens, cost = await run_in_threadpool(store.month_usage, tenant.id)
    if tenant.monthly_token_budget is not None and tokens >= tenant.monthly_token_budget:
        raise BudgetError(
            429, "Monthly token budget exceeded.", "budget_exceeded", "rate_limit_error", "tokens"
        )
    if tenant.monthly_cost_budget_micros is not None and cost >= tenant.monthly_cost_budget_micros:
        raise BudgetError(
            429, "Monthly cost budget exceeded.", "budget_exceeded", "rate_limit_error", "cost"
        )