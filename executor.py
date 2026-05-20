# executor.py
import os
import time
import json
import datetime
from database import get_db_connection
from validator import SQLValidator
from psycopg2.extras import RealDictCursor
from groq import Groq

# Initialize the production Groq client
client = Groq()

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "logs", "query_execution.log")
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

class SQLExecutor:
    @staticmethod
    def log_transaction(category: str, data: str) -> None:
        """Appends explicit agent logs for decomposition, generation, or execution metrics."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{category.upper()}] {data}\n"
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)

    @classmethod
    def execute_agent_loop(cls, question: str) -> dict:
        """
        Implements Step 1 through Step 5 of the Required Agent Flow.
        Handles safe generation, strict verification, and a 3-attempt recovery cycle.
        """
        # --- STEP 1 & 2: UNDERSTAND QUERY & GENERATE SQL ---
        system_prompt = (
            "You are an elite PostgreSQL DBA agent. Your job is to analyze a question and generate accurate SQL.\n\n"
            "TARGET SCHEMA CONTEXT:\n"
            "- Table 'customers': columns [customerNumber, customerName, city, country]\n"
            "- Table 'orders': columns [orderNumber, orderDate, status, customerNumber]\n"
            "- Table 'payments': columns [customerNumber, checkNumber, paymentDate, amount]\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. Wrap mixed-case columns in double quotes strictly. Example: \"customerNumber\", \"customerName\".\n"
            "2. Ensure any non-aggregated column in a multi-column aggregation has a matching GROUP BY statement.\n"
            "3. Output a strict JSON object with EXACTLY two keys: 'decomposition' (a text string detailing your structural plan) "
            "and 'sql' (the pure executable SQL query string ending in a semicolon). Do not wrap inside code block markdown."
        )

        user_prompt = f"User Question: '{question}'. Generate the decomposition trace and SQL string following the rules."

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0
            )
            raw_output = response.choices[0].message.content.strip()
            
            # Defensive markdown strip if model misbehaves
            if raw_output.startswith("```json"):
                raw_output = raw_output.replace("```json", "").replace("```", "").strip()
            
            payload = json.loads(raw_output)
            current_sql = payload.get("sql", "").strip()
            decomposition_trace = payload.get("decomposition", "No plan provided.")
        except Exception as gen_err:
            cls.log_transaction("error", f"Initial generation failed parsing: {str(gen_err)}")
            return {"status": "error", "error": "Failed initial generation", "sql": ""}

        # Log initial metadata steps
        cls.log_transaction("decomposition", f"Question: {question} | Plan: {decomposition_trace}")
        cls.log_transaction("sql_generation", f"Initial Draft SQL: {current_sql}")

        # --- STEP 3 & 4: EXECUTE WITH AUTONOMOUS 3x RETRY LOOP ---
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            print(f"[Agent Process] Execution attempt {attempt} of {max_attempts}...")
            
            # Security Guardrail Check
            if not SQLValidator.verify_safety(current_sql):
                err_msg = "Security Violation: Non-SELECT or write operation intercepted."
                cls.log_transaction("blocked", f"Query blocked on attempt {attempt}: {current_sql}")
                return {"status": "error", "error": err_msg, "sql": current_sql}

            start_time = time.time()
            try:
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        cursor.execute(current_sql)
                        records = cursor.fetchall()
                        execution_time = (time.time() - start_time) * 1000
                        
                        # Log success metrics
                        cls.log_transaction("execution_time", f"Query succeeded in {execution_time:.2f}ms")
                        cls.log_transaction("execution_success", f"SQL Run: {current_sql}")
                        
                        return {
                            "status": "success",
                            "sql": current_sql,
                            "result": records,
                            "execution_time_ms": round(execution_time, 2),
                            "decomposition": decomposition_trace
                        }
            except Exception as db_error:
                execution_time = (time.time() - start_time) * 1000
                error_msg = str(db_error).strip()
                cls.log_transaction("failed_attempt", f"Attempt {attempt} failed in {execution_time:.2f}ms. Error: {error_msg}")
                
                # If it's our last attempt, break and drop to fallback
                if attempt == max_attempts:
                    break
                
                # Run dynamic query healing prompt chaining
                current_sql = cls._heal_query_with_llm(current_sql, error_msg, decomposition_trace)
                cls.log_transaction("sql_self_correction", f"Healed SQL generated for attempt {attempt+1}: {current_sql}")

        # --- STEP 4 FALLBACK RESPONSE IF ALL RETRIES FAIL ---
        cls.log_transaction("critical_failure", f"All {max_attempts} retries completely exhausted for question: {question}")
        return {
            "status": "error",
            "error": "All agent self-correction retries were completely exhausted without compiling successfully.", 
            "sql": current_sql
        }

    @classmethod
    def _heal_query_with_llm(cls, broken_sql: str, error_message: str, plan: str) -> str:
        """Asks the agent to reconsider its structure based on error logs from the engine."""
        repair_prompt = (
            f"You are a PostgreSQL expert fixer agent. A generated query has failed execution.\n\n"
            f"Broken Query: {broken_sql}\n"
            f"Engine Error: {error_message}\n"
            f"Original Plan Intent: {plan}\n\n"
            f"Fix the error by checking camelCase double quoting requirements or missing GROUP BY statements.\n"
            f"Return ONLY the plain text fixed SQL query string. Do not use code blocks or text chat."
        )
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": repair_prompt}],
                temperature=0.0
            )
            repaired = response.choices[0].message.content.strip()
            repaired = repaired.replace("```sql", "").replace("```", "").strip()
            if not repaired.endswith(";"):
                repaired += ";"
            return repaired
        except Exception:
            return broken_sql