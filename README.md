# Support Ticket System

A complete internal support ticket system built on Databricks Lakebase (Postgres-compatible serverless database).

## Overview

This application provides a full-featured support ticket management system where users can:
- Create support tickets
- Add messages/comments to tickets
- Track ticket status (open, in_progress, closed)
- Maintain conversation history for each ticket

## Database Connection

**Lakebase Project**: `support-ticket-system`
**Branch**: `production`
**Endpoint**: `primary`
**Host**: `ep-aged-water-d8qvt48e.database.us-east-2.cloud.databricks.com`
**Database**: `databricks_postgres`

## Schema

### Tables

#### `tickets`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| ticket_id | SERIAL | PRIMARY KEY | Auto-incrementing ticket ID |
| title | VARCHAR(255) | NOT NULL | Ticket title/subject |
| status | VARCHAR(50) | NOT NULL, DEFAULT 'open' | Current status |
| created_by | VARCHAR(255) | NOT NULL | Creator's email |
| created_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Last update timestamp |

**Indexes**:
- `idx_tickets_status` - Fast filtering by status
- `idx_tickets_created_by` - Fast lookups by creator

#### `ticket_messages`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| message_id | SERIAL | PRIMARY KEY | Auto-incrementing message ID |
| ticket_id | INTEGER | NOT NULL, FOREIGN KEY | References tickets(ticket_id) |
| message_text | TEXT | NOT NULL | Message content |
| author | VARCHAR(255) | NOT NULL | Message author's email |
| created_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Message timestamp |

**Foreign Keys**:
- `ticket_id` → `tickets(ticket_id)` ON DELETE CASCADE

**Indexes**:
- `idx_ticket_messages_ticket_id` - Fast lookups of messages by ticket

## Python Connection Example

```python
import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get endpoint details
endpoint = w.postgres.get_endpoint(
    name="projects/support-ticket-system/branches/production/endpoints/primary"
)
host = endpoint.status.hosts.host

# Get credentials
username = w.current_user.me().user_name
token = w.postgres.generate_database_credential(endpoint=endpoint.name).token

# Connect
conn = psycopg.connect(
    host=host,
    dbname="databricks_postgres",
    user=username,
    password=token,
    sslmode="require"
)
```

## Common Operations

### Create a New Ticket

```python
with conn.cursor() as cur:
    cur.execute(
        """INSERT INTO tickets (title, status, created_by) 
           VALUES (%s, %s, %s) 
           RETURNING ticket_id""",
        ("Issue with data pipeline", "open", "user@example.com")
    )
    ticket_id = cur.fetchone()[0]
    conn.commit()
    print(f"Created ticket #{ticket_id}")
```

### Add a Message to a Ticket

```python
with conn.cursor() as cur:
    cur.execute(
        """INSERT INTO ticket_messages (ticket_id, message_text, author)
           VALUES (%s, %s, %s)""",
        (ticket_id, "The pipeline fails at the transformation step.", "user@example.com")
    )
    conn.commit()
```

### Get All Messages for a Ticket

```python
with conn.cursor() as cur:
    cur.execute(
        """SELECT message_id, message_text, author, created_at
           FROM ticket_messages
           WHERE ticket_id = %s
           ORDER BY created_at ASC""",
        (ticket_id,)
    )
    messages = cur.fetchall()
    for msg in messages:
        print(f"[{msg[3]}] {msg[2]}: {msg[1]}")
```

### Update Ticket Status

```python
with conn.cursor() as cur:
    cur.execute(
        """UPDATE tickets 
           SET status = %s, updated_at = CURRENT_TIMESTAMP
           WHERE ticket_id = %s""",
        ("in_progress", ticket_id)
    )
    conn.commit()
```

### Get All Open Tickets

```python
with conn.cursor() as cur:
    cur.execute(
        """SELECT ticket_id, title, created_by, created_at
           FROM tickets
           WHERE status = 'open'
           ORDER BY created_at DESC"""
    )
    tickets = cur.fetchall()
    for ticket in tickets:
        print(f"#{ticket[0]}: {ticket[1]} (by {ticket[2]})")
```

### Get Ticket Summary with Message Counts

```python
with conn.cursor() as cur:
    cur.execute(
        """SELECT 
               t.ticket_id,
               t.title,
               t.status,
               t.created_by,
               COUNT(tm.message_id) as message_count,
               MAX(tm.created_at) as last_message_at
           FROM tickets t
           LEFT JOIN ticket_messages tm ON t.ticket_id = tm.ticket_id
           GROUP BY t.ticket_id, t.title, t.status, t.created_by
           ORDER BY last_message_at DESC NULLS LAST"""
    )
    summary = cur.fetchall()
    for row in summary:
        print(f"#{row[0]}: {row[1]} [{row[2]}] - {row[4]} messages")
```

## Using executeLakebasePostgresSql Tool

You can also use the Databricks tool for quick queries without managing connections:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Query example
result = w.postgres.execute_sql(
    database="databricks_postgres",
    host="ep-aged-water-d8qvt48e.database.us-east-2.cloud.databricks.com",
    project_name="support-ticket-system",
    branch_name="production",
    sql="SELECT * FROM tickets WHERE status = 'open'",
    read_only=True
)
```

## Features

### Referential Integrity
- Foreign key constraint ensures every message belongs to a valid ticket
- CASCADE DELETE: When a ticket is deleted, all its messages are automatically removed

### Performance Optimization
- Indexed columns for fast queries on status, creator, and ticket relationships
- Efficient JOIN operations between tickets and messages

### Timestamp Tracking
- Automatic timestamps on ticket and message creation
- Updated_at field for tracking ticket modifications

## Status Values

Recommended status values:
- `open` - New ticket, awaiting response
- `in_progress` - Ticket is being worked on
- `waiting_customer` - Waiting for customer response
- `resolved` - Issue resolved, awaiting closure
- `closed` - Ticket closed

## Best Practices

1. **Token Management**: OAuth tokens expire after 1 hour. For production apps:
   - Implement token refresh logic
   - Use connection pooling with `pool_recycle=2700` (45 min)

2. **Connection Pooling**: Use SQLAlchemy or psycopg pool for production:
   ```python
   from psycopg_pool import ConnectionPool
   
   pool = ConnectionPool(
       conninfo=f"host={host} dbname=databricks_postgres user={username} sslmode=require",
       min_size=2,
       max_size=10
   )
   ```

3. **Error Handling**: Always wrap database operations in try-except blocks

4. **Transactions**: Use transactions for operations that modify multiple tables

## Next Steps

- [ ] Build a web UI (consider Databricks Apps with Streamlit/Dash)
- [ ] Add email notifications for new tickets/messages
- [ ] Implement user authentication and authorization
- [ ] Add ticket assignment to support staff
- [ ] Create analytics dashboards for ticket metrics
- [ ] Add file attachments to tickets
- [ ] Implement ticket priority levels
- [ ] Add SLA tracking

## Resources

- [Lakebase Documentation](https://docs.databricks.com/en/oltp/index.html)
- [Databricks SDK for Python](https://databricks-sdk-py.readthedocs.io/)
- [psycopg3 Documentation](https://www.psycopg.org/psycopg3/docs/)

## Support

For issues or questions about this system, contact your Databricks workspace administrator.
