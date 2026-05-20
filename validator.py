# validator.py
import re

class SQLValidator:
    # Explicit destructive mutations that must be intercepted
    FORBIDDEN_KEYWORDS = re.compile(
        r"\b(DELETE|DROP|UPDATE|INSERT|TRUNCATE|ALTER|GRANT|REVOKE|EXECUTE)\b", 
        re.IGNORECASE
    )

    @classmethod
    def verify_safety(cls, sql_query: str) -> bool:
        """
        Enforces read-only compliance. Returns True if transaction passes verification, 
        and False if forbidden keywords are identified.
        """
        cleaned_query = sql_query.strip()
        
        # Guardrail 1: Enforce strict SELECT statement declaration rule
        if not cleaned_query.upper().startswith("SELECT"):
            return False
            
        # Guardrail 2: Ensure no mutating keywords are injected inside the query body
        if cls.FORBIDDEN_KEYWORDS.search(cleaned_query):
            return False
            
        return True