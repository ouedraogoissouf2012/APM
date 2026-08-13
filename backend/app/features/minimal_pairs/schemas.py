from pydantic import BaseModel

# Bound on router.py's manual check of the /attempt multipart `target`/`other`
# fields (#328) — both are single minimal-pair words (e.g. "ship"/"sheep"), so
# this is generous (matches profile.MAX_INTEREST_LENGTH's precedent for a
# short free-form word/phrase), not the phrase-length bound shadowing uses.
MAX_WORD_CHARS = 50


class PairAttemptOut(BaseModel):
    transcript: str
    said_target: bool
    said_other: bool
    coaching: str
