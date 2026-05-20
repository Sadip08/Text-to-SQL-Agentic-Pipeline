# evaluate_agent.py
import requests
import json

TARGET_URL = "http://127.0.0.1:8000/agent/sql"

TEST_QUESTIONS = [
    "How many shipped orders are from USA customers?",
    "List all unique cities where customers live in Germany.",
    "What is the total amount paid by customer number 124?",
    "Show the order date and status for all orders placed by customers in France.",
    "Count the total number of customers per country."
]

print("🚀 Starting Autonomous Mini SQL Agent Evaluation Run...")
print("=" * 70)

for idx, question in enumerate(TEST_QUESTIONS, 1):
    print(f"\n[Test Case #{idx}] Question: '{question}'")
    try:
        response = requests.post(TARGET_URL, json={"question": question})
        if response.status_code == 200:
            data = response.json()
            print(f"  ✨ Status:  {data.get('status').upper()}")
            print(f"  💻 Generated SQL: {data.get('sql')}")
            print(f"  📊 DB Records:    {data.get('result')}")
            print(f"  📝 Summary:       {data.get('summary')}")
        else:
            print(f"  ❌ Failed with status code: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Connection Error: {str(e)}")
    print("-" * 70)

print("\n✅ Evaluation complete. Check your 'logs/query_execution.log' to view the internal agentic decomposition traces!")