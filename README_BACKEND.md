# FastAPI Backend Setup

This project uses a FastAPI backend to serve mock data for alerts, resources, security findings, and optimization configurations.

## Starting the Backend Server

1. **Navigate to the backend directory:**
   ```bash
   cd src/backend
   ```

2. **Install dependencies (first time only):**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure AWS credentials (optional, for agent integration):**
   ```bash
   cp .env.example .env
   # Edit .env with your AWS credentials
   ```

4. **Start the FastAPI server:**
   ```bash
   python main.py
   ```

   The server will start on `http://localhost:8000`

## AWS Strands Agent Integration

All main endpoints now support AI-driven insights via the AWS Strands Agent. Add `?use_agent=true` to any endpoint to enable agent analysis:

### Agent-Enhanced Endpoints
- `GET /alerts?use_agent=true` - Get alerts with AI severity classification and action summaries
- `GET /resources?use_agent=true` - Get resources with AI cost-saving recommendations
- `GET /security?use_agent=true` - Get security findings with AI risk analysis and compliance mapping
- `GET /optimization?use_agent=true` - Get optimization data with AI multi-factor recommendations

### Agent Response Format
When `use_agent=true`, responses include an additional `agent_insights` field:
```json
{
  "data": [...],
  "agent_insights": {
    "agent_enabled": true,
    "insights": "Full AI-generated analysis...",
    "data_type": "alerts|resources|security|optimization",
    "session_id": "uuid",
    "recommendations": ["recommendation 1", "recommendation 2", ...]
  }
}
```

### AWS Configuration
Set the following environment variables in `.env`:
- `AWS_REGION` - AWS region (default: us-east-1)
- `AWS_ACCESS_KEY_ID` - Your AWS access key
- `AWS_SECRET_ACCESS_KEY` - Your AWS secret key
- `AWS_STRANDS_AGENT_ID` - Your Strands Agent ID
- `AWS_STRANDS_AGENT_ALIAS_ID` - Agent alias ID (default: TSTALIASID)

### Cost Optimization
The agent integration uses:
- **AWS Bedrock Agent Runtime** - Pay per request
- **AWS Lambda** (optional) - Free tier eligible
- **DynamoDB** (optional) - For logging and state management
- **CloudWatch Logs** - For monitoring

Expected costs under normal usage: < $100/month

### Fallback Behavior
If AWS credentials are not configured or the agent is unavailable, endpoints will return static/mock data as before. The app remains fully functional without AWS integration.

## Available Endpoints

### Alerts
- `GET /alerts` - Fetch all alerts
- `GET /alerts/{alert_id}` - Fetch specific alert
- `PUT /alerts/{alert_id}` - Update alert status
- `DELETE /alerts/{alert_id}` - Delete alert

### Resources
- `GET /resources` - Fetch all resources
- `GET /resources/{resource_id}` - Fetch specific resource
- `PUT /resources/{resource_id}/optimize` - Optimize resource

### Security
- `GET /security` - Fetch security findings and summary
- `GET /security/{finding_id}` - Fetch specific finding
- `POST /security/update` - Update finding status

### Optimization
- `GET /optimization` - Fetch optimization config and projections
- `POST /optimization/config` - Update optimization configuration
- `POST /optimization/apply` - Apply specific optimization

### Notifications
- `GET /notifications/email?email={email}` - Fetch email notification preferences
- `PUT /notifications/email?email={email}` - Update email notification settings
- `POST /notifications/email/send` - Manually send monthly report email
- `GET /notifications/slack?email={email}` - Fetch Slack notification preferences
- `PUT /notifications/slack?email={email}` - Update Slack notification settings
- `POST /notifications/slack/send` - Send test Slack message

## CORS Configuration

The backend is configured with CORS to allow requests from any origin during development:
```python
allow_origins=["*"]
allow_methods=["*"]
allow_headers=["*"]
```

## Mock Data

All mock data is defined in the respective module files:
- `alerts.py` - Alert mock data
- `resources.py` - Resource mock data
- `security.py` - Security findings mock data
- `optimization.py` - Optimization config and recommendations
- `notifications.py` - Notification settings and report generation

## Notification Features

### Email Reports
The backend supports automated monthly email reports that include:
- Infrastructure overview (resources, utilization metrics, idle resources)
- Cost optimization summary (savings opportunities, spend trends)
- Alert analytics (total alerts, resolved, top issues)
- Security health (vulnerabilities, compliance drift)
- AI recommendations (top 3 optimization suggestions)

### Slack Integration
Real-time notifications to Slack channels:
- Critical alerts with severity, timestamp, and "View Details" link
- Weekly summaries every Friday with key metrics
- Test message functionality to verify webhook connection

## Frontend Fallback

If the backend server is not running, the frontend will automatically:
1. Log an error to the console with a ❌ emoji
2. Fall back to using local mock data
3. Show a toast notification with instructions to start the server

## Troubleshooting

**Error: "Failed to fetch"**
- Make sure the FastAPI server is running on localhost:8000
- Check that no firewall or security software is blocking port 8000
- Verify Python and FastAPI are installed correctly

**Error: "ERR_BLOCKED_BY_CLIENT"**
- This is typically caused by browser extensions (ad blockers)
- Try disabling extensions or adding localhost to the allow list
- Check browser console for specific blocking details

**Error: "CORS policy error"**
- Ensure the CORS middleware is properly configured in main.py
- Verify the frontend is making requests to the correct URL
- Check that all required headers are included in requests
