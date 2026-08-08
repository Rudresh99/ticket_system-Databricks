# Support Ticket System - Setup Guide

This guide walks you through setting up and deploying the Support Ticket System as a Databricks App.

## Prerequisites

1. **Lakebase Project**: The `support-ticket-system` Lakebase project should already be created
2. **Databricks Workspace**: Access to a Databricks workspace with Apps enabled
3. **Databricks CLI**: Install the Databricks CLI (v0.200.0 or later)

## Step 1: Setup Lakebase Connection

### Create a Native Postgres Role

The app uses a native Postgres role with a static password (not OAuth tokens) for simplicity. This avoids token refresh complexity.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Role, RoleRoleSpec, RoleIdentityType
import secrets

w = WorkspaceClient()

# Generate a secure password
password = secrets.token_urlsafe(32)

# Create the role
w.postgres.create_role(
    parent="projects/support-ticket-system/branches/production",
    role=Role(spec=RoleRoleSpec(
        postgres_role="ticket_app_role",
        password=password,
        identity_type=RoleIdentityType.CUSTOM
    )),
    role_id="ticket-app-role"
).wait()

print(f"Role created with password: {password}")
print("Save this password - you'll need it for the connection URL!")
```

### Create the Connection URL

Construct the Postgres connection URL:

```
postgresql://ticket_app_role:{PASSWORD}@{HOST}:5432/databricks_postgres?sslmode=require
```

Replace:
- `{PASSWORD}`: The password from the previous step
- `{HOST}`: Your endpoint host (e.g., `ep-aged-water-d8qvt48e.database.us-east-2.cloud.databricks.com`)

Example:
```
postgresql://ticket_app_role:abc123xyz789@ep-aged-water-d8qvt48e.database.us-east-2.cloud.databricks.com:5432/databricks_postgres?sslmode=require
```

## Step 2: Store the Connection URL as a Secret

### Create a Secret Scope

```bash
databricks secrets create-scope ticket_system
```

### Store the Connection URL

```bash
# Base64 encode the URL
echo -n "postgresql://ticket_app_role:PASSWORD@HOST:5432/databricks_postgres?sslmode=require" | base64

# Store in secrets (paste the base64 output)
databricks secrets put-secret ticket_system lakebase-url
```

Or use Python:

```python
import base64
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Your connection URL
url = "postgresql://ticket_app_role:PASSWORD@HOST:5432/databricks_postgres?sslmode=require"

# Base64 encode
encoded = base64.b64encode(url.encode()).decode()

# Create scope and store secret
w.secrets.create_scope(scope="ticket_system")
w.secrets.put_secret(
    scope="ticket_system",
    key="lakebase-url",
    string_value=encoded
)

print("Secret stored successfully!")
```

## Step 3: Grant Schema Permissions

The app role needs permissions to create and modify tables:

```sql
-- Connect to your Lakebase database and run:
GRANT ALL ON SCHEMA public TO ticket_app_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO ticket_app_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ticket_app_role;
```

Or use psycopg:

```python
import psycopg2

# Connect with your admin credentials
conn = psycopg2.connect(
    host="ep-aged-water-d8qvt48e.database.us-east-2.cloud.databricks.com",
    dbname="databricks_postgres",
    user="your-email@example.com",
    password="your-token",
    sslmode="require"
)

cur = conn.cursor()
cur.execute("GRANT ALL ON SCHEMA public TO ticket_app_role")
cur.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO ticket_app_role")
cur.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ticket_app_role")
conn.commit()
conn.close()

print("Permissions granted!")
```

## Step 4: Deploy the App

### Initialize the App

```bash
cd ticket_system

# Create the app
databricks apps create ticket-system
```

### Deploy

```bash
databricks apps deploy ticket-system --source-code-path .
```

### Start the App

```bash
databricks apps start ticket-system
```

### Check Status

```bash
databricks apps get ticket-system
```

## Step 5: Access the App

Once deployed, the app URL will be available in the Databricks UI under **Apps**. Navigate to:

```
https://<workspace-url>/apps/ticket-system
```

## Local Development

To run the app locally for development:

1. **Set environment variable:**

```bash
export LAKEBASE_SECRET_SCOPE="ticket_system"
export LAKEBASE_SECRET_KEY="lakebase-url"
```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Run the app:**

```bash
python app.py
```

4. **Open in browser:**

```
http://localhost:8000
```

## Troubleshooting

### "Permission denied for schema public"

The app role doesn't have sufficient permissions. Re-run the GRANT statements from Step 3.

### "Could not connect to server"

Verify:
1. The Lakebase endpoint is running (not scaled to zero or starting up)
2. The connection URL is correct
3. The password is correct
4. SSL mode is set to `require`

### "Secret not found"

Verify the secret scope and key exist:

```bash
databricks secrets list-scopes
databricks secrets list-secrets ticket_system
```

### "Table already exists" on first run

This is expected if tables were created manually. The app uses `CREATE TABLE IF NOT EXISTS`, so it's safe.

## Features

### Create Tickets
- Users can create support tickets with a title and initial message
- Tickets are automatically assigned to the creating user
- Default status is "open"

### View and Filter Tickets
- View all tickets in a table
- Filter by status (open, in_progress, waiting_customer, resolved, closed)
- Filter by user
- See message count for each ticket

### Ticket Details
- Click "View" to see full ticket details
- Read all messages in conversation order
- Add new messages to the ticket
- Change ticket status

### Multi-User Support
- Each user sees all tickets but can filter to their own
- User identity is automatically captured from Databricks
- Message authors are tracked

## Next Steps

- **Email Notifications**: Add email alerts when tickets are created or updated
- **Ticket Assignment**: Allow assigning tickets to specific support staff
- **File Attachments**: Add support for attaching files to tickets
- **Priority Levels**: Add priority field (low, medium, high, urgent)
- **SLA Tracking**: Track response times and SLA compliance
- **Dashboard**: Create analytics dashboard for ticket metrics
- **Search**: Add full-text search across tickets and messages

## Resources

- [Lakebase Documentation](https://docs.databricks.com/en/oltp/index.html)
- [Databricks Apps Guide](https://docs.databricks.com/en/dev-tools/databricks-apps/index.html)
- [Flask Documentation](https://flask.palletsprojects.com/)
