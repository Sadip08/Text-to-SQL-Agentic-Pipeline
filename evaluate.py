# evaluate.py
import requests
import json
import time

# URL of your running FastAPI server
API_URL = "http://127.0.0.1:8000/api/v1/execute-text2sql"

# 1. Text-to-SQL Benchmark Dataset (Task 2 Structured Decompositions)
BENCHMARK_DATASET = [
    {
        "question": "Show all customer names and cities",
        "Intent": "Extract name and geographic distribution attributes from the customer roster",
        "Tables": ["customers"],
        "Columns": ["customerName", "city"],
        "Filters": "None",
        "Joins": "None"
    },
    {
        "question": "Number of orders per status",
        "Intent": "Count total orders grouped per individual logistics status",
        "Tables": ["orders"],
        "Columns": ["status", "COUNT(orderNumber)"],
        "Filters": "None",
        "Joins": "None"
    },
    {
        "question": "Show all orders placed by customers in Germany",
        "Intent": "Retrieve orders paired with customer context filtered by country",
        "Tables": ["orders", "customers"],
        "Columns": ["orders.orderNumber", "customers.customerName"],
        "Filters": "customers.country = 'Germany'",
        "Joins": ["customers.customerNumber = orders.customerNumber"]
    },
    {
        "question": "Total payments per customer",
        "Intent": "Calculate cumulative historical financial amount per customer account",
        "Tables": ["payments", "customers"],
        "Columns": ["customers.customerName", "SUM(payments.amount)"],
        "Filters": "None",
        "Joins": ["payments.customerNumber = customers.customerNumber"]
    },
    {
        "question": "Count customers per country (Test Case for Case-Insensitive Retry)",
        "Intent": "Aggregate distribution tracking by nation with intentional lower-case column mismatch",
        "Tables": ["customers"],
        "Columns": ["country", "COUNT(customernumber)"],  # Intentional lowercase to trigger self-correction
        "Filters": "None",
        "Joins": "None"
    }
]

def run_evaluation():
    print("=" * 90)
    print("🚀 STARTING AUTOMATED TEXT-TO-SQL BENCHMARK EVALUATION RUN")
    print("=" * 90)
    
    evaluation_results = []
    success_count = 0
    retry_count = 0
    
    for idx, payload in enumerate(BENCHMARK_DATASET, 1):
        print(f"\n[Case #{idx}] Evaluating: '{payload['question']}'")
        
        start_time = time.time()
        try:
            response = requests.post(API_URL, json=payload, timeout=10)
            latency = round((time.time() - start_time) * 1000, 2)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                sql = data.get("sql")
                retry_applied = data.get("meta", {}).get("retry_applied", False)
                error_log = data.get("meta", {}).get("error_log")
                
                executed_successfully = "Yes" if status == "success" else "No"
                correct_result = "Yes" if status == "success" else f"No (Error: {error_log})"
                retry_needed = "Yes" if retry_applied else "No"
                final_status = "Success" if status == "success" else "Failed"
                
                if status == "success":
                    success_count += 1
                if retry_applied:
                    retry_count += 1
                    correct_result = "Fixed After Retry" if status == "success" else "Failed After Retry"
                
                evaluation_results.append({
                    "Question": payload["question"],
                    "Generated SQL": sql,
                    "Executed Successfully": executed_successfully,
                    "Correct Result": correct_result,
                    "Retry Needed": retry_needed,
                    "Final Status": final_status,
                    "Latency (ms)": latency
                })
                print(f" -> Status: {final_status} | Retry Applied: {retry_needed} | Latency: {latency}ms")
            else:
                print(f" ❌ Server returned unexpected error status: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print(" ❌ Connection Error: Ensure your FastAPI server application is running on port 8000!")
            return

    # 2. Print Summary Report Table (Formatted as requested by the assignment)
    print("\n" + "=" * 120)
    print("📊 FINAL EXPECTED EVALUATION OUTPUT TABLE")
    print("=" * 120)
    header_fmt = "{:<45} | {:<25} | {:<12} | {:<18} | {:<12} | {:<10}"
    print(header_fmt.format("Question", "Executed Successfully", "Correct Result", "Retry Needed", "Final Status", "Latency"))
    print("-" * 120)
    
    for res in evaluation_results:
        # Truncate long SQL queries to make the terminal view clean
        sql_summary = res["Generated SQL"][:22] + "..." if len(res["Generated SQL"]) > 25 else res["Generated SQL"]
        print(header_fmt.format(
            res["Question"][:43],
            res["Executed Successfully"],
            res["Correct Result"],
            res["Retry Needed"],
            res["Final Status"],
            f"{res['Latency (ms)']}ms"
        ))
        
    print("=" * 120)
    # Metric Calculations
    total_queries = len(BENCHMARK_DATASET)
    print(f"📈 SQL Execution Success Rate       : {round((success_count / total_queries) * 100, 2)}%")
    print(f"🔄 Agentic Self-Correction Rate     : {round((retry_count / total_queries) * 100, 2)}%")
    print(f"❌ Total Critical Failures Remaining : {total_queries - success_count}")
    print("=" * 120)

if __name__ == "__main__":
    run_evaluation()