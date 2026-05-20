# main.py
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union, Optional
from sql_generator import SQLGenerator
from executor import SQLExecutor
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

# Initialize core FastAPI application with secure configurations
app = FastAPI(
    title="Core Text-to-SQL Autonomous Backend",
    description="A secure FastAPI service for automated text-to-SQL generation, agentic self-correction, and natural language summarization.",
    version="1.0.0"
)

# Initialize the production Groq client
client = Groq()

# ================================================================================
# REQUEST SCHEMAS (PYDANTIC MODELS)
# ================================================================================

class DecompositionPayload(BaseModel):
    """Schema for manual/structured query decomposition processing."""
    question: str
    Intent: str
    Tables: Union[str, List[str]]
    Columns: Union[str, List[str]]
    Filters: Optional[str] = "None"
    Joins: Optional[Union[str, List[str]]] = "None"

class AgentRequest(BaseModel):
    """Official Task 4 Schema: Accepts a single natural language question string."""
    question: str


# ================================================================================
# HELPER CORE LOGIC: SUMMARY GENERATION ENGINE (STEP 5)
# ================================================================================

def generate_natural_language_summary(question: str, db_result: list) -> str:
    """
    Converts raw database record sets into a polished business intelligence natural language summary sentence.
    """
    if not db_result:
        return "No matching records were found in the database to answer this question."

    summary_prompt = (
        "You are an expert business intelligence data analyst.\n"
        "Your sole objective is to convert raw database record sets into a direct natural language summary sentence.\n\n"
        f"Original User Question: '{question}'\n"
        f"Raw Executed DB Records: {db_result}\n\n"
        "Instructions:\n"
        "1. Formulate a clear, direct, and factual 1-sentence summary answering the user's question explicitly based on the metrics provided.\n"
        "2. Do not provide conversational introductions (like 'Sure, here is the summary'), markdown formatting, or descriptive filler text."
    )
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as summary_err:
        # Graceful fallback to prevent pipeline crashes if the external LLM API experiences latency
        return f"Data Summary (Fallback Trace): {str(db_result)}"


# ================================================================================
# ROUTE 1: OFFICIAL TASK 4 AUTONOMOUS MINI SQL AGENT ENDPOINT
# ================================================================================

@app.post("/agent/sql", response_model=dict)
async def run_autonomous_sql_agent(payload: AgentRequest):
    """
    TASK 4 PRIMARY ENDPOINT: Fully autonomous agentic data assistant loop.
    Accepts a single raw question string, executes understanding, multi-turn self-healing, 
    and synthesizes a natural human answer response block.
    """
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question parameter cannot be empty.")
        
    # Trigger the agentic execution engine loop (implements steps 1 through 4 internally)
    agent_execution = SQLExecutor.execute_agent_loop(payload.question)
    
    # Handle critical exhaustion states safely
    if agent_execution.get("status") == "error":
        return {
            "sql": agent_execution.get("sql", ""),
            "result": None,
            "summary": f"Could not process request. Agent Error: {agent_execution.get('error', 'Unknown Failure')}",
            "status": "failed"
        }
        
    # Generate Step 5 Natural Language Summary from successful data records
    records = agent_execution.get("result", [])
    nl_summary = generate_natural_language_summary(payload.question, records)
    
    return {
        "sql": agent_execution.get("sql", ""),
        "result": records,
        "summary": nl_summary,
        "status": "success"
    }


# ================================================================================
# ROUTE 2: COMPATIBILITY BACKWARD TRANSACTIONS ENDPOINT
# ================================================================================

@app.post("/api/v1/execute-text2sql", response_model=dict)
async def process_text_to_sql_transaction(payload: DecompositionPayload):
    """
    Accepts structured query decompositions, routes requests through the 
    self-healing loop wrapper, and outputs structured analytical responses.
    """
    try:
        # Route query through the self-healing multi-attempt executor runtime
        execution_response = SQLExecutor.execute_agent_loop(payload.question)
        
        # Guardrail default summary text
        summary_text = "Could not process summary due to preceding query execution failure."
        
        if execution_response.get("status") == "success":
            records_data = execution_response.get("result", [])
            summary_text = generate_natural_language_summary(payload.question, records_data)
        
        # Return structured JSON matching expected evaluation pipeline shapes
        return {
            "question": payload.question,
            "sql": execution_response.get("sql", ""),
            "result": execution_response.get("result", []),
            "summary": summary_text,
            "status": execution_response.get("status", "error"),
            "meta": {
                "retry_applied": execution_response.get("retry_applied", True if execution_response.get("retry_attempted", 0) > 0 else False),
                "error_log": execution_response.get("error", None)
            }
        }
        
    except Exception as system_exception:
        raise HTTPException(
            status_code=500, 
            detail=f"Pipeline Processing Exception Interception: {str(system_exception)}"
        )


# ================================================================================
# APPLICATION EXECUTION SITE
# ================================================================================

if __name__ == "__main__":
    import uvicorn
    # Launch backend server pipeline locally
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)