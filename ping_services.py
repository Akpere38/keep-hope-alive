import os
import sys
import re
import urllib.request
import urllib.error
import json

TIMEOUT = 20

def read_lines(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️ Warning: File {filepath} not found.")
        return []
    lines = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line not in lines:
                lines.append(line)
    return lines

def make_request(url, headers=None, method='GET'):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        # Prevent SSL verification issues on standard python installations
        import ssl
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=context) as response:
            return response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:
        return 0, str(e)

def get_supabase_table(project_url, anon_key):
    base_url = project_url.rstrip('/')
    openapi_url = f"{base_url}/rest/v1/"
    headers = {
        'apikey': anon_key,
        'Authorization': f'Bearer {anon_key}'
    }
    
    status, body = make_request(openapi_url, headers)
    if status != 200:
        raise Exception(f"Failed to fetch database schema (HTTP {status}). {body[:150]}")
    
    try:
        spec = json.loads(body)
        paths = spec.get('paths', {})
        # Find first path that starts with / and is not the root "/"
        tables = [p.lstrip('/') for p in paths.keys() if p != '/']
        if not tables:
            raise Exception("No tables exposed in the API schema.")
        return tables[0]
    except json.JSONDecodeError:
        raise Exception("Failed to parse OpenAPI JSON response from Supabase.")

def check_supabase_db(project_url, anon_key, table_name):
    base_url = project_url.rstrip('/')
    query_url = f"{base_url}/rest/v1/{table_name}?select=*&limit=1"
    headers = {
        'apikey': anon_key,
        'Authorization': f'Bearer {anon_key}'
    }
    
    status, body = make_request(query_url, headers)
    if status == 200:
        try:
            res = json.loads(body)
            if isinstance(res, list):
                return True, status, f"Success: queried table '{table_name}' successfully."
            else:
                return False, status, f"Unexpected response format (not a list): {body[:100]}"
        except json.JSONDecodeError:
            return False, status, f"Response body was not valid JSON: {body[:100]}"
    else:
        if status == 401:
            reason = "Authentication/credentials problem (unauthorized)"
        elif status == 403:
            reason = "Permissions/Row-Level Security (RLS) problem"
        elif status == 404:
            reason = "Table not found / wrong endpoint"
        elif status == 0:
            reason = f"Connectivity failure: {body}"
        else:
            reason = f"Database/Server error"
        return False, status, f"{reason} ({body.strip()[:100]})"

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
        
    print("--------------------------------")
    print("Keep Hope Alive")
    print("--------------------------------\n")
    
    urls = read_lines("urls.txt")
    supabase_urls = read_lines("supabase-projects.txt")
    
    failures = 0
    
    print("Frontend & Backend:")
    if not urls:
        print("  (No URLs configured in urls.txt)")
    for url in urls:
        status, _ = make_request(url)
        if 200 <= status < 400:
            print(f"✓ {url} -> {status}")
        else:
            print(f"✗ {url} -> {status if status != 0 else 'TIMEOUT/ERROR'}")
            failures += 1
            
    print("\nSupabase:")
    if not supabase_urls:
        print("  (No Supabase projects configured in supabase-projects.txt)")
    for url in supabase_urls:
        # Extract project ID
        match = re.search(r'https://([^.]+)\.supabase\.co', url)
        if not match:
            print(f"✗ {url}\n  ✗ Invalid Supabase URL format")
            failures += 1
            continue
            
        project_id = match.group(1)
        env_var_name = f"SUPABASE_ANON_KEY_{project_id.upper()}"
        anon_key = os.environ.get(env_var_name)
        
        if not anon_key:
            print(f"✗ {url}")
            print("  ✗ Configuration FAILED")
            print(f"    Reason: Environment variable {env_var_name} is missing.")
            print("    Please set this secret in your GitHub repository.")
            failures += 1
            continue
            
        # First verify API is reachable by calling OpenAPI root
        # If this fails with 401/403, we can still parse table name if it returned schema,
        # but let's just run get_supabase_table directly
        try:
            table_name = get_supabase_table(url, anon_key)
            # Query the table
            success, status_code, message = check_supabase_db(url, anon_key, table_name)
            if success:
                print(f"✓ {url}")
                print("  ✓ API reachable")
                print(f"  ✓ PostgreSQL-backed query successful (table: {table_name})")
                print("  ✓ Database keep-alive successful")
            else:
                print(f"✗ {url}")
                print("  ✓ API reachable")
                print(f"  ✗ PostgreSQL-backed query FAILED")
                print(f"    HTTP: {status_code}")
                print(f"    Reason: {message}")
                failures += 1
        except Exception as e:
            print(f"✗ {url}")
            print("  ✗ API unreachable / query FAILED")
            print(f"    Reason: {str(e)}")
            failures += 1
            
    print("\n--------------------------------")
    if failures == 0:
        print("Keep-alive completed successfully")
        print("--------------------------------")
        sys.exit(0)
    else:
        print(f"Keep-alive completed with {failures} error(s)")
        print("--------------------------------")
        sys.exit(1)

if __name__ == "__main__":
    main()
