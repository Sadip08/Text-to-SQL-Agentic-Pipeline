# executor.py
import json
from groq import Groq
import os
import datetime
import re
from database import get_db_connection
from validator import SQLValidator
from psycopg2.extras import RealDictCursor

# --- IMPORT YOUR LLM CLIENT HERE ---
# Example: from openai import OpenAI
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "logs", "query_execution.log")

# Ensure runtime directory dependencies are created
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

class SQLExecutor:
    @staticmethod
    def log_transaction(sql_query: str, status: str, error_msg: str = "") -> None:
        """Appends comprehensive system transaction details to an append-only log file."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] STATUS: {status} | QUERY: {sql_query}"
        if error_msg:
            log_line += f" | ERROR DESCRIPTION: {error_msg}"
        
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

    @classmethod
    def execute_query(cls, sql_query: str, decomposition: dict = None) -> dict:
        """
        Runs SQL on the live database. Handles compilation failures via 
        an automated single-retry recovery pipeline using an LLM.
        """
        # Security Guardrail Check
        if not SQLValidator.verify_safety(sql_query):
            err_text = "Security Violation: Query attempted a non-SELECT write/mutation mutation."
            cls.log_transaction(sql_query, "BLOCKED", err_text)
            return {"status": "error", "error": err_text, "sql": sql_query, "retry_attempted": False}

        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(sql_query)
                    records = cursor.fetchall()
                    cls.log_transaction(sql_query, "SUCCESS")
                    return {"status": "success", "sql": sql_query, "result": records, "retry_attempted": False}
                    
        except Exception as primary_error:
            # Fallback Loop Trigger: Initiate Single Self-Correction Operation
            cls.log_transaction(sql_query, "FAILED_FIRST_PASS", str(primary_error))
            print(f"[System Diagnostic] Primary failure detected: {str(primary_error)}. Running fallback repair loop...")
            
            # Fire Approach A: LLM Self-Correction
            repaired_query = cls._attempt_query_repair(sql_query, str(primary_error), decomposition)
            print(f"[System Diagnostic] Repaired SQL Generated: {repaired_query}")
            
            # Re-verify the repaired statement against the security guardrails
            if not SQLValidator.verify_safety(repaired_query):
                err_text = "Security Violation: Repaired statement failed security validation check."
                cls.log_transaction(repaired_query, "BLOCKED_ON_RETRY", err_text)
                return {"status": "error", "error": err_text, "sql": repaired_query, "retry_attempted": True}
            
            try:
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        cursor.execute(repaired_query)
                        records = cursor.fetchall()
                        cls.log_transaction(repaired_query, "SUCCESS_AFTER_RETRY")
                        return {"status": "success", "sql": repaired_query, "result": records, "retry_attempted": True}
            except Exception as retry_error:
                cls.log_transaction(repaired_query, "CRITICAL_FAILURE", str(retry_error))
                return {
                    "status": "error",
                    "error": f"Retry Exception: {str(retry_error)}",
                    "sql": repaired_query,
                    "retry_attempted": True
                }
        
    @classmethod
    def _attempt_query_repair(cls, broken_sql: str, error_message: str, decomposition: dict) -> str:
        """
        Approach A: An LLM-powered prompt chaining routine using the free Groq SDK 
        to process engine feedback and automatically repair queries.
        """
        repair_system_prompt = (
            "You are an expert PostgreSQL Database Administrator and backend AI agent.\n"
            "Your sole task is to fix a broken SQL query based on the database error log and metadata provided.\n\n"
            "CRITICAL POSTGRESQL RULES:\n"
            "1. CASE-SENSITIVITY: PostgreSQL requires identifiers with mixed or uppercase letters (camelCase) "
            "to be strictly wrapped in double quotes. Example: customernumber -> \"customerNumber\".\n"
            "2. GROUP BY CONSTRAINT: If a query selects a categorical column (like \"country\") AND an aggregate "
            "function (like COUNT(\"customerNumber\")), you MUST append a matching 'GROUP BY' clause at the end.\n"
            "3. OUTPUT FORMAT: Return ONLY the raw, clean, executable SQL query string. Do NOT wrap it in "
            "markdown code blocks (such as ```sql), do not write explanations, and do not append conversational greetings."
        )
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        repair_user_prompt = f"""
        Failed SQL Query:
        {broken_sql}
        
        PostgreSQL Error Log Received:
        {error_message}
        
        Target Schema Context (Metadata Decomposition):
        {json.dumps(decomposition) if decomposition else "None"}
        
        Please correct the query using the CRITICAL POSTGRESQL RULES and output the fixed SQL statement string:
        """
        
        try:
            # Invoking Llama 3 70B via Groq's ultra-fast engine
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": repair_system_prompt},
                    {"role": "user", "content": repair_user_prompt}
                ],
                temperature=0.0
            )
            repaired_sql = response.choices[0].message.content.strip()
            
            print("\n" + "="*40)
            print(f"🔮 RAW LLM OUTPUT: {repaired_sql}")
            print("="*40 + "\n")
            # Defensive guardrail cleanups
            repaired_sql = repaired_sql.replace("```sql", "").replace("```", "").strip()
            if not repaired_sql.endswith(";"):
                repaired_sql += ";"
                
            return repaired_sql

        except Exception as api_err:
            print(f"[Diagnostic Failure] Groq self-correction call failed: {str(api_err)}")
            return broken_sql