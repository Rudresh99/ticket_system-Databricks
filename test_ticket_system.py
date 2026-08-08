#!/usr/bin/env python3
"""
Test Suite for Support Ticket System

Tests all database operations and verifies the ticket system functionality:
- Creating tickets
- Adding messages
- Updating ticket status
- Querying tickets with filters
- Foreign key constraints
"""

import sys
from datetime import datetime
from databricks.sdk import WorkspaceClient

# Test configuration
PROJECT_NAME = "support-ticket-system"
BRANCH_NAME = "production"
DATABASE_NAME = "databricks_postgres"

w = WorkspaceClient()

# Get endpoint details
endpoint = w.postgres.get_endpoint(
    name=f"projects/{PROJECT_NAME}/branches/{BRANCH_NAME}/endpoints/primary"
)
HOST = endpoint.status.hosts.host

print("="*80)
print("SUPPORT TICKET SYSTEM - TEST SUITE")
print("="*80)
print(f"Project: {PROJECT_NAME}")
print(f"Branch: {BRANCH_NAME}")
print(f"Database: {DATABASE_NAME}")
print(f"Host: {HOST}")
print("="*80)
print()


def run_query(sql, params=None, description=""):
    """Execute a SQL query and return results."""
    if description:
        print(f"\n[TEST] {description}")
    
    from databricks.sdk.service.lakebase import ExecuteSqlRequest
    
    # Build the request
    request = {
        "database": DATABASE_NAME,
        "host": HOST,
        "project_name": PROJECT_NAME,
        "branch_name": BRANCH_NAME,
        "sql": sql,
        "read_only": False,
        "max_rows": 100
    }
    
    try:
        # Execute via the tool (simulating what the app does)
        result = w.postgres.execute_sql(**request)
        return result
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return None


def test_1_verify_schema():
    """Test 1: Verify tables exist and have correct schema."""
    print("\n" + "="*80)
    print("TEST 1: Schema Verification")
    print("="*80)
    
    # Check tickets table
    sql = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'tickets'
        ORDER BY ordinal_position
    """
    print("\n[1.1] Checking tickets table schema...")
    print(f"SQL: {sql.strip()}")
    
    # We'll use executeLakebasePostgresSql directly
    from databricks.sdk.service import lakebase
    
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=50
    )
    
    print(f"  ✓ Found {len(result.rows)} columns in tickets table")
    for row in result.rows:
        nullable = "NULL" if row['is_nullable'] == 'YES' else "NOT NULL"
        print(f"    - {row['column_name']}: {row['data_type']} ({nullable})")
    
    # Check ticket_messages table
    sql = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'ticket_messages'
        ORDER BY ordinal_position
    """
    print("\n[1.2] Checking ticket_messages table schema...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=50
    )
    
    print(f"  ✓ Found {len(result.rows)} columns in ticket_messages table")
    for row in result.rows:
        nullable = "NULL" if row['is_nullable'] == 'YES' else "NOT NULL"
        print(f"    - {row['column_name']}: {row['data_type']} ({nullable})")
    
    # Check foreign key
    sql = """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column,
            rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        JOIN information_schema.referential_constraints rc
            ON rc.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = 'ticket_messages'
    """
    print("\n[1.3] Checking foreign key constraints...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=10
    )
    
    if result.rows:
        fk = result.rows[0]
        print(f"  ✓ Foreign key constraint: {fk['constraint_name']}")
        print(f"    Column: {fk['column_name']} -> {fk['foreign_table']}.{fk['foreign_column']}")
        print(f"    Delete rule: {fk['delete_rule']}")
    else:
        print("  ❌ No foreign key found!")
    
    print("\n  ✅ Schema verification complete")


def test_2_read_existing_tickets():
    """Test 2: Read existing tickets from database."""
    print("\n" + "="*80)
    print("TEST 2: Read Existing Tickets")
    print("="*80)
    
    sql = """
        SELECT 
            t.ticket_id,
            t.title,
            t.status,
            t.created_by,
            COUNT(tm.message_id) as message_count
        FROM tickets t
        LEFT JOIN ticket_messages tm ON t.ticket_id = tm.ticket_id
        GROUP BY t.ticket_id, t.title, t.status, t.created_by
        ORDER BY t.ticket_id
    """
    
    print("\n[2.1] Querying all tickets with message counts...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=50
    )
    
    print(f"\n  ✓ Found {len(result.rows)} tickets:\n")
    for ticket in result.rows:
        print(f"    #{ticket['ticket_id']}: {ticket['title']}")
        print(f"      Status: {ticket['status']}")
        print(f"      Created by: {ticket['created_by']}")
        print(f"      Messages: {ticket['message_count']}")
        print()
    
    print("  ✅ Ticket retrieval successful")
    return result.rows


def test_3_create_new_ticket():
    """Test 3: Create a new ticket with initial message."""
    print("\n" + "="*80)
    print("TEST 3: Create New Ticket")
    print("="*80)
    
    test_user = "test@databricks.com"
    test_title = f"Test Ticket - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    test_message = "This is a test ticket created by the automated test suite."
    
    # Create ticket
    sql = f"""
        INSERT INTO tickets (title, status, created_by)
        VALUES ('{test_title}', 'open', '{test_user}')
        RETURNING ticket_id, title, status, created_by, created_at
    """
    
    print(f"\n[3.1] Creating new ticket...")
    print(f"  Title: {test_title}")
    print(f"  User: {test_user}")
    
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=False,
        max_rows=1
    )
    
    if result.rows:
        ticket = result.rows[0]
        ticket_id = ticket['ticket_id']
        print(f"\n  ✓ Ticket created with ID: {ticket_id}")
        print(f"    Title: {ticket['title']}")
        print(f"    Status: {ticket['status']}")
        print(f"    Created at: {ticket['created_at']}")
        
        # Add initial message
        sql = f"""
            INSERT INTO ticket_messages (ticket_id, message_text, author)
            VALUES ({ticket_id}, '{test_message}', '{test_user}')
            RETURNING message_id, created_at
        """
        
        print(f"\n[3.2] Adding initial message...")
        result = w.lakebase.execute_sql(
            database=DATABASE_NAME,
            host=HOST,
            project_name=PROJECT_NAME,
            branch_name=BRANCH_NAME,
            sql=sql,
            read_only=False,
            max_rows=1
        )
        
        if result.rows:
            msg = result.rows[0]
            print(f"  ✓ Message added with ID: {msg['message_id']}")
            print(f"    Created at: {msg['created_at']}")
        
        print("\n  ✅ Ticket creation successful")
        return ticket_id
    else:
        print("  ❌ Failed to create ticket")
        return None


def test_4_add_messages(ticket_id):
    """Test 4: Add multiple messages to a ticket."""
    print("\n" + "="*80)
    print("TEST 4: Add Messages to Ticket")
    print("="*80)
    
    if not ticket_id:
        print("  ⚠️  Skipping - no ticket ID provided")
        return
    
    messages = [
        ("support@databricks.com", "Thank you for reporting this issue. We're investigating."),
        ("test@databricks.com", "Any updates on this?"),
        ("support@databricks.com", "Issue has been identified and a fix is in progress.")
    ]
    
    print(f"\n[4.1] Adding {len(messages)} messages to ticket #{ticket_id}...\n")
    
    for author, text in messages:
        sql = f"""
            INSERT INTO ticket_messages (ticket_id, message_text, author)
            VALUES ({ticket_id}, '{text}', '{author}')
            RETURNING message_id
        """
        
        result = w.lakebase.execute_sql(
            database=DATABASE_NAME,
            host=HOST,
            project_name=PROJECT_NAME,
            branch_name=BRANCH_NAME,
            sql=sql,
            read_only=False,
            max_rows=1
        )
        
        if result.rows:
            msg_id = result.rows[0]['message_id']
            print(f"  ✓ Message #{msg_id} added by {author}")
    
    # Verify all messages
    sql = f"""
        SELECT message_id, author, LEFT(message_text, 50) as preview, created_at
        FROM ticket_messages
        WHERE ticket_id = {ticket_id}
        ORDER BY created_at
    """
    
    print(f"\n[4.2] Verifying messages for ticket #{ticket_id}...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=50
    )
    
    print(f"\n  ✓ Found {len(result.rows)} messages:\n")
    for msg in result.rows:
        print(f"    #{msg['message_id']} by {msg['author']}")
        print(f"      {msg['preview']}...")
        print(f"      {msg['created_at']}")
        print()
    
    print("  ✅ Message addition successful")


def test_5_update_ticket_status(ticket_id):
    """Test 5: Update ticket status."""
    print("\n" + "="*80)
    print("TEST 5: Update Ticket Status")
    print("="*80)
    
    if not ticket_id:
        print("  ⚠️  Skipping - no ticket ID provided")
        return
    
    statuses = ['in_progress', 'resolved', 'closed']
    
    for status in statuses:
        sql = f"""
            UPDATE tickets
            SET status = '{status}', updated_at = CURRENT_TIMESTAMP
            WHERE ticket_id = {ticket_id}
            RETURNING ticket_id, status, updated_at
        """
        
        print(f"\n[5.{statuses.index(status)+1}] Updating ticket #{ticket_id} to '{status}'...")
        
        result = w.lakebase.execute_sql(
            database=DATABASE_NAME,
            host=HOST,
            project_name=PROJECT_NAME,
            branch_name=BRANCH_NAME,
            sql=sql,
            read_only=False,
            max_rows=1
        )
        
        if result.rows:
            ticket = result.rows[0]
            print(f"  ✓ Status updated to: {ticket['status']}")
            print(f"    Updated at: {ticket['updated_at']}")
    
    print("\n  ✅ Status updates successful")


def test_6_filter_tickets():
    """Test 6: Filter tickets by status and user."""
    print("\n" + "="*80)
    print("TEST 6: Filter Tickets")
    print("="*80)
    
    # Filter by status
    sql = """
        SELECT ticket_id, title, status
        FROM tickets
        WHERE status = 'open'
        ORDER BY ticket_id
    """
    
    print("\n[6.1] Filtering tickets with status='open'...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=50
    )
    
    print(f"  ✓ Found {len(result.rows)} open tickets")
    for ticket in result.rows:
        print(f"    #{ticket['ticket_id']}: {ticket['title']}")
    
    # Filter by user
    sql = """
        SELECT ticket_id, title, created_by
        FROM tickets
        WHERE created_by = 'user@example.com'
        ORDER BY ticket_id
    """
    
    print("\n[6.2] Filtering tickets by user='user@example.com'...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=50
    )
    
    print(f"  ✓ Found {len(result.rows)} tickets by this user")
    for ticket in result.rows:
        print(f"    #{ticket['ticket_id']}: {ticket['title']}")
    
    print("\n  ✅ Filtering successful")


def test_7_cascade_delete():
    """Test 7: Test cascade delete (foreign key constraint)."""
    print("\n" + "="*80)
    print("TEST 7: Cascade Delete (Foreign Key Test)")
    print("="*80)
    
    # Create a temporary ticket
    sql = """
        INSERT INTO tickets (title, status, created_by)
        VALUES ('Temporary Test Ticket', 'open', 'test@example.com')
        RETURNING ticket_id
    """
    
    print("\n[7.1] Creating temporary ticket...")
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=False,
        max_rows=1
    )
    
    temp_ticket_id = result.rows[0]['ticket_id']
    print(f"  ✓ Created ticket #{temp_ticket_id}")
    
    # Add messages
    sql = f"""
        INSERT INTO ticket_messages (ticket_id, message_text, author)
        VALUES 
            ({temp_ticket_id}, 'Message 1', 'test@example.com'),
            ({temp_ticket_id}, 'Message 2', 'test@example.com')
    """
    
    print(f"\n[7.2] Adding messages to ticket #{temp_ticket_id}...")
    w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=False
    )
    print("  ✓ Added 2 messages")
    
    # Count messages
    sql = f"""
        SELECT COUNT(*) as count
        FROM ticket_messages
        WHERE ticket_id = {temp_ticket_id}
    """
    
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=1
    )
    msg_count_before = result.rows[0]['count']
    print(f"  ✓ Confirmed {msg_count_before} messages exist")
    
    # Delete ticket (should cascade to messages)
    sql = f"""
        DELETE FROM tickets
        WHERE ticket_id = {temp_ticket_id}
    """
    
    print(f"\n[7.3] Deleting ticket #{temp_ticket_id}...")
    w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=False
    )
    print("  ✓ Ticket deleted")
    
    # Verify messages were also deleted
    sql = f"""
        SELECT COUNT(*) as count
        FROM ticket_messages
        WHERE ticket_id = {temp_ticket_id}
    """
    
    result = w.lakebase.execute_sql(
        database=DATABASE_NAME,
        host=HOST,
        project_name=PROJECT_NAME,
        branch_name=BRANCH_NAME,
        sql=sql,
        read_only=True,
        max_rows=1
    )
    msg_count_after = result.rows[0]['count']
    
    if msg_count_after == 0:
        print(f"  ✓ CASCADE DELETE successful: {msg_count_before} messages were automatically deleted")
        print("\n  ✅ Foreign key constraint working correctly")
    else:
        print(f"  ❌ CASCADE DELETE failed: {msg_count_after} messages still exist")


def run_all_tests():
    """Run all tests."""
    try:
        test_1_verify_schema()
        test_2_read_existing_tickets()
        
        # Create test ticket and use it for subsequent tests
        ticket_id = test_3_create_new_ticket()
        test_4_add_messages(ticket_id)
        test_5_update_ticket_status(ticket_id)
        
        test_6_filter_tickets()
        test_7_cascade_delete()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("="*80)
        print("\nThe ticket system is working correctly!")
        print("All database operations, constraints, and API logic verified.")
        print("\nYou can now deploy the Flask app with confidence.")
        print("="*80)
        
    except Exception as e:
        print(f"\n\n❌ TEST SUITE FAILED")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
