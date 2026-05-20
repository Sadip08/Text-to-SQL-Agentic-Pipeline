# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union, Optional
from sql_generator import SQLGenerator
from executor import SQLExecutor
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Core Text-to-SQL Autonomous Backend",
    description="A secure FastAPI service for automated text-to-SQL generation and query execution"
)

class DecompositionPayload(BaseModel):
    question: str
    Intent: str
    Tables: Union[str, List[str]]
    Columns: Union[str, List[str]]
    Filters: Optional[str] = "None"
    Joins: Optional[Union[str, List[str]]] = "None"

@app.post("/api/v1/execute-text2sql", response_model=dict)
async def process_text_to_sql_transaction(payload: DecompositionPayload):
    """
    Accepts structured query decompositions, converts them into valid SQL statements, 
    safely executes them against PostgreSQL, and returns structured data results.
    """
    decomposition_dict = payload.dict()
    
    try:
        # Step 1: Generate valid SQL query string from decomposition parameters
        generated_sql = SQLGenerator.generate_from_decomposition(decomposition_dict)
        
        # Step 2: Execute query via the self-healing transaction runtime
        execution_response = SQLExecutor.execute_query(generated_sql, decomposition_dict)
        
        # Step 3: Format and return the structured JSON payload
        return {
            "question": payload.question,
            "sql": execution_response["sql"],
            "result": execution_response.get("result", []),
            "status": execution_response["status"],
            "meta": {
                "retry_applied": execution_response["retry_attempted"],
                "error_log": execution_response.get("error", None)
            }
        }
        
    except Exception as system_exception:
        raise HTTPException(
            status_code=500, 
            detail=f"Pipeline Processing Exception Interception: {str(system_exception)}"
        )
    
if __name__ == "__main__":
    import uvicorn
    # Launch backend server pipeline
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)