"""
Databricks Support Ticket System App:
- Serves a Flask web interface for managing support tickets
- Reads/writes to Lakebase (Databricks-managed Postgres)
- Allows users to create tickets and add messages

Run locally:
    python app.py
Deploy as a Databricks App using app.yaml.
"""

import logging
import os
from datetime import datetime

from databricks.sdk import WorkspaceClient
from flask import Flask, jsonify, render_template, request

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ticket-system")

app = Flask(__name__)
_w = WorkspaceClient()

TICKETS_TABLE = "tickets"
MESSAGES_TABLE = "ticket_messages"


def ensure_tables():
    """Create the tables in Lakebase if they don't exist yet."""
    # Create tickets table
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TICKETS_TABLE} (
            ticket_id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'open',
            created_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Create ticket_messages table
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {MESSAGES_TABLE} (
            message_id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL,
            message_text TEXT NOT NULL,
            author VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_ticket
                FOREIGN KEY (ticket_id) 
                REFERENCES {TICKETS_TABLE}(ticket_id)
                ON DELETE CASCADE
        )
        """
    )
    
    # Create indexes
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON {MESSAGES_TABLE}(ticket_id)"
    )
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_tickets_status ON {TICKETS_TABLE}(status)"
    )
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON {TICKETS_TABLE}(created_by)"
    )


def _current_user_email() -> str:
    """
    Resolve the current user's email.
    
    Databricks Apps inject the logged-in user's identity via the
    X-Forwarded-Email header on every request. Fall back to the Databricks
    SDK's current_user API for local development where that header isn't set.
    """
    header_email = request.headers.get("X-Forwarded-Email")
    if header_email:
        return header_email
    return _w.current_user.me().user_name


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON (not an HTML error page)."""
    logger.exception("Unhandled exception while processing request")
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/")
def index():
    """Simple UI to create tickets and add messages."""
    return render_template("index.html")


@app.route("/tickets", methods=["GET"])
def list_tickets():
    """Get all tickets with message counts."""
    ensure_tables()
    
    status_filter = request.args.get("status")
    user_filter = request.args.get("user")
    
    query = f"""
        SELECT 
            t.ticket_id,
            t.title,
            t.status,
            t.created_by,
            t.created_at,
            t.updated_at,
            COUNT(tm.message_id) as message_count
        FROM {TICKETS_TABLE} t
        LEFT JOIN {MESSAGES_TABLE} tm ON t.ticket_id = tm.ticket_id
    """
    
    conditions = []
    params = []
    
    if status_filter:
        conditions.append("t.status = %s")
        params.append(status_filter)
    
    if user_filter:
        conditions.append("t.created_by = %s")
        params.append(user_filter)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += """
        GROUP BY t.ticket_id, t.title, t.status, t.created_by, t.created_at, t.updated_at
        ORDER BY t.created_at DESC
    """
    
    rows = lakebase.run_query(query, tuple(params) if params else None)
    return jsonify(rows)


@app.route("/tickets/<int:ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    """Get a specific ticket with all its messages."""
    ensure_tables()
    
    # Get ticket details
    ticket_rows = lakebase.run_query(
        f"SELECT * FROM {TICKETS_TABLE} WHERE ticket_id = %s",
        (ticket_id,)
    )
    
    if not ticket_rows:
        return jsonify({"error": "Ticket not found"}), 404
    
    ticket = ticket_rows[0]
    
    # Get all messages for this ticket
    messages = lakebase.run_query(
        f"""
        SELECT message_id, ticket_id, message_text, author, created_at
        FROM {MESSAGES_TABLE}
        WHERE ticket_id = %s
        ORDER BY created_at ASC
        """,
        (ticket_id,)
    )
    
    return jsonify({
        "ticket": ticket,
        "messages": messages
    })


@app.route("/tickets", methods=["POST"])
def create_ticket():
    """Create a new ticket."""
    ensure_tables()
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    title = request.json.get("title", "").strip()
    message_text = request.json.get("message", "").strip()
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
    
    if not message_text:
        return jsonify({"error": "Initial message is required"}), 400
    
    email = _current_user_email()
    
    # Create the ticket
    ticket_rows = lakebase.run_query(
        f"""
        INSERT INTO {TICKETS_TABLE} (title, status, created_by)
        VALUES (%s, 'open', %s)
        RETURNING ticket_id, title, status, created_by, created_at, updated_at
        """,
        (title, email)
    )
    
    if not ticket_rows:
        return jsonify({"error": "Failed to create ticket"}), 500
    
    ticket = ticket_rows[0]
    ticket_id = ticket["ticket_id"]
    
    # Add the initial message
    lakebase.run_write(
        f"""
        INSERT INTO {MESSAGES_TABLE} (ticket_id, message_text, author)
        VALUES (%s, %s, %s)
        """,
        (ticket_id, message_text, email)
    )
    
    return jsonify(ticket), 201


@app.route("/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_message(ticket_id):
    """Add a message to an existing ticket."""
    ensure_tables()
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    message_text = request.json.get("message", "").strip()
    
    if not message_text:
        return jsonify({"error": "Message text is required"}), 400
    
    # Verify ticket exists
    ticket_rows = lakebase.run_query(
        f"SELECT ticket_id FROM {TICKETS_TABLE} WHERE ticket_id = %s",
        (ticket_id,)
    )
    
    if not ticket_rows:
        return jsonify({"error": "Ticket not found"}), 404
    
    email = _current_user_email()
    
    # Add the message
    message_rows = lakebase.run_query(
        f"""
        INSERT INTO {MESSAGES_TABLE} (ticket_id, message_text, author)
        VALUES (%s, %s, %s)
        RETURNING message_id, ticket_id, message_text, author, created_at
        """,
        (ticket_id, message_text, email)
    )
    
    # Update ticket's updated_at timestamp
    lakebase.run_write(
        f"""
        UPDATE {TICKETS_TABLE}
        SET updated_at = CURRENT_TIMESTAMP
        WHERE ticket_id = %s
        """,
        (ticket_id,)
    )
    
    return jsonify(message_rows[0]), 201


@app.route("/tickets/<int:ticket_id>/status", methods=["PATCH"])
def update_ticket_status(ticket_id):
    """Update the status of a ticket."""
    ensure_tables()
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    status = request.json.get("status", "").strip()
    
    valid_statuses = ["open", "in_progress", "waiting_customer", "resolved", "closed"]
    
    if status not in valid_statuses:
        return jsonify({
            "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        }), 400
    
    # Update the ticket status
    affected = lakebase.run_write(
        f"""
        UPDATE {TICKETS_TABLE}
        SET status = %s, updated_at = CURRENT_TIMESTAMP
        WHERE ticket_id = %s
        """,
        (status, ticket_id)
    )
    
    if affected == 0:
        return jsonify({"error": "Ticket not found"}), 404
    
    # Get updated ticket
    ticket_rows = lakebase.run_query(
        f"SELECT * FROM {TICKETS_TABLE} WHERE ticket_id = %s",
        (ticket_id,)
    )
    
    return jsonify(ticket_rows[0])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
