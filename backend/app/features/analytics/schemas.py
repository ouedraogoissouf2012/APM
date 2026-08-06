from pydantic import BaseModel


class AnalyticsSummaryOut(BaseModel):
    users_activated: int
    completions_total: int
    completions_this_week: int
    transfers_started_total: int
