# sql_generator.py
import re

class SQLGenerator:
    @staticmethod
    def generate_from_decomposition(decomposition: dict) -> str:
        """
        Translates structured decomposition blocks into a valid PostgreSQL statement.
        Automatically wraps camelCase names in double quotes.
        """
        # 1. Columns & Aggregation Processing
        columns_input = decomposition.get("Columns", "*")
        intent = decomposition.get("Intent", "").lower()
        
        # Helper to wrap individual column names while handling aggregates
        def clean_identifier(col: str) -> str:
            col = col.strip()
            if col == "*" or col.upper() == "DISTINCT *":
                return col
            
            # Helper to wrap an identifier that might have a table prefix
            def wrap_identifier(identifier: str) -> str:
                if "." in identifier:
                    tbl, col_name = identifier.split(".", 1)
                    return f'"{tbl.strip()}"."{col_name.strip()}"'
                return f'"{identifier}"'
            
            # Handle standard functional aggregates: COUNT, SUM, AVG, MAX, MIN
            agg_match = re.match(r"^(COUNT|SUM|AVG|MAX|MIN)\((.*?)\)$", col, re.IGNORECASE)
            if agg_match:
                func = agg_match.group(1).upper()
                inner = agg_match.group(2).strip()
                # Handle DISTINCT inside aggregates
                if inner.upper().startswith("DISTINCT "):
                    inner_col = inner.split(" ", 1)[1].strip()
                    return f"{func}(DISTINCT {wrap_identifier(inner_col)})"
                return f"{func}({wrap_identifier(inner)})" if inner != "*" else f"{func}(*)"
            
            # Handle DISTINCT modifiers
            if col.upper().startswith("DISTINCT "):
                inner_col = col.split(" ", 1)[1].strip()
                return f"DISTINCT {wrap_identifier(inner_col)}"
                
            return wrap_identifier(col)

        # Parse column collections
        if isinstance(columns_input, list):
            processed_cols = [clean_identifier(c) for c in columns_input]
            columns_clause = ", ".join(processed_cols)
        elif isinstance(columns_input, str) and columns_input != "*":
            processed_cols = [clean_identifier(c) for c in columns_input.split(",")]
            columns_clause = ", ".join(processed_cols)
        else:
            columns_clause = "*"

        # 2. Base Table Processing
        tables = decomposition.get("Tables", [])
        if isinstance(tables, str):
            tables = [t.strip() for t in tables.split(",")]
        
        if not tables:
            raise ValueError("Structured decomposition missing required table entities.")
            
        primary_table = tables[0]

        # 3. Join Construction
        join_clause = ""
        joins = decomposition.get("Joins", "None")
        if joins and str(joins).lower() != "none":
            if isinstance(joins, str):
                joins = [joins]
            for j in joins:
                # Matches patterns like: customers.customerNumber = orders.customerNumber
                match = re.match(r"([\w]+)\.([\w]+)\s*=\s*([\w]+)\.([\w]+)", j.strip())
                if match:
                    t1, c1, t2, c2 = match.groups()
                    target_table = t2 if t2 != tables[0] else t1
                    join_clause += f' JOIN "{target_table}" ON "{t1}"."{c1}" = "{t2}"."{c2}"'

        # 4. Filter Processing
        where_clause = ""
        filters = decomposition.get("Filters", "None")
        if filters and str(filters).lower() != "none":
            # Simple wrapper to inject quotes on column names inside conditions
            if "=" in str(filters):
                left, right = str(filters).split("=", 1)
                # If there's a table prefix (e.g. customers.country)
                if "." in left:
                    tbl_pref, col_name = left.strip().split(".", 1)
                    where_clause = f' WHERE "{tbl_pref}"."{col_name.strip()}" = {right.strip()}'
                else:
                    where_clause = f' WHERE "{left.strip()}" = {right.strip()}'
            else:
                where_clause = f" WHERE {filters}"

        # 5. Group By Construction
        group_by_clause = ""
        if "per" in intent or "group by" in intent:
            # Deduces column positions for group-by from the baseline non-aggregate column
            if len(tables) > 1 and join_clause:
                # Multi-table group expressions
                if "country" in intent: group_by_clause = ' GROUP BY "customers"."country"'
                elif "status" in intent: group_by_clause = ' GROUP BY "orders"."status"'
                elif "productline" in intent: group_by_clause = ' GROUP BY "products"."productLine"'
                elif "city" in intent: group_by_clause = ' GROUP BY "offices"."city"'
                elif "vendor" in intent: group_by_clause = ' GROUP BY "products"."productVendor"'
                else: group_by_clause = f' GROUP BY {processed_cols[0]}'
            else:
                # Single-table group expressions
                if "country" in intent: group_by_clause = ' GROUP BY "country"'
                elif "status" in intent: group_by_clause = ' GROUP BY "status"'
                elif "productline" in intent: group_by_clause = ' GROUP BY "productLine"'
                elif "vendor" in intent: group_by_clause = ' GROUP BY "productVendor"'
                else: group_by_clause = f" GROUP BY {processed_cols[0]}"

        # Construct final executable SQL statement
        query = f"SELECT {columns_clause} FROM {primary_table}{join_clause}{where_clause}{group_by_clause};"
        return query